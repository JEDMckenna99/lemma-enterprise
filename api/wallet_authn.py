"""
Wallet Ed25519 identity assertions for protected isHuman / wallet endpoints.

Canonical formats are shared with static/js/lemma-keys.js and scripts/lemma_wallet_keys.py.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import jsonify
from sqlalchemy.exc import IntegrityError

from auth.redis_store import delete as redis_delete
from auth.redis_store import get as redis_get
from auth.redis_store import store as redis_store
from auth.redis_store import store_nx as redis_store_nx
from auth.redis_store import consume as redis_consume
from api.wallet_keys import (
    CHALLENGE_TTL_SECONDS,
    build_assertion_payload,
    build_register_payload,
    b64url_decode,
    b64url_encode,
    verify_message,
)

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover
    Ed25519PublicKey = None  # type: ignore


@dataclass(frozen=True)
class Result:
    ok: bool
    code: str = ""
    error: str = ""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _challenge_key(nonce: str) -> str:
    return f"wallet:challenge:{nonce}"


def issue_wallet_challenge(*, wallet_id: str = "", device_id: str = "") -> dict:
    """Issue a short-lived nonce for wallet assertion signing."""
    nonce_bytes = secrets.token_bytes(32)
    nonce = b64url_encode(nonce_bytes)
    expires_at = (_utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS)).isoformat()
    redis_store(
        _challenge_key(nonce),
        {
            "wallet_id": (wallet_id or "").strip(),
            "device_id": (device_id or "").strip(),
            "created_at": _utcnow().isoformat(),
        },
        ttl_seconds=CHALLENGE_TTL_SECONDS,
    )
    return {"success": True, "nonce": nonce, "expires_at": expires_at}


def _load_registered_pubkey(
    wallet_id: str,
    *,
    device_id: str = "",
    pubkey_b64: str = "",
) -> tuple[Result, bytes | None, str | None]:
    from api.database import SessionLocal, WalletSigningKey

    if not wallet_id:
        return Result(False, "wallet_assertion_malformed", "wallet_id required"), None, None

    db = SessionLocal()
    try:
        query = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id)
        device_id = (device_id or "").strip()
        if device_id:
            row = query.filter_by(device_id=device_id).first()
            if not row and device_id != "legacy":
                row = query.filter_by(device_id="legacy").first()
        elif pubkey_b64:
            try:
                target = bytes(b64url_decode(pubkey_b64))
            except Exception:
                return Result(False, "wallet_assertion_malformed", "invalid pubkey encoding"), None, None
            row = query.filter(WalletSigningKey.pubkey == target).first()
        else:
            row = query.filter(WalletSigningKey.revoked_at.is_(None)).order_by(
                WalletSigningKey.last_used_at.desc().nullslast(),
                WalletSigningKey.created_at.desc(),
            ).first()
        if not row or row.revoked_at:
            return Result(False, "wallet_not_registered", "wallet signing key not registered"), None, None
        if not row.pubkey:
            return Result(False, "wallet_not_registered", "wallet signing key missing"), None, None
        return Result(True), bytes(row.pubkey), str(row.device_id or "legacy")
    finally:
        db.close()


def _ensure_provisional_person_after_register(db, wallet_id: str) -> None:
    """Create provisional assigned person_root when one-PPID assurance model is enabled."""
    from api.config import one_ppid_assurance_model_enabled

    if not one_ppid_assurance_model_enabled():
        return
    from api.identity_person import ensure_provisional_person_for_wallet

    ensure_provisional_person_for_wallet(db, wallet_id=wallet_id)


DEVICE_ENROLLMENT_GRANT_TTL_SECONDS = 300
LOST_DEVICE_RECOVERY_AUTH_TTL_SECONDS = 600


def _device_enrollment_grant_key(grant: str) -> str:
    digest = hashlib.sha256(str(grant or "").encode("utf-8")).hexdigest()
    return f"wallet:device-enrollment-grant:{digest}"


def _lost_device_recovery_auth_key(token: str) -> str:
    digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    return f"wallet:lost-device-recovery-auth:{digest}"


def _idv_recovery_consume_key(session_id: str) -> str:
    digest = hashlib.sha256(str(session_id or "").encode("utf-8")).hexdigest()
    return f"wallet:idv-recovery-consumed:{digest}"


def issue_device_enrollment_grant(*, wallet_id: str, source: str) -> str:
    """Issue a short-lived one-time grant after an authorized device transfer."""
    wallet_id = str(wallet_id or "").strip()
    source = str(source or "").strip()
    if not wallet_id or not source:
        raise ValueError("wallet_id and source required")
    grant = f"weg_{secrets.token_urlsafe(32)}"
    stored = redis_store(
        _device_enrollment_grant_key(grant),
        {"wallet_id": wallet_id, "source": source},
        ttl_seconds=DEVICE_ENROLLMENT_GRANT_TTL_SECONDS,
    )
    if not stored:
        raise RuntimeError("device_enrollment_grant_unavailable")
    return grant


def _consume_device_enrollment_grant(*, grant: str, wallet_id: str) -> Result:
    grant = str(grant or "").strip()
    wallet_id = str(wallet_id or "").strip()
    if not grant:
        return Result(False, "device_enrollment_authorization_required", "enrollment grant required")
    payload = redis_consume(_device_enrollment_grant_key(grant))
    if not payload:
        return Result(False, "device_enrollment_grant_invalid", "enrollment grant invalid or expired")
    if str(payload.get("wallet_id") or "").strip() != wallet_id:
        return Result(False, "device_enrollment_grant_mismatch", "enrollment grant wallet mismatch")
    return Result(True)


def issue_lost_device_recovery_authorization(
    *,
    wallet_id: str,
    idv_session_id: str,
) -> tuple[Result, str]:
    """Issue a one-time recovery auth after a verified IDV session for the wallet.

    The IDV session may authorize recovery only once. The returned token is
    required by the lost-device WebAuthn enrollment ceremony.
    """
    from api.database import SessionLocal, IsHumanVerification

    wallet_id = str(wallet_id or "").strip()
    idv_session_id = str(idv_session_id or "").strip()
    if not wallet_id or not idv_session_id:
        return Result(False, "recovery_authorization_malformed", "wallet_id and idv_session_id required"), ""

    db = SessionLocal()
    try:
        if not _wallet_has_established_identity(db, wallet_id):
            return Result(False, "recovery_identity_required", "wallet has no established identity"), ""
        record = db.query(IsHumanVerification).filter_by(session_id=idv_session_id).first()
        if not record or str(record.wallet_id or "") != wallet_id:
            return Result(False, "recovery_idv_not_found", "verified IDV session not found for wallet"), ""
        if str(record.status or "") != "verified":
            return Result(False, "recovery_idv_not_verified", "IDV session is not verified"), ""
    finally:
        db.close()

    # Atomically claim the IDV session for recovery before issuing auth.
    claimed = redis_store_nx(
        _idv_recovery_consume_key(idv_session_id),
        {"wallet_id": wallet_id, "consumed_at": _utcnow().isoformat()},
        ttl_seconds=86400,
    )
    if not claimed:
        return Result(False, "idv_recovery_already_consumed", "IDV session already used for recovery"), ""

    token = f"wra_{secrets.token_urlsafe(32)}"
    if not redis_store(
        _lost_device_recovery_auth_key(token),
        {
            "wallet_id": wallet_id,
            "idv_session_id": idv_session_id,
            "purpose": "lost_device_recovery",
        },
        ttl_seconds=LOST_DEVICE_RECOVERY_AUTH_TTL_SECONDS,
    ):
        redis_delete(_idv_recovery_consume_key(idv_session_id))
        return Result(False, "recovery_authorization_unavailable", "could not issue recovery auth"), ""
    return Result(True), token


def consume_lost_device_recovery_authorization(*, token: str, wallet_id: str) -> Result:
    token = str(token or "").strip()
    wallet_id = str(wallet_id or "").strip()
    if not token:
        return Result(False, "recovery_authorization_required", "lost-device recovery authorization required")
    payload = redis_consume(_lost_device_recovery_auth_key(token))
    if not payload:
        return Result(False, "recovery_authorization_invalid", "recovery authorization invalid or expired")
    if str(payload.get("wallet_id") or "").strip() != wallet_id:
        return Result(False, "recovery_authorization_mismatch", "recovery authorization wallet mismatch")
    if str(payload.get("purpose") or "") != "lost_device_recovery":
        return Result(False, "recovery_authorization_invalid", "recovery authorization purpose mismatch")
    return Result(True)


def _wallet_has_established_identity(db, wallet_id: str) -> bool:
    """Return whether wallet_id already carries person or verification authority."""
    from api.database import IsHumanVerification, LemmaWalletBinding

    binding = db.query(LemmaWalletBinding).filter(
        LemmaWalletBinding.wallet_id == wallet_id,
        LemmaWalletBinding.binding_status == "active",
    ).first()
    if binding:
        return True
    verification = db.query(IsHumanVerification).filter(
        IsHumanVerification.wallet_id == wallet_id,
    ).first()
    return verification is not None


def register_wallet_signing_key(
    *,
    wallet_id: str,
    pubkey_b64: str,
    signature_b64: str,
    device_id: str = "legacy",
    device_name: str = "",
    enrollment_grant: str = "",
    allow_first_device_bootstrap: bool = False,
) -> Result:
    """Register a wallet key after self-signature and enrollment authority.

    New device keys require a one-time enrollment grant (transfer or recovery)
    unless ``allow_first_device_bootstrap`` is set by the verified first-device
    WebAuthn enrollment ceremony. Idempotent re-registration of the same
    device key does not consume a grant.
    """
    from api.database import SessionLocal, WalletSigningKey

    wallet_id = (wallet_id or "").strip()
    device_id = (device_id or "legacy").strip() or "legacy"
    pubkey_b64 = (pubkey_b64 or "").strip()
    signature_b64 = (signature_b64 or "").strip()

    if not wallet_id or not pubkey_b64 or not signature_b64:
        return Result(False, "wallet_assertion_malformed", "wallet_id, pubkey, and signature required")

    try:
        pubkey_bytes = b64url_decode(pubkey_b64)
        signature_bytes = b64url_decode(signature_b64)
        public_key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    except Exception:
        return Result(False, "wallet_assertion_malformed", "invalid pubkey or signature encoding")

    payload = build_register_payload(wallet_id=wallet_id, pubkey_b64=pubkey_b64)
    if not verify_message(public_key, payload, signature_bytes):
        return Result(False, "wallet_assertion_invalid_signature", "registration self-signature invalid")

    db = SessionLocal()
    try:
        existing = db.query(WalletSigningKey).filter_by(
            wallet_id=wallet_id,
            device_id=device_id,
        ).first()
        if existing:
            if existing.revoked_at:
                return Result(False, "wallet_pubkey_mismatch", "wallet signing key revoked")
            if bytes(existing.pubkey) == pubkey_bytes:
                existing.last_used_at = datetime.utcnow()
                if device_name:
                    existing.device_name = device_name
                _ensure_provisional_person_after_register(db, wallet_id)
                db.commit()
                return Result(True)
            return Result(
                False,
                "wallet_pubkey_mismatch",
                "device already registered with a different public key",
            )

        other_active = db.query(WalletSigningKey).filter(
            WalletSigningKey.wallet_id == wallet_id,
            WalletSigningKey.revoked_at.is_(None),
            WalletSigningKey.device_id != device_id,
        ).first()
        established_identity = _wallet_has_established_identity(db, wallet_id)
        first_unbound_device = other_active is None and not established_identity
        if not allow_first_device_bootstrap:
            if first_unbound_device and not str(enrollment_grant or "").strip():
                return Result(
                    False,
                    "first_device_webauthn_enrollment_required",
                    "first-device enrollment requires verified WebAuthn registration",
                )
            grant_result = _consume_device_enrollment_grant(
                grant=enrollment_grant,
                wallet_id=wallet_id,
            )
            if not grant_result.ok:
                return grant_result

        db.add(
            WalletSigningKey(
                wallet_id=wallet_id,
                device_id=device_id,
                pubkey=pubkey_bytes,
                algorithm="ed25519",
                device_name=(device_name or None),
                created_at=datetime.utcnow(),
                last_used_at=datetime.utcnow(),
            )
        )
        _ensure_provisional_person_after_register(db, wallet_id)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            winner = db.query(WalletSigningKey).filter_by(
                wallet_id=wallet_id,
                device_id=device_id,
            ).first()
            if winner and not winner.revoked_at and bytes(winner.pubkey) == pubkey_bytes:
                winner.last_used_at = datetime.utcnow()
                _ensure_provisional_person_after_register(db, wallet_id)
                db.commit()
                return Result(True)
            if winner and winner.revoked_at:
                return Result(False, "wallet_pubkey_mismatch", "wallet signing key revoked")
            return Result(
                False,
                "wallet_pubkey_mismatch",
                "device already registered with a different public key",
            )
        return Result(True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def bind_wallet_passkey(
    *,
    wallet_id: str,
    device_id: str,
    credential_id: str,
    public_key: str,
    attestation_format: str | None = None,
    device_name: str | None = None,
    sign_count: int = 0,
) -> Result:
    """Persist a wallet-bound WebAuthn credential after ceremony verification."""
    from api.database import SessionLocal, WalletPasskey

    wallet_id = (wallet_id or "").strip()
    device_id = (device_id or "").strip()
    credential_id = (credential_id or "").strip()
    public_key = (public_key or "").strip()
    if not wallet_id or not device_id or not credential_id or not public_key:
        return Result(False, "wallet_passkey_malformed", "wallet_id, device_id, credential_id, and public_key required")

    db = SessionLocal()
    try:
        existing = db.query(WalletPasskey).filter_by(credential_id=credential_id).first()
        if existing and existing.revoked_at:
            return Result(False, "passkey_revoked", "passkey revoked")
        if existing:
            if str(existing.wallet_id or "") != wallet_id or str(existing.device_id or "") != device_id:
                return Result(False, "passkey_wallet_mismatch", "passkey already bound to another wallet device")
            existing.public_key = public_key
            existing.sign_count = int(sign_count or existing.sign_count or 0)
            existing.last_used_at = datetime.utcnow()
            if attestation_format:
                existing.attestation_format = attestation_format
            if device_name:
                existing.device_name = device_name
        else:
            db.add(
                WalletPasskey(
                    wallet_id=wallet_id,
                    device_id=device_id,
                    credential_id=credential_id,
                    public_key=public_key,
                    sign_count=int(sign_count or 0),
                    attestation_format=attestation_format,
                    device_name=device_name,
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow(),
                )
            )
        db.commit()
        return Result(True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def revoke_wallet_device(
    *,
    wallet_id: str,
    device_id: str,
    revoke_passkeys: bool = True,
) -> Result:
    from api.database import SessionLocal, WalletPasskey, WalletSigningKey

    wallet_id = (wallet_id or "").strip()
    device_id = (device_id or "").strip()
    if not wallet_id or not device_id:
        return Result(False, "wallet_assertion_malformed", "wallet_id and device_id required")

    db = SessionLocal()
    try:
        row = db.query(WalletSigningKey).filter_by(
            wallet_id=wallet_id,
            device_id=device_id,
        ).first()
        if not row or row.revoked_at:
            return Result(False, "device_not_found", "device signing key not found")
        row.revoked_at = datetime.utcnow()
        if revoke_passkeys:
            for passkey in db.query(WalletPasskey).filter_by(
                wallet_id=wallet_id,
                device_id=device_id,
            ).all():
                if not passkey.revoked_at:
                    passkey.revoked_at = datetime.utcnow()
        db.commit()
        return Result(True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def count_active_wallet_devices(wallet_id: str, *, exclude_device_id: str = "") -> int:
    from api.database import SessionLocal, WalletSigningKey

    db = SessionLocal()
    try:
        rows = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id).all()
        active = [row for row in rows if not getattr(row, "revoked_at", None)]
        exclude_device_id = (exclude_device_id or "").strip()
        if exclude_device_id:
            active = [row for row in active if str(row.device_id or "") != exclude_device_id]
        return len(active)
    finally:
        db.close()


def _parse_assertion(body: dict) -> tuple[Result, str, str, dict]:
    assertion = body.get("wallet_assertion")
    if not isinstance(assertion, dict):
        return Result(False, "wallet_assertion_required", "wallet_assertion object required"), "", "", {}
    nonce = str(assertion.get("nonce") or "").strip()
    signature_b64 = str(assertion.get("signature") or "").strip()
    if not nonce or not signature_b64:
        return Result(False, "wallet_assertion_malformed", "nonce and signature required"), "", "", {}
    return Result(True), nonce, signature_b64, assertion


def verify_assertion_from_body(
    body: dict,
    *,
    wallet_id: str,
    field_names: list[str],
) -> tuple[Result, dict]:
    """Verify wallet_assertion; burn nonce on success."""
    parse_result, nonce, signature_b64, assertion = _parse_assertion(body or {})
    if not parse_result.ok:
        return parse_result, {}

    wallet_id = (wallet_id or str(body.get("wallet_id") or "")).strip()
    if not wallet_id:
        return Result(False, "wallet_assertion_malformed", "wallet_id required"), {}

    challenge_entry = redis_get(_challenge_key(nonce))
    if not challenge_entry:
        return Result(False, "wallet_assertion_nonce_unknown", "challenge nonce unknown or expired"), {}

    bound_wallet = str(challenge_entry.get("wallet_id") or "").strip()
    if bound_wallet and bound_wallet != wallet_id:
        return Result(False, "wallet_assertion_malformed", "wallet_id does not match challenge"), {}

    bound_device = str(challenge_entry.get("device_id") or "").strip()
    requested_device = str(body.get("device_id") or assertion.get("device_id") or "").strip()
    if bound_device and requested_device and bound_device != requested_device:
        return Result(False, "wallet_assertion_malformed", "device_id does not match challenge"), {}

    reg_result, pubkey_bytes, registered_device_id = _load_registered_pubkey(
        wallet_id,
        device_id=requested_device or bound_device,
    )
    if not reg_result.ok:
        return reg_result, {}

    # Wallet SDK buildWalletAssertion always appends device_id to the signed
    # field set. Mirror that here so derive/seed/start endpoints keep working
    # after the device-binding migration.
    effective_field_names = [
        str(name or "").strip() for name in (field_names or []) if str(name or "").strip()
    ]
    if "device_id" not in effective_field_names:
        effective_field_names.append("device_id")

    device_id_value = (
        requested_device
        or bound_device
        or str(registered_device_id or "").strip()
        or "legacy"
    )

    field_values = {}
    for name in effective_field_names:
        if name == "device_id":
            field_values[name] = device_id_value
            continue
        raw = body.get(name)
        field_values[name] = "" if raw is None else str(raw)

    payload = build_assertion_payload(
        wallet_id=wallet_id,
        nonce_b64=nonce,
        field_names=effective_field_names,
        field_values=field_values,
    )

    try:
        signature_bytes = b64url_decode(signature_b64)
        public_key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    except Exception:
        return Result(False, "wallet_assertion_malformed", "invalid signature encoding"), {}

    if not verify_message(public_key, payload, signature_bytes):
        return Result(False, "wallet_assertion_invalid_signature", "wallet assertion signature invalid"), {}

    if not redis_delete(_challenge_key(nonce)):
        return Result(False, "wallet_assertion_nonce_replay", "challenge nonce already used"), {}

    _touch_last_used(wallet_id, registered_device_id or requested_device or bound_device or "legacy")
    return Result(True), field_values


def _touch_last_used(wallet_id: str, device_id: str = "legacy") -> None:
    from api.database import SessionLocal, WalletSigningKey

    db = SessionLocal()
    try:
        row = db.query(WalletSigningKey).filter_by(
            wallet_id=wallet_id,
            device_id=(device_id or "legacy").strip() or "legacy",
        ).first()
        if row:
            row.last_used_at = datetime.utcnow()
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def assertion_error_response(result: Result) -> tuple:
    return (
        jsonify({
            "success": False,
            "error": result.error or "wallet_assertion_failed",
            "code": result.code or "wallet_assertion_failed",
        }),
        403,
    )
