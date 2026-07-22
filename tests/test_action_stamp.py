"""Tests for action-bound stamp signing and offline verification."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY_SDK_PATH = ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
MJS_PATH = ROOT / "static" / "js" / "proof-verifier.mjs"
VERIFIER_PATH = ROOT / "static" / "js" / "ishuman-verifier.js"
WALLET_PATH = ROOT / "static" / "js" / "lemma-wallet.js"
KEYS_PATH = ROOT / "static" / "js" / "lemma-keys.js"


def _load_py_sdk():
    pytest.importorskip("cryptography")
    name = "lemma_proof_verifier_action_tests"
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


def test_hash_action_body_is_stable(py_sdk):
    body = {"amountCents": 4200, "cartId": "abc", "currency": "USD"}
    assert py_sdk.hash_action_body(body) == py_sdk.hash_action_body(
        {"currency": "USD", "cartId": "abc", "amountCents": 4200}
    )


def test_verify_action_stamp_rejects_missing_stamp(py_sdk):
    ctx = py_sdk.VerificationContext(site_id="demo.example.com")
    result = ctx.verify_action_stamp({"payload": {}}, action="checkout")
    assert result.ok is False
    assert result.reason == "action_stamp_missing"


def test_verify_action_stamp_replays_nonce(py_sdk, monkeypatch):
    import time

    mod = py_sdk
    ctx = mod.VerificationContext(site_id="demo.example.com", required_assurance="passkey")
    store = mod.InMemoryNonceStore()
    now = int(time.time())
    body = {"action": "checkout", "amountCents": 100}
    body_hash = mod.hash_action_body(body)

    stamped = {
        "payload": body,
        "lemma": {
            "version": mod.ACTION_STAMP_VERSION,
            "action": "checkout",
            "method": "POST",
            "path": "/api/checkout",
            "bodyHash": body_hash,
            "nonce": "nonce-1",
            "credential": {
                "id": "c1",
                "subject": "did:lemma:ppid_a",
                "claims": {"site_signing_pubkey": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
                "proof": {},
            },
            "action_assertion": {
                "version": mod.ACTION_STAMP_VERSION,
                "site_id": "demo.example.com",
                "credential_id": "c1",
                "subject": "did:lemma:ppid_a",
                "assurance": "passkey",
                "action": "checkout",
                "method": "POST",
                "path": "/api/checkout",
                "body_hash": body_hash,
                "nonce": "nonce-1",
                "issued_at_unix": now,
                "expires_at_unix": now + 60,
            },
            "action_signature": "abc",
        },
    }

    monkeypatch.setattr(
        ctx,
        "verify",
        lambda presentation: mod.VerificationContext.Result(
            True,
            "valid",
            ppid="did:lemma:ppid_a",
            credential_id="c1",
            assurance="passkey",
        ),
    )
    monkeypatch.setattr(
        mod,
        "_verify_site_ed25519_digest",
        lambda *_args, **_kwargs: None,
    )

    first = ctx.verify_action_stamp(
        stamped,
        action="checkout",
        method="POST",
        path="/api/checkout",
        body=body,
        nonce_store=store,
    )
    second = ctx.verify_action_stamp(
        stamped,
        action="checkout",
        method="POST",
        path="/api/checkout",
        body=body,
        nonce_store=store,
    )
    assert first.ok is True
    assert second.ok is False
    assert second.reason == "action_nonce_reused"


@pytest.mark.browser
def test_wallet_exposes_sign_site_action_presentation():
    source = WALLET_PATH.read_text(encoding="utf-8")
    assert "async signSiteActionPresentation(" in source
    assert "lemma:site-action-presentation:v1" in source


@pytest.mark.browser
def test_keys_exposes_hash_action_body():
    source = KEYS_PATH.read_text(encoding="utf-8")
    assert "hashActionBody" in source
    assert "canonicalJsonStringify" in source


@pytest.mark.browser
def test_verifier_exposes_stamp_action():
    source = VERIFIER_PATH.read_text(encoding="utf-8")
    assert "async stampAction(payload = {}, options = {})" in source
    assert "ACTION_STAMP_VERSION" in source
    assert "_signActionViaPopup" in source


def test_node_sdk_exposes_verify_action_stamp():
    src = MJS_PATH.read_text(encoding="utf-8")
    assert "async function verifyActionStamp(" in src
    assert "export async function hashActionBody" in src
    assert "export class InMemoryNonceStore" in src
    assert "@version 1.4.0" in src
    assert "return { verify, verifyWithPolicy, verifyStamp, verifyActionStamp, refresh };" in src


def test_backend_sdk_version_headers():
    from api.sdk_versions import backend_verifier_version

    serving = (ROOT / "api" / "sdk_serving.py").read_text(encoding="utf-8")
    assert 'response.headers["X-SDK-Version"] = version' in serving
    assert "backend_verifier_version()" in serving
    assert backend_verifier_version() == "1.4.0"


def test_docs_mention_stamp_action():
    docs = (ROOT / "docs" / "integration" / "ISHUMAN_AGENT_INTEGRATION.md").read_text(encoding="utf-8")
    assert "stampAction" in docs
    assert "verify_action_stamp" in docs or "verifyActionStamp" in docs
