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
    """Opaque site-local action binding, lemma.id never receives action details."""
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


def build_fresh_passkey_canonical_message(artifact: dict, *, include_issuer: bool = True) -> bytes:
    """Byte-exact fresh-passkey signing input.

    Wave 4: ``issuer`` is bound into the signed bytes so a foreign trusted
    issuer cannot forge platform fresh-passkey artifacts.
    """
    lines = [
        FRESH_PASSKEY_PREFIX,
        str(artifact.get("schema") or FRESH_PASSKEY_SCHEMA).strip(),
    ]
    if include_issuer:
        lines.append(str(artifact.get("issuer") or "").strip())
    lines.extend(
        [
            str(artifact.get("site_id") or "").strip(),
            str(artifact.get("credential_id") or "").strip(),
            str(artifact.get("subject") or "").strip(),
            str(artifact.get("action_commitment") or "").strip().lower(),
            str(artifact.get("attestation_id") or "").strip(),
            str(int(artifact.get("issued_at_unix") or 0)),
            str(int(artifact.get("expires_at_unix") or 0)),
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _artifact_signing_issuer_did() -> str:
    from api.federated_signer import get_federated_signer, use_remote_federated_signer
    from api.ishuman import _get_ishuman_issuer

    if use_remote_federated_signer():
        return str(get_federated_signer().get_did() or "").strip()
    return str(_get_ishuman_issuer().get_did() or "").strip()


def _sign_fresh_passkey_digest(digest: bytes) -> tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from api.federated_signer import get_federated_signer, use_remote_federated_signer
    from api.ishuman import _get_ishuman_issuer

    if use_remote_federated_signer():
        signer = get_federated_signer()
        return signer.sign_digest_hex(digest), signer.get_did()

    issuer = _get_ishuman_issuer()
    seed = bytes(issuer.signing_key_bytes())
    if len(seed) != 32:
        raise ValueError("issuer signing key seed must be 32 bytes")
    signature_hex = Ed25519PrivateKey.from_private_bytes(seed).sign(digest).hex()
    return signature_hex, issuer.get_did()


def sign_fresh_passkey_attestation(artifact: dict) -> dict:
    """Attach issuer + Ed25519 proof to a fresh-passkey attestation dict."""
    signed = dict(artifact)
    signed["issuer"] = _artifact_signing_issuer_did()
    message = build_fresh_passkey_canonical_message(signed, include_issuer=True)
    digest = hashlib.sha256(message).digest()
    signature_hex, issuer_did = _sign_fresh_passkey_digest(digest)
    signed["issuer"] = issuer_did
    signed["proof"] = {"signatureValueWeb": signature_hex}
    return signed


def _pubkeys_for_issuer(
    *,
    issuer_did: str,
    trusted_issuer_pubkeys: Optional[list[str]] = None,
    trusted_issuers: Optional[dict] = None,
) -> list[str]:
    """Resolve pubkeys for one issuer DID only (never flatten all issuers)."""
    did = str(issuer_did or "").strip()
    if not did:
        return []
    if trusted_issuers is not None:
        entry = trusted_issuers.get(did) if hasattr(trusted_issuers, "get") else None
        if entry is None:
            return []
        if hasattr(entry, "pubkeys_hex"):
            return sorted(str(p).lower() for p in entry.pubkeys_hex)
        if isinstance(entry, (set, list, tuple)):
            return sorted(str(p).lower() for p in entry)
        return []
    return [str(p).strip().lower() for p in (trusted_issuer_pubkeys or []) if str(p).strip()]


def verify_fresh_passkey_attestation(
    attestation: dict,
    *,
    site_id: str,
    credential_id: str,
    subject: str,
    action_commitment: str,
    trusted_issuer_pubkeys: Optional[list[str]] = None,
    trusted_issuers: Optional[dict] = None,
    expected_issuer_did: Optional[str] = None,
    now_unix: Optional[int] = None,
    max_age_seconds: int = FRESH_PASSKEY_TTL_SECONDS,
) -> tuple[bool, str]:
    """Verify a fresh-passkey attestation against the claimed issuer's keys only."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(attestation, dict):
        return False, "fresh_passkey_missing"
    if str(attestation.get("schema") or "") != FRESH_PASSKEY_SCHEMA:
        return False, "fresh_passkey_schema_mismatch"
    issuer_did = str(attestation.get("issuer") or "").strip()
    if not issuer_did:
        return False, "fresh_passkey_issuer_missing"
    if expected_issuer_did and issuer_did != str(expected_issuer_did).strip():
        return False, "fresh_passkey_issuer_mismatch"
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
            "issuer",
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
    pubkeys = _pubkeys_for_issuer(
        issuer_did=issuer_did,
        trusted_issuer_pubkeys=trusted_issuer_pubkeys,
        trusted_issuers=trusted_issuers,
    )
    if not pubkeys:
        return False, "fresh_passkey_untrusted_issuer"

    digests = [
        hashlib.sha256(build_fresh_passkey_canonical_message(unsigned, include_issuer=True)).digest(),
        # Legacy grace: pre-Wave-4 artifacts omitted issuer from the signed bytes.
        hashlib.sha256(build_fresh_passkey_canonical_message(unsigned, include_issuer=False)).digest(),
    ]
    for digest in digests:
        for pubkey_hex in pubkeys:
            try:
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex)).verify(signature, digest)
                return True, "valid"
            except (InvalidSignature, ValueError):
                continue
    return False, "fresh_passkey_invalid_signature"


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


def _is_spki_public_key(raw: bytes) -> bool:
    """Browser getPublicKey() returns DER SubjectPublicKeyInfo (starts with 0x30)."""
    return bool(raw) and raw[0] == 0x30


def allowed_fresh_passkey_origins() -> list[str]:
    """Origins accepted for wallet fresh-passkey ceremonies."""
    from api.passkey_auth import ALLOWED_AUTH_ORIGINS, EXPECTED_ORIGIN, ORIGIN

    origins: list[str] = []
    for value in (ORIGIN, EXPECTED_ORIGIN):
        text = str(value or "").strip()
        if text and text not in origins:
            origins.append(text)
    for value in sorted(ALLOWED_AUTH_ORIGINS):
        text = str(value or "").strip()
        if text and text not in origins:
            origins.append(text)
    return origins


def extract_cose_public_key_b64(attestation_object_b64: str) -> str:
    """Extract COSE credential public key from a WebAuthn attestation object."""
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.parse_attestation_object import parse_attestation_object
    from webauthn.helpers.parse_authenticator_data import parse_authenticator_data

    raw = _decode_public_key(str(attestation_object_b64 or "").strip())
    att_obj = parse_attestation_object(raw)
    auth_data = att_obj.auth_data
    if isinstance(auth_data, (bytes, bytearray)):
        auth_data = parse_authenticator_data(bytes(auth_data))
    if not auth_data.attested_credential_data:
        raise ValueError("no_attested_credential_data")
    return bytes_to_base64url(auth_data.attested_credential_data.credential_public_key)


def _normalize_expected_origins(origin: str | list[str] | None) -> list[str]:
    if isinstance(origin, list):
        values = origin
    elif origin:
        values = [origin]
    else:
        values = []
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    if not normalized:
        normalized = allowed_fresh_passkey_origins()
    return normalized


def _sign_count_replay_detected(new_sign_count: int, current_sign_count: int) -> bool:
    """Mirror pywebauthn: zero counters mean the authenticator omits a counter."""
    current = int(current_sign_count or 0)
    new = int(new_sign_count or 0)
    return (new > 0 or current > 0) and new <= current


def _verify_spki_wallet_webauthn_assertion(
    *,
    credential: dict,
    expected_challenge: bytes,
    rp_id: str,
    expected_origins: list[str],
    public_key_spki: bytes,
    sign_count: int = 0,
) -> tuple[bool, str, int]:
    """Verify assertions stored against browser SPKI exports (legacy wallet rows)."""
    import hashlib
    import json

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.parse_authenticator_data import parse_authenticator_data

    response = credential.get("response") if isinstance(credential, dict) else None
    if not isinstance(response, dict):
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)

    client_data_json = response.get("clientDataJSON")
    authenticator_data_b64 = response.get("authenticatorData")
    signature_b64 = response.get("signature")
    if not client_data_json or not authenticator_data_b64 or not signature_b64:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)

    client_data = json.loads(base64url_to_bytes(client_data_json))
    if client_data.get("type") != "webauthn.get":
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)
    challenge = base64url_to_bytes(client_data.get("challenge") or "")
    if challenge != expected_challenge:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)
    origin = str(client_data.get("origin") or "").strip()
    if origin not in expected_origins:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)

    auth_data = parse_authenticator_data(base64url_to_bytes(authenticator_data_b64))
    if hashlib.sha256(rp_id.encode("utf-8")).digest() != auth_data.rp_id_hash:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)
    if not auth_data.flags.up:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)
    if not auth_data.flags.uv:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)

    new_sign_count = int(auth_data.sign_count or 0)
    if _sign_count_replay_detected(new_sign_count, sign_count):
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)

    client_data_hash = hashlib.sha256(base64url_to_bytes(client_data_json)).digest()
    signed_data = base64url_to_bytes(authenticator_data_b64) + client_data_hash
    signature = base64url_to_bytes(signature_b64)
    public_key = load_der_public_key(public_key_spki)
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        public_key.verify(signature, signed_data, ec.ECDSA(hashes.SHA256()))
    elif isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(signature, signed_data, padding.PKCS1v15(), hashes.SHA256())
    else:
        return False, "fresh_passkey_webauthn_invalid", int(sign_count or 0)
    return True, "valid", new_sign_count


def _verify_cose_wallet_webauthn_assertion(
    *,
    credential: dict,
    expected_challenge: bytes,
    rp_id: str,
    expected_origins: list[str],
    public_key_cose: bytes,
    sign_count: int = 0,
) -> tuple[bool, str, int]:
    """Verify assertions against COSE-encoded wallet passkey material."""
    from webauthn import verify_authentication_response
    from webauthn.helpers import parse_authentication_credential_json

    parsed_credential = parse_authentication_credential_json(credential)
    verification = verify_authentication_response(
        credential=parsed_credential,
        expected_challenge=expected_challenge,
        expected_rp_id=rp_id,
        expected_origin=expected_origins,
        credential_public_key=public_key_cose,
        credential_current_sign_count=int(sign_count or 0),
        require_user_verification=True,
    )
    return True, "valid", int(verification.new_sign_count)


def verify_wallet_webauthn_assertion(
    *,
    credential: dict,
    expected_challenge: bytes,
    rp_id: str,
    origin: str | list[str],
    public_key_b64: str,
    sign_count: int = 0,
) -> tuple[bool, str, int]:
    """Verify a WebAuthn assertion against a stored wallet/device passkey."""
    expected_origins = _normalize_expected_origins(origin)
    public_key_raw = _decode_public_key(public_key_b64)
    failures: list[str] = []

    if not _is_spki_public_key(public_key_raw):
        try:
            return _verify_cose_wallet_webauthn_assertion(
                credential=credential,
                expected_challenge=expected_challenge,
                rp_id=rp_id,
                expected_origins=expected_origins,
                public_key_cose=public_key_raw,
                sign_count=sign_count,
            )
        except Exception as exc:
            failures.append(f"cose:{exc}")
            logger.warning("Fresh passkey COSE WebAuthn verify failed: %s", exc)

    if _is_spki_public_key(public_key_raw):
        try:
            return _verify_spki_wallet_webauthn_assertion(
                credential=credential,
                expected_challenge=expected_challenge,
                rp_id=rp_id,
                expected_origins=expected_origins,
                public_key_spki=public_key_raw,
                sign_count=sign_count,
            )
        except Exception as exc:
            failures.append(f"spki:{exc}")
            logger.warning("Fresh passkey SPKI WebAuthn verify failed: %s", exc)

    if failures:
        logger.warning("Fresh passkey WebAuthn verify exhausted: %s", "; ".join(failures))
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


def lookup_wallet_passkey_identity(credential_id_b64: str) -> tuple[Optional[str], Optional[str]]:
    """Return (wallet_id, device_id) for a registered passkey credential."""
    from api.database import SessionLocal, WalletPasskey

    db = SessionLocal()
    try:
        row = (
            db.query(WalletPasskey)
            .filter_by(credential_id=str(credential_id_b64 or "").strip())
            .filter(WalletPasskey.revoked_at.is_(None))
            .first()
        )
        if not row:
            return None, None
        return str(row.wallet_id or "").strip() or None, str(row.device_id or "").strip() or None
    finally:
        db.close()


def validate_fresh_passkey_identity_binding(
    *,
    passkey_credential_id: str,
    wallet_id: str,
    subject: str,
    site_id: str = "",
) -> tuple[bool, str]:
    """Ensure the passkey belongs to the claimed wallet/subject binding.

    Wave 4: site PPIDs are unlinkable via ``resolve_wallet_id_for_ppid``, so we
    derive the expected site PPID for the registered wallet (or passkey) and
    require an exact match. Lookup failures fail closed.
    """
    registered_wallet_id, _device_id = lookup_wallet_passkey_identity(passkey_credential_id)
    if not registered_wallet_id:
        return False, "passkey_not_registered_on_server"

    claimed_wallet = str(wallet_id or "").strip()
    if claimed_wallet and claimed_wallet != registered_wallet_id:
        return False, "wallet_id_mismatch"

    subject_value = str(subject or "").strip()
    if not subject_value.startswith("did:lemma:ppid_"):
        return False, "subject_ppid_required"

    site = str(site_id or "").strip()
    effective_wallet = claimed_wallet or registered_wallet_id

    try:
        from api.database import SessionLocal
        from api.ishuman import _derive_ppid_for_site, resolve_wallet_id_for_ppid
        from api.ppid import derive_ppid_from_passkey

        db = SessionLocal()
        try:
            resolved_wallet = resolve_wallet_id_for_ppid(db, subject_value)
            if resolved_wallet:
                if resolved_wallet != registered_wallet_id:
                    return False, "subject_wallet_mismatch"
                return True, "ok"

            if not site:
                return False, "site_id_required_for_subject_bind"

            try:
                expected = _derive_ppid_for_site(
                    rp_id=site,
                    wallet_id=effective_wallet,
                    db=db,
                    provisional=True,
                )
                if expected == subject_value:
                    return True, "ok"
            except Exception:
                # Fall through to passkey-derived PPID for pre-IDV wallets.
                pass

            passkey_ppid = derive_ppid_from_passkey(passkey_credential_id, site)
            if passkey_ppid == subject_value:
                return True, "ok"
            return False, "subject_ppid_mismatch"
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Fresh passkey subject binding check failed: %s", exc)
        return False, "subject_binding_failed"


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
