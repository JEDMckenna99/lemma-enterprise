"""Demo issuer and device Ed25519 key management."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _hex_to_bytes(hex_str: str) -> bytes:
    clean = hex_str.strip()
    if len(clean) != 64:
        raise ValueError("Ed25519 private key hex must be 64 characters (32 bytes)")
    return bytes.fromhex(clean)


def load_public_key_b64(private_key: Ed25519PrivateKey) -> str:
    return _b64url(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ))


def _key_from_env(env_name: str) -> Ed25519PrivateKey | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    return Ed25519PrivateKey.from_private_bytes(_hex_to_bytes(raw))


def _ensure_key(path: Path, env_name: str | None = None) -> Ed25519PrivateKey:
    if env_name:
        from_env = _key_from_env(env_name)
        if from_env is not None:
            return from_env
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    key = Ed25519PrivateKey.generate()
    path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    return key


def ensure_issuer_keypair(path: Path) -> Ed25519PrivateKey:
    return _ensure_key(path, "DELIVERY_ISSUER_KEY_HEX")


def ensure_device_keypair(path: Path) -> Ed25519PrivateKey:
    return _ensure_key(path, "DELIVERY_DEVICE_KEY_HEX")


def load_private_key(path: Path) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(path.read_bytes())


def private_key_to_hex(private_key: Ed25519PrivateKey) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()


def sign_bytes(private_key: Ed25519PrivateKey, message: bytes) -> str:
    return _b64url(private_key.sign(message))


def verify_bytes(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(public_key_b64))
        pub.verify(_b64url_decode(signature_b64), message)
        return True
    except (InvalidSignature, ValueError):
        return False
