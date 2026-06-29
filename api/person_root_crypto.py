"""AWS-KMS boundary for assigned-person root material."""

from __future__ import annotations

import hashlib
import hmac
import os

KMS_PREFIX = "kms1:"
_CONTEXT_DOMAIN = b"lemma.id/person-root-kms-context/v1"


def is_kms_person_root(value: object) -> bool:
    return isinstance(value, str) and value.startswith(KMS_PREFIX)


def _production() -> bool:
    from api.config import is_production

    return bool(is_production())


def _context_key() -> bytes:
    material = os.getenv("LEMMA_COLUMN_ENCRYPTION_KEY") or os.getenv("LEMMA_PERSON_ROOT_SALT_V1") or ""
    if not material:
        raise RuntimeError("person-root KMS context key unavailable")
    return hashlib.sha256(b"context-key\x00" + material.encode("utf-8")).digest()


def _context_id(person_id: str) -> str:
    if not person_id:
        raise ValueError("person_id required for person-root KMS context")
    return hmac.new(
        _context_key(),
        _CONTEXT_DOMAIN + b"\x00" + person_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def encrypt_person_root(person_id: str, person_root_hex: str) -> str:
    """Encrypt a 32-byte person root under the configured AWS KMS key."""
    raw = bytes.fromhex(person_root_hex)
    if len(raw) != 32:
        raise ValueError("person root must be 32 bytes")
    from api.kms_manager import get_kms_manager

    kms = get_kms_manager()
    if not kms.is_enabled():
        if _production():
            raise RuntimeError("production person-root encryption requires AWS KMS")
        # Tests/local development retain the legacy encrypted-column envelope.
        from api.column_crypto import encrypt_column
        return encrypt_column(person_root_hex)
    ciphertext, _key_id = kms.encrypt_identity_secret(
        raw,
        key_type="ishuman_person_root",
        purpose="ppid_derivation",
        context_id=_context_id(person_id),
        version="1",
    )
    return KMS_PREFIX + ciphertext


def decrypt_person_root(person_id: str, stored_value: str) -> str:
    """Decrypt a person root; production rejects non-KMS legacy envelopes."""
    if is_kms_person_root(stored_value):
        from api.kms_manager import get_kms_manager

        kms = get_kms_manager()
        if not kms.is_enabled():
            raise RuntimeError("AWS KMS unavailable for person-root decryption")
        raw = kms.decrypt_identity_secret(
            stored_value[len(KMS_PREFIX):],
            key_type="ishuman_person_root",
            purpose="ppid_derivation",
            context_id=_context_id(person_id),
            version="1",
        )
        if len(raw) != 32:
            raise ValueError("decrypted person root must be 32 bytes")
        return raw.hex()

    if _production():
        raise RuntimeError("production person root is not KMS encrypted")
    from api.column_crypto import decrypt_column
    return decrypt_column(stored_value)
