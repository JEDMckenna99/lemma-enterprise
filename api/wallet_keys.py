"""
Wallet signing-key derivation and assertion helpers (Python).

Must match static/js/lemma-keys.js canonical formats.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Iterable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

WALLET_SIGNING_KEY_DOMAIN = b"lemma:hkdf:v1"
WALLET_SIGNING_KEY_INFO = b"wallet-signing-key-v1"
ASSERTION_PREFIX = "lemma:wallet-assertion:v1"
REGISTER_PREFIX = "lemma:register-signing-key:v1"
CHALLENGE_TTL_SECONDS = 120


def _hex_to_bytes(wallet_secret: str) -> bytes:
    text = (wallet_secret or "").strip()
    if not text:
        raise ValueError("wallet_secret required")
    return bytes.fromhex(text)


def derive_wallet_signing_seed(wallet_secret: str) -> bytes:
    ikm = _hex_to_bytes(wallet_secret)
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=WALLET_SIGNING_KEY_DOMAIN,
        info=WALLET_SIGNING_KEY_INFO,
    ).derive(ikm)


def derive_wallet_signing_keypair(wallet_secret: str) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    seed = derive_wallet_signing_seed(wallet_secret)
    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    return private_key, private_key.public_key()


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    padded = (text or "").strip() + ("=" * (-len(text) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def build_assertion_payload(
    *,
    wallet_id: str,
    nonce_b64: str,
    field_names: Iterable[str],
    field_values: dict,
) -> bytes:
    lines = [
        ASSERTION_PREFIX,
        str(wallet_id or "").strip(),
        str(nonce_b64 or "").strip(),
    ]
    for name in field_names:
        key = str(name or "").strip()
        value = field_values.get(key, field_values.get(name, ""))
        if value is None:
            value = ""
        lines.append(f"{key}={str(value)}")
    return "\n".join(lines).encode("utf-8")


def build_register_payload(*, wallet_id: str, pubkey_b64: str) -> bytes:
    lines = [
        REGISTER_PREFIX,
        str(wallet_id or "").strip(),
        str(pubkey_b64 or "").strip(),
    ]
    return "\n".join(lines).encode("utf-8")


def sign_message(private_key: Ed25519PrivateKey, message: bytes) -> bytes:
    digest = hashlib.sha256(message).digest()
    return private_key.sign(digest)


def verify_message(public_key: Ed25519PublicKey, message: bytes, signature: bytes) -> bool:
    digest = hashlib.sha256(message).digest()
    try:
        public_key.verify(signature, digest)
        return True
    except Exception:
        return False


def pubkey_to_b64url(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return b64url_encode(raw)


def register_self_signature(wallet_id: str, wallet_secret: str) -> tuple[str, str]:
    """Return (pubkey_b64, signature_b64) for register-signing-key."""
    _priv, pub = derive_wallet_signing_keypair(wallet_secret)
    pubkey_b64 = pubkey_to_b64url(pub)
    payload = build_register_payload(wallet_id=wallet_id, pubkey_b64=pubkey_b64)
    sig = sign_message(_priv, payload)
    return pubkey_b64, b64url_encode(sig)


@dataclass
class WalletAssertion:
    nonce: str
    signature: str


def build_wallet_assertion(
    *,
    wallet_id: str,
    wallet_secret: str,
    field_names: list[str],
    field_values: dict,
    nonce_b64: str | None = None,
) -> WalletAssertion:
    priv, _pub = derive_wallet_signing_keypair(wallet_secret)
    nonce = nonce_b64 or b64url_encode(secrets.token_bytes(32))
    payload = build_assertion_payload(
        wallet_id=wallet_id,
        nonce_b64=nonce,
        field_names=field_names,
        field_values=field_values,
    )
    sig = sign_message(priv, payload)
    return WalletAssertion(nonce=nonce, signature=b64url_encode(sig))
