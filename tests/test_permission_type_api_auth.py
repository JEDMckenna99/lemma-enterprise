"""Tests for permission type API auth, forged credentials must fail."""

from __future__ import annotations

import json

import pytest
from flask import Flask


@pytest.fixture(name="perm_type_client")
def fixture_perm_type_client(monkeypatch):
    from api.permission_type_api import permission_type_api

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(permission_type_api)
    with app.test_client() as client:
        yield client


@pytest.mark.unit
def test_forged_json_bearer_rejected(perm_type_client):
    forged = json.dumps({
        "subject": "did:lemma:ppid_attacker",
        "claims": {"email": "attacker@evil.com", "permissionId": "admin"},
    })
    resp = perm_type_client.get(
        "/api/v1/sites/site_victim/permission-types",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert resp.status_code == 401


@pytest.mark.unit
def test_verify_site_access_rejects_unverified_json(monkeypatch):
    from api.permission_type_api import _verify_site_access

    app = Flask(__name__)

    with app.test_request_context(
        headers={"Authorization": f"Bearer {json.dumps({'claims': {'email': 'a@b.com'}})}"},
    ):
        monkeypatch.setattr(
            "api.authz_engine.extract_user_lemma_principal",
            lambda _headers: (None, "missing"),
        )
        monkeypatch.setattr(
            "api.site_access.get_authenticated_ppid",
            lambda: None,
        )
        monkeypatch.setattr(
            "auth.decorators.extract_authenticated_ppid_from_request",
            lambda: None,
        )
        assert _verify_site_access("site_victim") is False


@pytest.mark.unit
def test_verify_site_access_accepts_customer_api_key(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import Site
    from api.permission_type_api import _verify_site_access

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    fake_ishuman_db_session_factory.store.data[Site.__name__].append(
        Site(
            site_id="site_perm_test",
            site_domain="perm.example.com",
            company_name="Perm",
            admin_email="ops@perm.example.com",
            api_key="lm_perm_site_key",
            oauth_client_id="oc_perm",
            oauth_client_secret="secret",
        )
    )
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (None, "missing"),
    )
    monkeypatch.setattr("api.site_access.get_authenticated_ppid", lambda: None)
    monkeypatch.setattr("auth.decorators.extract_authenticated_ppid_from_request", lambda: None)
    monkeypatch.setattr(
        "api.customer_accounts.customer_manager.validate_api_key",
        lambda key: {"valid": True, "site_id": "site_perm_test"} if key == "lm_customer_perm" else {"valid": False},
    )

    app = Flask(__name__)
    with app.test_request_context(headers={"Authorization": "Bearer lm_customer_perm"}):
        assert _verify_site_access("site_perm_test") is True
