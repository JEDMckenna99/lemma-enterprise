"""Wallet session fallback auth for browser billing and developer APIs."""

from __future__ import annotations

import base64
import json

import pytest
from flask import Flask, g, jsonify


def _encode_header(credential: dict) -> str:
    raw = json.dumps(credential).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _ppid(seed: str = "a") -> str:
    return f"did:lemma:ppid_{seed * 64}"


@pytest.mark.unit
def test_try_wallet_session_principal_accepts_parseable_header(monkeypatch):
    from api.authz_engine import try_wallet_session_principal

    ppid = _ppid("b")
    credential = {
        "id": "cred_browser",
        "subject": ppid,
        "claims": {"permissionId": "admin_access", "siteId": "lemma.id"},
    }

    monkeypatch.setattr(
        "api.agent_credentials._has_valid_wallet_unlock_session",
        lambda: True,
    )
    monkeypatch.setattr(
        "api.agent_credentials._decode_lemma_header_credential",
        lambda: credential,
    )

    principal, error = try_wallet_session_principal(
        {"X-Lemma-Credential": _encode_header(credential)}
    )
    assert error is None
    assert principal is not None
    assert principal.ppid == ppid
    assert principal.auth_method == "wallet_session"


@pytest.mark.unit
def test_billing_account_status_accepts_wallet_session(monkeypatch):
    from api.stripe_usage_billing import stripe_usage_billing_bp

    ppid = _ppid("c")
    credential = {
        "id": "cred_billing",
        "subject": ppid,
        "claims": {"permissionId": "admin_access", "siteId": "lemma.id"},
    }

    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (None, "invalid_lemma:invalid_signature"),
    )
    monkeypatch.setattr(
        "api.agent_credentials._has_valid_wallet_unlock_session",
        lambda: True,
    )
    monkeypatch.setattr(
        "api.agent_credentials._decode_lemma_header_credential",
        lambda: credential,
    )

    class FakeCustomer:
        customer_id = "cus_test"
        email = "owner@lemma.id"
        stripe_customer_id = "cus_stripe"
        subscription_status = "none"
        monthly_usage = {}
        sites = []

    class FakeManager:
        def get_customer_by_did(self, _ppid):
            return FakeCustomer()

        def get_customer(self, _customer_id):
            return FakeCustomer()

    monkeypatch.setattr(
        "api.customer_accounts.customer_manager",
        FakeManager(),
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(stripe_usage_billing_bp)

    client = app.test_client()
    resp = client.get(
        "/api/billing/account-status",
        headers={"X-Lemma-Credential": _encode_header(credential)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["billing"]["customer_id"] == "cus_test"


@pytest.mark.unit
def test_require_customer_or_admin_uses_wallet_session_fallback(monkeypatch):
    from auth.decorators import require_customer_or_admin

    ppid = _ppid("d")
    credential = {
        "id": "cred_decorator",
        "subject": ppid,
        "claims": {"permissionId": "admin_access", "siteId": "lemma.id"},
    }

    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (None, "invalid_lemma:invalid_signature"),
    )
    monkeypatch.setattr(
        "api.agent_credentials._has_valid_wallet_unlock_session",
        lambda: True,
    )
    monkeypatch.setattr(
        "api.agent_credentials._decode_lemma_header_credential",
        lambda: credential,
    )

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.get("/protected")
    @require_customer_or_admin
    def protected():
        return jsonify({"ppid": g.ppid, "auth_method": g.auth_method})

    client = app.test_client()
    resp = client.get(
        "/protected",
        headers={"X-Lemma-Credential": _encode_header(credential)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ppid"] == ppid
    assert payload["auth_method"] == "wallet_session"
