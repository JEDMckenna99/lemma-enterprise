"""Verify the server-issued isHuman credentials carry a browser-canonical Ed25519 signature.

The static/js/ishuman-verifier.js verifier builds its canonical signing message
with `JSON.stringify({issuer, subject, claims: sorted, issuedAt?, expiresAt?})`
using JSON.stringify default separators and undefined-key omission. The Rust
issuer signs a different (binary-concat) message format that the JS verifier
cannot reproduce, so the server attaches a parallel `signatureValueWeb`
covering the browser canonical message.

These tests pin the canonical message format and round-trip the signature
against an Ed25519 public key derived from the issuer's seed.
"""

from __future__ import annotations

import hashlib
import json

import pytest

cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _canonical_message_python(credential: dict) -> bytes:
    """Reference Python port of canonicalMessage() in ishuman-verifier.js."""
    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    sorted_claims: dict = {}
    for key in sorted(claims.keys()):
        value = claims[key]
        if value is True:
            sorted_claims[key] = "true"
        elif value is False:
            sorted_claims[key] = "false"
        elif isinstance(value, (list, dict)):
            sorted_claims[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        else:
            sorted_claims[key] = value
    payload: dict = {
        "issuer": credential.get("issuer"),
        "subject": credential.get("subject"),
        "claims": sorted_claims,
    }
    if credential.get("issuedAt") is not None:
        payload["issuedAt"] = credential["issuedAt"]
    if credential.get("expiresAt") is not None:
        payload["expiresAt"] = credential["expiresAt"]
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_browser_canonical_matches_static_pinned_bytes():
    credential = {
        "issuer": "did:lemma:abcdef",
        "subject": "did:lemma:ppid_e09aedba",
        "claims": {
            "isHuman": True,
            "siteId": "tickets-demo.lemma.id",
            "issuedAt": "1779999",
            "expiresAt": "1781111",
            "verificationMethod": "stripe_identity",
            "packageType": "identity",
            "site_signing_pubkey": "abcXYZ==",
            "ppidDerivation": "person_root_v1",
        },
    }
    expected = (
        '{"issuer":"did:lemma:abcdef",'
        '"subject":"did:lemma:ppid_e09aedba",'
        '"claims":{'
        '"expiresAt":"1781111",'
        '"isHuman":"true",'
        '"issuedAt":"1779999",'
        '"packageType":"identity",'
        '"ppidDerivation":"person_root_v1",'
        '"siteId":"tickets-demo.lemma.id",'
        '"site_signing_pubkey":"abcXYZ==",'
        '"verificationMethod":"stripe_identity"'
        '}}'
    ).encode("utf-8")
    assert _canonical_message_python(credential) == expected


def test_server_issued_credential_carries_browser_signature():
    pytest.importorskip("api.ishuman")
    from api.ishuman import _browser_canonical_message, _sign_with_issuer_for_browser

    seed = b"\x11" * 32

    class _FakeIssuer:
        def signing_key_bytes(self):  # noqa: D401
            return seed

    credential = {
        "issuer": "did:lemma:1111111111",
        "subject": "did:lemma:ppid_demo",
        "claims": {
            "isHuman": True,
            "siteId": "tickets-demo.lemma.id",
            "issuedAt": "1779000",
            "expiresAt": "1780000",
        },
    }
    signature_hex = _sign_with_issuer_for_browser(credential, _FakeIssuer())
    assert len(signature_hex) == 128, "Ed25519 signature must be 64 bytes hex-encoded"

    # Verify with the matching public key
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk = sk.public_key()
    message = _browser_canonical_message(credential)
    digest = hashlib.sha256(message).digest()
    pk.verify(bytes.fromhex(signature_hex), digest)


def test_canonical_message_matches_server_helper():
    pytest.importorskip("api.ishuman")
    from api.ishuman import _browser_canonical_message

    credential = {
        "issuer": "did:lemma:abc",
        "subject": "did:lemma:ppid_xyz",
        "claims": {
            "isHuman": True,
            "verificationMethod": "stripe_identity",
            "packageType": "identity",
            "siteId": "lemma.id",
            "issuedAt": "100",
            "expiresAt": "200",
        },
    }
    assert _browser_canonical_message(credential) == _canonical_message_python(credential)
