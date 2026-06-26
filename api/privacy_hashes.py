"""Keyed hashes for provider identifiers that should not persist raw."""

from __future__ import annotations

import functools
import hashlib
import hmac
import os

_HMAC_PREFIX = "ph1:"
_HMAC_DOMAIN = b"lemma.id/provider-id-hash/v1"


@functools.lru_cache(maxsize=1)
def _provider_hash_key() -> bytes:
    """Return secret material for provider-ID HMACs.

    Preference order keeps deployments explicit while preserving local/test
    operability with existing out-of-database identity secrets.
    """
    explicit = os.environ.get("LEMMA_PROVIDER_ID_HASH_KEY")
    if explicit and len(explicit) >= 32:
        return explicit.encode("utf-8")

    column_key = os.environ.get("LEMMA_COLUMN_ENCRYPTION_KEY")
    if column_key and len(column_key) >= 32:
        return column_key.encode("utf-8")

    try:
        from api.config import get_person_root_salt

        salt = get_person_root_salt() or ""
    except Exception:
        salt = os.environ.get("LEMMA_PERSON_ROOT_SALT_V1", "") or ""

    if salt and len(salt) >= 32:
        return salt.encode("utf-8")

    return b""


def reset_provider_hash_key_cache() -> None:
    _provider_hash_key.cache_clear()


def hash_provider_identifier(provider: str, value: str | None, *, label: str = "session") -> str | None:
    """HMAC a provider identifier for local audit correlation."""
    raw = (value or "").strip()
    if not raw:
        return None
    key = _provider_hash_key()
    if not key:
        return None
    provider_norm = (provider or "unknown").strip().lower()
    label_norm = (label or "id").strip().lower()
    msg = b"\x00".join(
        [
            _HMAC_DOMAIN,
            provider_norm.encode("utf-8"),
            label_norm.encode("utf-8"),
            raw.encode("utf-8"),
        ]
    )
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"{_HMAC_PREFIX}{digest}"
