"""Tests for fresh-passkey attestation and action commitment helpers."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY_SDK_PATH = ROOT / "packages" / "ishuman-verify-py" / "lemma_ishuman_verify.py"


def _load_py_sdk():
    pytest.importorskip("cryptography")
    name = "lemma_ishuman_verify_fresh_passkey_tests"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PY_SDK_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(name="py_sdk")
def fixture_py_sdk():
    return _load_py_sdk()


@pytest.mark.unit
def test_build_action_commitment_is_stable(py_sdk):
    commitment = py_sdk.build_action_commitment(
        server_nonce="nonce-abc",
        site_id="demo.example.com",
        action="claim_presale_code",
        method="POST",
        path="/api/presale/claim-code",
        body_hash="deadbeef",
    )
    again = py_sdk.build_action_commitment(
        server_nonce="nonce-abc",
        site_id="demo.example.com",
        action="claim_presale_code",
        method="post",
        path="/api/presale/claim-code",
        body_hash="DEADBEEF",
    )
    assert commitment == again
    assert len(commitment) == 64


@pytest.mark.unit
def test_verify_fresh_passkey_attestation(fake_issuer, py_sdk):
    from api.fresh_passkey_attestation import issue_fresh_passkey_attestation

    _issuer, pk_hex = fake_issuer
    attestation = issue_fresh_passkey_attestation(
        site_id="demo.example.com",
        credential_id="cred_123",
        subject="did:lemma:ppid_" + ("a" * 64),
        action_commitment=py_sdk.build_action_commitment(
            server_nonce="nonce-1",
            site_id="demo.example.com",
            action="claim_presale_code",
            method="POST",
            path="/api/presale/claim-code",
            body_hash=py_sdk.hash_action_body({"drop_id": "drop-1"}),
        ),
    )
    ok, reason = py_sdk.verify_fresh_passkey_attestation(
        attestation,
        site_id="demo.example.com",
        credential_id="cred_123",
        subject=attestation["subject"],
        action_commitment=attestation["action_commitment"],
        trusted_issuer_pubkeys=[pk_hex],
    )
    assert ok is True
    assert reason == "valid"


@pytest.mark.unit
def test_verify_action_stamp_requires_fresh_passkey(py_sdk, monkeypatch):
    now = int(time.time())
    body = {"drop_id": "drop-1"}
    body_hash = py_sdk.hash_action_body(body)
    server_nonce = "server-nonce-001"
    commitment = py_sdk.build_action_commitment(
        server_nonce=server_nonce,
        site_id="demo.example.com",
        action="claim_presale_code",
        method="POST",
        path="/api/presale/claim-code",
        body_hash=body_hash,
    )
    ctx = py_sdk.VerificationContext(site_id="demo.example.com", required_assurance="passkey")
    stamped = {
        "drop_id": "drop-1",
        "lemma": {
            "credential": {
                "id": "cred_123",
                "subject": "did:lemma:ppid_a",
                "claims": {"site_signing_pubkey": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
                "proof": {},
            },
            "action_assertion": {
                "version": py_sdk.ACTION_STAMP_VERSION,
                "site_id": "demo.example.com",
                "credential_id": "cred_123",
                "subject": "did:lemma:ppid_a",
                "assurance": "passkey",
                "action": "claim_presale_code",
                "method": "POST",
                "path": "/api/presale/claim-code",
                "body_hash": body_hash,
                "nonce": "nonce-claim-1",
                "issued_at_unix": now,
                "expires_at_unix": now + 60,
            },
            "action_signature": "abc",
        },
    }
    monkeypatch.setattr(
        ctx,
        "verify",
        lambda presentation: py_sdk.VerificationContext.Result(
            True,
            "valid",
            ppid="did:lemma:ppid_a",
            credential_id="cred_123",
            assurance="passkey",
        ),
    )
    monkeypatch.setattr(py_sdk, "_verify_site_ed25519_digest", lambda *_args, **_kwargs: None)
    missing = ctx.verify_action_stamp(
        stamped,
        action="claim_presale_code",
        method="POST",
        path="/api/presale/claim-code",
        body=body,
        require_fresh_passkey=True,
        server_nonce=server_nonce,
        nonce_store=py_sdk.InMemoryNonceStore(),
    )
    assert missing.ok is False
    assert missing.reason == "fresh_passkey_missing"


@pytest.fixture
def fake_issuer(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    seed = b"\x44" * 32
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk_hex = sk.public_key().public_bytes_raw().hex()

    class _Issuer:
        def signing_key_bytes(self):
            return seed

        def get_did(self):
            return f"did:lemma:{pk_hex}"

    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: _Issuer())
    return _Issuer(), pk_hex
