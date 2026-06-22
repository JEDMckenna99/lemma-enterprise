"""At-rest encryption for sensitive identity-linkage columns.

Some columns store derived identifiers that, on their own, let an attacker
reconstruct the cross-site PPID graph. The sharpest example is
``LemmaPerson.person_root_hash``: it is the direct input to canonical PPID
derivation, so a plaintext copy enables enumeration of every site PPID for a
person *with no additional secret*. A leaked DB backup or read-only SQL access
must not yield these values in the clear.

This module provides minimal, additive application-level AES-GCM encryption for
such columns. The key lives OUTSIDE the database (env / KMS-provisioned secret),
so a DB-only breach yields ciphertext.

Design notes / invariants:

* Only apply to columns that are NEVER used as equality-lookup keys. Randomized
  AES-GCM breaks ``WHERE col = ?`` queries; columns that need lookups (e.g.
  ``LemmaDocumentRoot.document_root_hash``, which is the dedup key and is itself
  already a keyed HMAC of PII) are intentionally left as-is.
* Legacy plaintext values pass through unchanged on read, so this is migration
  safe: existing rows keep working and encrypt lazily on next write (a backfill
  script upgrades them in place).
* Envelope format (str): ``lc1:<b64url iv>:<b64url ciphertext+tag>``.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import logging
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

_PREFIX = "lc1:"
_HKDF_INFO = b"lemma.id/column-encryption/v1"


def _derive_column_key(material: str) -> bytes:
    """Domain-separated column key from secret material (>= 32 bytes)."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(material.encode("utf-8"))


@functools.lru_cache(maxsize=1)
def _column_key() -> bytes:
    """Return the 32-byte at-rest column key, or b"" when none is configured.

    Preference order:
      1. ``LEMMA_COLUMN_ENCRYPTION_KEY`` (explicit, KMS-provisioned).
      2. HKDF of the always-required ``LEMMA_PERSON_ROOT_SALT_V1`` so the feature
         works without new ops config. The HKDF ``info`` keeps this key domain
         separated from the salt's primary derivation use.

    Both paths use the same HKDF derivation so operators may set
    ``LEMMA_COLUMN_ENCRYPTION_KEY`` to a dedicated secret, or mirror
    ``LEMMA_PERSON_ROOT_SALT_V1`` for the same effective key bytes.

    When neither is available (e.g. a minimal dev shell) an empty key is
    returned and callers store plaintext -- the legacy behaviour.
    """
    explicit = os.environ.get("LEMMA_COLUMN_ENCRYPTION_KEY")
    if explicit and len(explicit) >= 32:
        return _derive_column_key(explicit)

    base = ""
    try:
        from api.config import get_person_root_salt

        base = get_person_root_salt() or ""
    except Exception:
        base = os.environ.get("LEMMA_PERSON_ROOT_SALT_V1", "") or ""

    if not base:
        return b""

    return _derive_column_key(base)


def column_encryption_active() -> bool:
    """True when at-rest column encryption key material is configured."""
    return bool(_column_key())


def require_column_encryption_in_production() -> None:
    """Fail fast in production when identity columns would store plaintext."""
    try:
        from api.config import is_production

        if is_production() and not column_encryption_active():
            raise RuntimeError(
                "CRITICAL: production requires LEMMA_COLUMN_ENCRYPTION_KEY or "
                "LEMMA_PERSON_ROOT_SALT_V1 for at-rest identity column encryption"
            )
    except RuntimeError:
        raise
    except Exception:
        pass


def reset_key_cache() -> None:
    """Clear the cached key (tests that mutate secret env vars)."""
    _column_key.cache_clear()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_column(plaintext):
    """Encrypt a column value for storage.

    Returns ``None`` unchanged, already-encrypted values unchanged, and plaintext
    unchanged when no key is configured (dev/test degrade).
    """
    if plaintext is None:
        return None
    if is_encrypted(plaintext):
        return plaintext
    key = _column_key()
    if not key:
        return plaintext
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, str(plaintext).encode("utf-8"), None)
    return f"{_PREFIX}{_b64e(iv)}:{_b64e(ciphertext)}"


def decrypt_column(value):
    """Decrypt a stored column value.

    Legacy plaintext (no envelope prefix) and ``None`` pass through unchanged. On
    any decryption failure the raw value is returned so the caller can surface a
    clear downstream error (e.g. ``bytes.fromhex`` raising) rather than silently
    corrupting data.
    """
    if value is None or not is_encrypted(value):
        return value
    key = _column_key()
    if not key:
        return value
    try:
        _, iv_b64, ct_b64 = value.split(":", 2)
        plaintext = AESGCM(key).decrypt(_b64d(iv_b64), _b64d(ct_b64), None)
        return plaintext.decode("utf-8")
    except Exception:
        logger.error("column decryption failed; returning raw envelope")
        return value
