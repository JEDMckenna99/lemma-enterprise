"""isHuman v2 (Phase 1.1): person-root seed derivation + sealed envelopes.

The server holds the document-anchored ``person_root`` (32 bytes, never leaves).
At IDV completion it derives two per-wallet secrets and seals each to the
wallet's posted X25519 public encryption key so only that wallet can open them:

    wallet_local_seed   = HKDF(person_root, info="wallet-local-seed/v1" | wallet_id)
        -> replaces wallet_secret as the root for per-site signing keys
    person_root_proxy   = HKDF(person_root, info="person-root-proxy/v1")
        -> lets the wallet compute its own PPIDs client-side without a round-trip

Both derivations are deterministic: the same person_root always yields the same
seeds, so re-IDV restores identical material (identity lives in the network).

The sealed envelope is a libsodium-style sealed box built on X25519 + HKDF +
ChaCha20-Poly1305 using only the ``cryptography`` package. Wire format:

    version(1) || ephemeral_pubkey(32) || nonce(12) || ciphertext(16+ tag)
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SEED_VERSION = "v1"
ENVELOPE_VERSION = 1

WALLET_LOCAL_SEED_INFO = b"lemma.id/wallet-local-seed/v1"
SEAL_INFO = b"lemma.id/seed-envelope/v1"


def _hkdf(ikm: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(ikm)


def derive_wallet_local_seed(person_root: bytes, wallet_id: str) -> bytes:
    """Per-wallet signing seed. Same person_root + wallet_id -> same seed."""
    if len(person_root) != 32:
        raise ValueError("person_root must be 32 bytes")
    info = WALLET_LOCAL_SEED_INFO + b"|" + (wallet_id or "").encode("utf-8")
    return _hkdf(person_root, info)


def derive_person_root_proxy(person_root: bytes) -> bytes:
    """Person-root proxy delivered (sealed) to the wallet for client-side PPID
    computation.

    It is the person_root itself so that the wallet's
    ``derive_ppid_from_person_root_bytes(proxy, site)`` produces byte-identical
    PPIDs to the server's ``derive_ppid_from_person_root_bytes(person_root, site)``
, no round-trip needed for display. It is only ever transmitted sealed to the
    wallet's X25519 key (see ``seal_envelope``), never in the clear.
    """
    if len(person_root) != 32:
        raise ValueError("person_root must be 32 bytes")
    return bytes(person_root)


def _raw_pub(pubkey: X25519PublicKey) -> bytes:
    return pubkey.public_bytes(Encoding.Raw, PublicFormat.Raw)


def seal_envelope(recipient_pubkey: bytes, plaintext: bytes) -> bytes:
    """Seal *plaintext* to the wallet's X25519 public key (anonymous sender)."""
    if len(recipient_pubkey) != 32:
        raise ValueError("recipient_pubkey must be a 32-byte X25519 key")
    ephemeral = X25519PrivateKey.generate()
    eph_pub = _raw_pub(ephemeral.public_key())
    recipient = X25519PublicKey.from_public_bytes(recipient_pubkey)
    shared = ephemeral.exchange(recipient)
    key = _hkdf(shared, SEAL_INFO + eph_pub + recipient_pubkey)
    nonce = os.urandom(12)
    aead = AESGCM(key)
    ciphertext = aead.encrypt(nonce, plaintext, eph_pub)
    return bytes([ENVELOPE_VERSION]) + eph_pub + nonce + ciphertext


def open_envelope(recipient_privkey: bytes, blob: bytes) -> bytes:
    """Open a sealed envelope with the wallet's X25519 private key."""
    if not blob or blob[0] != ENVELOPE_VERSION:
        raise ValueError("unsupported envelope version")
    if len(blob) < 1 + 32 + 12 + 16:
        raise ValueError("envelope too short")
    eph_pub = blob[1:33]
    nonce = blob[33:45]
    ciphertext = blob[45:]
    private = X25519PrivateKey.from_private_bytes(recipient_privkey)
    recipient_pub = _raw_pub(private.public_key())
    shared = private.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    key = _hkdf(shared, SEAL_INFO + eph_pub + recipient_pub)
    aead = AESGCM(key)
    return aead.decrypt(nonce, ciphertext, eph_pub)


def use_person_root_seeds_enabled() -> bool:
    """Feature flag (Phase 1.1). Default OFF -> existing wallet_secret behavior."""
    return (os.getenv("LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS", "") or "").strip().lower() == "true"
