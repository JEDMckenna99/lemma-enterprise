"""KMS/column encryption for site OAuth client secrets."""

from __future__ import annotations

import os
import secrets

KMS_PREFIX = "kms1:"
KEY_TYPE = "site_oauth_client"
PURPOSE = "oauth_client_secret"


def is_encrypted_oauth_client_secret(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value.startswith(KMS_PREFIX):
        return True
    from api.column_crypto import is_encrypted

    return is_encrypted(value)


def generate_oauth_client_secret() -> str:
    return secrets.token_urlsafe(32)


def _production() -> bool:
    from api.config import is_production

    return bool(is_production())


def encrypt_oauth_client_secret(site_id: str, secret: str) -> str:
    """Persist OAuth client secret as KMS or dev column envelope."""
    if not site_id:
        raise ValueError("site_id required for OAuth client secret encryption")
    if not secret:
        raise ValueError("OAuth client secret required")

    from api.kms_manager import get_kms_manager

    kms = get_kms_manager()
    if kms.is_enabled():
        ciphertext, _key_id = kms.encrypt_identity_secret(
            secret.encode("utf-8"),
            key_type=KEY_TYPE,
            purpose=PURPOSE,
            context_id=site_id,
            version="1",
        )
        return KMS_PREFIX + ciphertext

    if _production():
        raise RuntimeError("production OAuth client secrets require AWS KMS")

    from api.column_crypto import encrypt_column

    return encrypt_column(secret)


def decrypt_oauth_client_secret(site_id: str, stored_value: str) -> str:
    """Decrypt stored OAuth client secret for server-side OAuth flows."""
    if not stored_value:
        raise ValueError("stored OAuth client secret required")

    if stored_value.startswith(KMS_PREFIX):
        from api.kms_manager import get_kms_manager

        kms = get_kms_manager()
        if not kms.is_enabled():
            raise RuntimeError("AWS KMS unavailable for OAuth client secret decryption")
        raw = kms.decrypt_identity_secret(
            stored_value[len(KMS_PREFIX) :],
            key_type=KEY_TYPE,
            purpose=PURPOSE,
            context_id=site_id,
            version="1",
        )
        return raw.decode("utf-8")

    if _production() and not is_encrypted_oauth_client_secret(stored_value):
        raise RuntimeError("production OAuth client secret is not encrypted")

    from api.column_crypto import decrypt_column

    return decrypt_column(stored_value)


def provision_oauth_client_credentials(site_id: str) -> tuple[str, str]:
    """Return (oauth_client_id, encrypted_oauth_client_secret)."""
    client_id = f"oc_{secrets.token_urlsafe(16)}"
    secret = generate_oauth_client_secret()
    stored = encrypt_oauth_client_secret(site_id, secret)
    return client_id, stored
