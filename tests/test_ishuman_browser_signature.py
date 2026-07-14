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

pytestmark = pytest.mark.integration

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


def test_verify_presentation_endpoint_round_trip(monkeypatch):
    """The /api/ishuman/verify-presentation endpoint accepts a presentation bundle and validates it."""
    pytest.importorskip("flask")
    pytest.importorskip("api.ishuman")

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from flask import Flask

    from api import ishuman as ishuman_module
    from api.ishuman import (
        _browser_canonical_message,
        _sign_with_issuer_for_browser,
        ishuman_bp,
    )

    seed = b"\x22" * 32
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk_hex = sk.public_key().public_bytes_raw().hex()
    issuer_did = f"did:lemma:{pk_hex}"

    class _FakeIssuer:
        def signing_key_bytes(self):
            return seed

        def get_did(self):
            return issuer_did

        def get_public_key_hex(self):
            return pk_hex

    credential = {
        "id": "ishuman_site_test123",
        "issuer": issuer_did,
        "subject": "did:lemma:ppid_demo",
        "claims": {
            "isHuman": True,
            "siteId": "tickets-demo.lemma.id",
            "issuedAt": "1700000000",
            "expiresAt": str(2_000_000_000),
            "packageType": "identity",
            "verificationMethod": "stripe_identity",
        },
        "credentialSubject": {
            "isHuman": True,
            "siteId": "tickets-demo.lemma.id",
            "issuedAt": "1700000000",
            "expiresAt": str(2_000_000_000),
            "packageType": "identity",
            "verificationMethod": "stripe_identity",
        },
        "issuerInfo": {"did": issuer_did, "publicKey": pk_hex},
        "proof": {
            "type": "Ed25519Signature2020",
            "verificationMethod": issuer_did,
            "signatureValueWeb": _sign_with_issuer_for_browser(
                {
                    "issuer": issuer_did,
                    "subject": "did:lemma:ppid_demo",
                    "claims": {
                        "isHuman": True,
                        "siteId": "tickets-demo.lemma.id",
                        "issuedAt": "1700000000",
                        "expiresAt": str(2_000_000_000),
                        "packageType": "identity",
                        "verificationMethod": "stripe_identity",
                    },
                },
                _FakeIssuer(),
            ),
        },
    }

    # Bypass external trust list / revocation lookups for this isolated test.
    monkeypatch.setattr(
        "api.trusted_issuers.is_trusted_issuer",
        lambda did: did == issuer_did,
        raising=False,
    )
    import sys, types
    fake_rev = types.SimpleNamespace(is_credential_revoked=lambda _cid: False)
    monkeypatch.setitem(sys.modules, "api.revocation_verifier", fake_rev)

    app = Flask(__name__)
    app.register_blueprint(ishuman_bp)
    client = app.test_client()

    response = client.post(
        "/api/ishuman/verify-presentation",
        json={
            "site_id": "tickets-demo.lemma.id",
            "credential": credential,
        },
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert data["success"] is True
    assert data["human"] is True
    assert data["ppid"] == "did:lemma:ppid_demo"
    assert data["site_id"] == "tickets-demo.lemma.id"
    assert data["session_status"] == "absent"

    passkey_credential = json.loads(json.dumps(credential))
    passkey_credential["claims"] = {
        "assurance": "passkey",
        "siteId": "tickets-demo.lemma.id",
        "issuedAt": "1700000000",
        "expiresAt": str(2_000_000_000),
        "packageType": "identity",
        "verificationMethod": "passkey",
    }
    passkey_credential["credentialSubject"] = dict(passkey_credential["claims"])
    passkey_credential["proof"]["signatureValueWeb"] = _sign_with_issuer_for_browser(
        {
            "issuer": issuer_did,
            "subject": "did:lemma:ppid_demo",
            "claims": passkey_credential["claims"],
        },
        _FakeIssuer(),
    )
    passkey_resp = client.post(
        "/api/ishuman/verify-presentation",
        json={
            "site_id": "tickets-demo.lemma.id",
            "credential": passkey_credential,
            "required_assurance": "passkey",
        },
    )
    assert passkey_resp.status_code == 200, passkey_resp.get_json()
    passkey_data = passkey_resp.get_json()
    assert passkey_data["success"] is True
    assert passkey_data["assurance"] == "passkey"

    passkey_only_resp = client.post(
        "/api/ishuman/verify-presentation",
        json={
            "site_id": "tickets-demo.lemma.id",
            "credential": passkey_credential,
        },
    )
    assert passkey_only_resp.status_code == 400, passkey_only_resp.get_json()
    assert passkey_only_resp.get_json()["error"] == "assurance_insufficient"

    # A tampered claim should now fail signature verification.
    tampered = json.loads(json.dumps(credential))
    tampered["claims"]["siteId"] = "evil.example.com"
    tampered["credentialSubject"]["siteId"] = "evil.example.com"
    bad = client.post(
        "/api/ishuman/verify-presentation",
        json={"site_id": "evil.example.com", "credential": tampered},
    )
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "invalid_signature"
