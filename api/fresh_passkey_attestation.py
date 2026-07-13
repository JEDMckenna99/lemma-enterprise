"""Issuer-signed fresh-passkey action attestations (see CANONICAL_MESSAGES.md §10)."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

ACTION_COMMITMENT_PREFIX = "lemma:action-commitment:v1"
FRESH_PASSKEY_PREFIX = "lemma:fresh-passkey-attestation:v1"
FRESH_PASSKEY_SCHEMA = "fresh_passkey_attestation.v1"
FRESH_PASSKEY_TTL_SECONDS = 120
FRESH_PASSKEY_CHALLENGE_TTL_SECONDS = 120


def build_action_commitment(
    *,
    server_nonce: str,
    site_id: str,
    action: str,
    method: str = "POST",
    path: str = "",
    body_hash: str = "",
) -> str:
    """Opaque site-local action binding — lemma.id never receives action details."""
    lines = [
        ACTION_COMMITMENT_PREFIX,
        str(server_nonce or "").strip(),
        str(site_id or "").strip(),
        str(action or "").strip(),
        str(method or "POST").strip().upper(),
        str(path or "").strip(),
        str(body_hash or "").strip().lower(),
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def build_fresh_passkey_canonical_message(artifact: dict) -> bytes:
    """Byte-exact fresh-passkey signing input."""
    lines = [
        FRESH_PASSKEY_PREFIX,
        str(artifact.get("schema") or FRESH_PASSKEY_SCHEMA).strip(),
        str(artifact.get("site_id") or "").strip(),
        str(artifact.get("credential_id") or "").strip(),
        str(artifact.get("subject") or "").strip(),
        str(artifact.get("action_commitment") or "").strip().lower(),
        str(artifact.get("attestation_id") or "").strip(),
        str(int(artifact.get("issued_at_unix") or 0)),
        str(int(artifact.get("expires_at_unix") or 0)),
    ]
    return "\n".join(lines).encode("utf-8")


def _sign_fresh_passkey_digest(digest: bytes) -> tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from api.ishuman import _get_ishuman_issuer

    issuer = _get_ishuman_issuer()
    seed = bytes(issuer.signing_key_bytes())
    if len(seed) != 32:
        raise ValueError("issuer signing key seed must be 32 bytes")
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    signature_hex = sk.sign(digest).hex()
    return signature_hex, issuer.get_did()


def sign_fresh_passkey_attestation(artifact: dict) -> dict:
    """Attach issuer + Ed25519 proof to a fresh-passkey attestation dict."""
    message = build_fresh_passkey_canonical_message(artifact)
    digest = hashlib.sha256(message).digest()
    signature_hex, issuer_did = _sign_fresh_passkey_digest(digest)
    signed = dict(artifact)
    signed["issuer"] = issuer_did
    signed["proof"] = {"signatureValueWeb": signature_hex}
    return signed


def verify_fresh_passkey_attestation(
    attestation: dict,
    *,
    site_id: str,
    credential_id: str,
    subject: str,
    action_commitment: str,
    trusted_issuer_pubkeys: list[str],
    now_unix: Optional[int] = None,
    max_age_seconds: int = FRESH_PASSKEY_TTL_SECONDS,
) -> tuple[bool, str]:
    """Verify a fresh-passkey attestation against trusted Lemma issuer keys."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(attestation, dict):
        return False, "fresh_passkey_missing"
    if str(attestation.get("schema") or "") != FRESH_PASSKEY_SCHEMA:
        return False, "fresh_passkey_schema_mismatch"
    if str(attestation.get("site_id") or "").strip() != str(site_id or "").strip():
        return False, "fresh_passkey_site_mismatch"
    if str(attestation.get("credential_id") or "").strip() != str(credential_id or "").strip():
        return False, "fresh_passkey_credential_mismatch"
    if str(attestation.get("subject") or "").strip() != str(subject or "").strip():
        return False, "fresh_passkey_subject_mismatch"
    expected_commitment = str(action_commitment or "").strip().lower()
    if expected_commitment and str(attestation.get("action_commitment") or "").strip().lower() != expected_commitment:
        return False, "fresh_passkey_commitment_mismatch"

    now = int(now_unix if now_unix is not None else time.time())
    try:
        expires_at = int(attestation.get("expires_at_unix") or 0)
        issued_at = int(attestation.get("issued_at_unix") or 0)
    except (TypeError, ValueError):
        return False, "fresh_passkey_timestamps_invalid"
    if not issued_at or not expires_at or expires_at < now:
        return False, "fresh_passkey_expired"
    if issued_at > now + 300:
        return False, "fresh_passkey_issued_in_future"
    if now - issued_at > max(1, int(max_age_seconds)):
        return False, "fresh_passkey_too_old"

    proof = attestation.get("proof") or {}
    signature_hex = str(proof.get("signatureValueWeb") or "").strip()
    if not signature_hex:
        return False, "fresh_passkey_signature_missing"
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False, "fresh_passkey_signature_malformed"

    unsigned = {
        key: attestation[key]
        for key in (
            "schema",
            "attestation_id",
            "site_id",
            "credential_id",
            "subject",
            "action_commitment",
            "issued_at_unix",
            "expires_at_unix",
        )
        if key in attestation
    }
    digest = hashlib.sha256(build_fresh_passkey_canonical_message(unsigned)).digest()
    verified = False
    for pubkey_hex in trusted_issuer_pubkeys:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, digest)
            verified = True
            break
        except (InvalidSignature, ValueError):
            continue
    if not verified:
        return False, "fresh_passkey_invalid_signature"
    return True, "valid"


def issue_fresh_passkey_attestation(
    *,
    site_id: str,
    credential_id: str,
    subject: str,
    action_commitment: str,
) -> dict:
    """Create a short-lived issuer-signed fresh-passkey attestation."""
    now_unix = int(time.time())
    unsigned = {
        "schema": FRESH_PASSKEY_SCHEMA,
        "attestation_id": f"fpa_{secrets.token_urlsafe(16)}",
        "site_id": str(site_id or "").strip(),
        "credential_id": str(credential_id or "").strip(),
        "subject": str(subject or "").strip(),
        "action_commitment": str(action_commitment or "").strip().lower(),
        "issued_at_unix": now_unix,
        "expires_at_unix": now_unix + FRESH_PASSKEY_TTL_SECONDS,
    }
    return sign_fresh_passkey_attestation(unsigned)


def _challenge_key(challenge_key: str) -> str:
    return f"fresh_passkey:challenge:{challenge_key}"


def store_fresh_passkey_challenge(challenge_key: str, payload: dict) -> None:
    from auth.redis_store import store as redis_store

    redis_store(
        _challenge_key(challenge_key),
        payload,
        ttl_seconds=FRESH_PASSKEY_CHALLENGE_TTL_SECONDS,
    )


def get_fresh_passkey_challenge(challenge_key: str) -> Optional[dict]:
    from auth.redis_store import get as redis_get

    return redis_get(_challenge_key(challenge_key))


def delete_fresh_passkey_challenge(challenge_key: str) -> None:
    from auth.redis_store import delete as redis_delete

    redis_delete(_challenge_key(challenge_key))


def _decode_public_key(raw: str) -> bytes:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("missing public key")
    try:
        return base64.urlsafe_b64decode(text + ("=" * (-len(text) % 4)))
    except Exception:
        return bytes.fromhex(text)


def verify_wallet_webauthn_assertion(
    *,
    credential: dict,
    expected_challenge: bytes,
    rp_id: str,
    origin: str,
    public_key_b64: str,
    sign_count: int = 0,
) -> tuple[bool, str, int]:
    """Verify a WebAuthn assertion against a stored wallet/device passkey."""
    from webauthn import verify_authentication_response

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=_decode_public_key(public_key_b64),
            credential_current_sign_count=int(sign_count or 0),
            require_user_verification=True,
        )
        return True, "valid", int(verification.new_sign_count)
    except Exception as exc:
        logger.warning("Fresh passkey WebAuthn verify failed: %s", exc)
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)


def lookup_wallet_passkey_public_key(credential_id_b64: str) -> tuple[Optional[str], int]:
    """Resolve wallet passkey public key + sign count from server registry."""
    from api.database import SessionLocal, WalletPasskey

    db = SessionLocal()
    try:
        row = (
            db.query(WalletPasskey)
            .filter_by(credential_id=str(credential_id_b64 or "").strip())
            .filter(WalletPasskey.revoked_at.is_(None))
            .first()
        )
        if not row or not row.public_key:
            return None, 0
        return str(row.public_key), int(row.sign_count or 0)
    finally:
        db.close()


def update_wallet_passkey_sign_count(credential_id_b64: str, new_sign_count: int) -> None:
    from api.database import SessionLocal, WalletPasskey

    db = SessionLocal()
    try:
        row = db.query(WalletPasskey).filter_by(credential_id=str(credential_id_b64 or "").strip()).first()
        if row:
            row.sign_count = int(new_sign_count)
            row.last_used_at = datetime.utcnow()
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
