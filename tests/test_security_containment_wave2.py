"""Wave 2 security containment regression tests."""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest
from flask import Flask, g

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("SESSION_SECRET", "containment-test-session-secret")
os.environ.setdefault("LEMMA_ACCESS_TOKEN_SECRET", "containment-access-token-secret")

PPID = (
    "did:lemma:ppid_abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
)


def _load_py_sdk():
    pytest.importorskip("cryptography")
    name = "lemma_proof_verifier_wave2"
    if name in sys.modules:
        return sys.modules[name]
    path = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_sdk_api_key_fingerprint_is_stable_and_non_reversible():
    from api.sdk_api import _api_key_fingerprint

    fp = _api_key_fingerprint("lm_site_secret_value")
    assert len(fp) == 16
    assert fp == _api_key_fingerprint("lm_site_secret_value")
    assert fp != "lm_site_secret_value"
    assert "secret" not in fp


def test_sdk_idv_session_binds_fingerprint_not_raw_key():
    from api import sdk_api

    sdk_api._sdk_idv_sessions_memory.clear()
    sdk_api._store_sdk_idv_session("sess_1", api_key="lm_raw_key_abc", user_id="u1")
    stored = sdk_api._sdk_idv_sessions_memory[sdk_api._sdk_idv_session_key("sess_1")]
    assert "api_key" not in stored
    assert stored["api_key_fp"] == sdk_api._api_key_fingerprint("lm_raw_key_abc")

    assert sdk_api._consume_sdk_idv_session("sess_1", api_key="lm_raw_key_abc") is not None
    assert sdk_api._consume_sdk_idv_session("sess_1", api_key="lm_raw_key_abc") is None


def test_developer_self_issue_auth_uses_only_g_ppid(monkeypatch):
    from api import developer_self_issue as dsi

    app = Flask(__name__)
    app.config["TESTING"] = True

    class _Cust:
        customer_id = "cust_1"

    monkeypatch.setattr(
        "api.customer_accounts.customer_manager.get_customer_by_ppid",
        lambda ppid: _Cust() if ppid == PPID else None,
    )

    with app.test_request_context(
        "/api/developer/issue-self-permission",
        headers={"X-Lemma-Credential": '{"subject":"did:lemma:ppid_forged"}'},
    ):
        g.ppid = PPID
        cid, did = dsi._authenticate_developer()
        assert cid == "cust_1"
        assert did == PPID

    with app.test_request_context("/"):
        cid, did = dsi._authenticate_developer()
        assert cid is None and did is None


def test_developer_bootstrap_requires_domain_proof(monkeypatch):
    from api import developer_self_issue as dsi

    ok, err = dsi._require_domain_proof_for_bootstrap({}, "new-site.example.com")
    assert ok is False
    assert err == "domain_verification_required"

    monkeypatch.setattr(
        "api.domain_ownership.consume_verified_domain_proof",
        lambda domain, token, method: domain == "new-site.example.com" and token == "tok",
    )
    ok, err = dsi._require_domain_proof_for_bootstrap(
        {"domain_verification_token": "tok", "domain_verification_method": "dns"},
        "new-site.example.com",
    )
    assert ok is True
    assert err == "ok"


def test_verify_well_known_blocks_private_targets(monkeypatch):
    from api import issuer_registry

    called = {"fetch": False}

    def _blocked(url, **_kwargs):
        called["fetch"] = True
        return False, "private_or_reserved_ip", None

    monkeypatch.setattr("api.url_safety.fetch_safe_outbound_text", _blocked)
    assert issuer_registry.verify_well_known("127.0.0.1", "token") is False
    assert called["fetch"] is True


def test_trusted_issuer_fail_closed_missing_expiry_and_revocation(monkeypatch):
    from api import trusted_issuers

    monkeypatch.setattr(trusted_issuers, "is_trusted_issuer", lambda _did: True)

    cred = {
        "id": "cred_1",
        "issuer": "did:lemma:issuer",
        "claims": {"siteId": "example.com"},
    }
    result = trusted_issuers.verify_credential_with_trust(cred)
    assert result["valid"] is False
    assert result["reason"] == "expires_at_missing"

    cred2 = {
        "id": "cred_2",
        "issuer": "did:lemma:issuer",
        "claims": {"siteId": "example.com", "expiresAt": str(4102444800)},
    }
    monkeypatch.setattr(
        "api.revocation_verifier.check_revocation_candidate",
        lambda _cid: "unavailable",
    )
    result2 = trusted_issuers.verify_credential_with_trust(cred2)
    assert result2["valid"] is False
    assert result2["reason"] == "revocation_unavailable"


def _load_py_sdk_testing(mod):
    name = "lemma_proof_verifier_testing_wave2"
    if name in sys.modules:
        return sys.modules[name]
    path = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier_testing.py"
    # Ensure sibling import resolves to the wave2-loaded verifier module.
    sys.modules["lemma_proof_verifier"] = mod
    spec = importlib.util.spec_from_file_location(name, path)
    testing = importlib.util.module_from_spec(spec)
    sys.modules[name] = testing
    assert spec.loader is not None
    spec.loader.exec_module(testing)
    return testing


def test_proof_verifier_require_session_assertion_without_site_key():
    mod = _load_py_sdk()
    testing = _load_py_sdk_testing(mod)
    issuer = testing.mint_test_issuer()
    # Minted credentials intentionally omit site_signing_pubkey.
    presentation = testing.mint_test_presentation(
        site_id="demo.example.com",
        ppid=PPID,
        assurance="passkey",
        issuer=issuer,
    )
    ctx = testing.create_offline_test_context(
        site_id="demo.example.com",
        issuer_did=issuer["did"],
        issuer_pubkey_hex=issuer["pubkey_hex"],
        required_assurance="passkey",
    )
    ctx.require_session_assertion = True
    result = ctx.verify(presentation)
    assert result.ok is False
    assert result.reason == "credential_missing_site_signing_pubkey"


def test_proof_verifier_rejects_zero_expiry():
    mod = _load_py_sdk()
    testing = _load_py_sdk_testing(mod)
    issuer = testing.mint_test_issuer()
    presentation = testing.mint_test_presentation(
        site_id="demo.example.com",
        ppid=PPID,
        assurance="passkey",
        issuer=issuer,
    )
    presentation["credential"]["claims"]["expiresAt"] = "0"
    presentation["credential"]["credentialSubject"]["expiresAt"] = "0"
    # Re-sign after mutating expiry so signature verification is not the fail reason.
    message = mod.browser_canonical_message(presentation["credential"])
    digest = __import__("hashlib").sha256(message).digest()
    presentation["credential"]["proof"]["signatureValueWeb"] = issuer["private_key"].sign(
        digest
    ).hex()

    ctx = testing.create_offline_test_context(
        site_id="demo.example.com",
        issuer_did=issuer["did"],
        issuer_pubkey_hex=issuer["pubkey_hex"],
        required_assurance="passkey",
    )
    result = ctx.verify(presentation)
    assert result.ok is False
    assert result.reason in {"expiresAt_missing", "credential_expires_at_missing"}
