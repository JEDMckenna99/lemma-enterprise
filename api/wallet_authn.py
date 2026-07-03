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


def issue_wallet_challenge(*, wallet_id: str = "") -> dict:
    """Issue a short-lived nonce for wallet assertion signing."""
    nonce_bytes = secrets.token_bytes(32)
    nonce = b64url_encode(nonce_bytes)
    expires_at = (_utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS)).isoformat()
    redis_store(
        _challenge_key(nonce),
        {
            "wallet_id": (wallet_id or "").strip(),
            "created_at": _utcnow().isoformat(),
        },
        ttl_seconds=CHALLENGE_TTL_SECONDS,
    )
    return {"success": True, "nonce": nonce, "expires_at": expires_at}


def _load_registered_pubkey(wallet_id: str) -> tuple[Result, bytes | None]:
    from api.database import SessionLocal, WalletSigningKey

    if not wallet_id:
        return Result(False, "wallet_assertion_malformed", "wallet_id required"), None

    db = SessionLocal()
    try:
        row = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id).first()
        if not row or row.revoked_at:
            return Result(False, "wallet_not_registered", "wallet signing key not registered"), None
        if not row.pubkey:
            return Result(False, "wallet_not_registered", "wallet signing key missing"), None
        return Result(True), bytes(row.pubkey)
    finally:
        db.close()


def _ensure_provisional_person_after_register(db, wallet_id: str) -> None:
    """Create provisional assigned person_root when one-PPID assurance model is enabled."""
    from api.config import one_ppid_assurance_model_enabled

    if not one_ppid_assurance_model_enabled():
        return
    from api.identity_person import ensure_provisional_person_for_wallet

    ensure_provisional_person_for_wallet(db, wallet_id=wallet_id)


def register_wallet_signing_key(
    *,
    wallet_id: str,
    pubkey_b64: str,
    signature_b64: str,
) -> Result:
    """Register wallet Ed25519 public key after self-signature proof."""
    from api.database import SessionLocal, WalletSigningKey

    wallet_id = (wallet_id or "").strip()
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
        existing = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id).first()
        if existing:
            if existing.revoked_at:
                return Result(False, "wallet_pubkey_mismatch", "wallet signing key revoked")
            if bytes(existing.pubkey) == pubkey_bytes:
                existing.last_used_at = datetime.utcnow()
                _ensure_provisional_person_after_register(db, wallet_id)
                db.commit()
                return Result(True)
            return Result(
                False,
                "wallet_pubkey_mismatch",
                "wallet already registered with a different public key",
            )

        db.add(
            WalletSigningKey(
                wallet_id=wallet_id,
                pubkey=pubkey_bytes,
                algorithm="ed25519",
                created_at=datetime.utcnow(),
                last_used_at=datetime.utcnow(),
            )
        )
        _ensure_provisional_person_after_register(db, wallet_id)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent registration: the wallet page and the IDV popup can both
            # call register-signing-key in the same instant, so two requests pass
            # the "no existing row" check and race to INSERT the same wallet_id
            # primary key. Treat this as idempotent: re-read the winning row and
            # accept it when the public key matches (which it must, since the key
            # is deterministically derived from the wallet secret).
            db.rollback()
            winner = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id).first()
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
                "wallet already registered with a different public key",
            )
        return Result(True)
    except Exception:
        db.rollback()
        raise
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
    parse_result, nonce, signature_b64, _raw = _parse_assertion(body or {})
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

    reg_result, pubkey_bytes = _load_registered_pubkey(wallet_id)
    if not reg_result.ok:
        return reg_result, {}

    field_values = {}
    for name in field_names:
        key = str(name or "").strip()
        raw = body.get(key)
        field_values[key] = "" if raw is None else str(raw)

    payload = build_assertion_payload(
        wallet_id=wallet_id,
        nonce_b64=nonce,
        field_names=field_names,
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

    _touch_last_used(wallet_id)
    return Result(True), field_values


def _touch_last_used(wallet_id: str) -> None:
    from api.database import SessionLocal, WalletSigningKey

    db = SessionLocal()
    try:
        row = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id).first()
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
