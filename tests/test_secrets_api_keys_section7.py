"""Section 7: secrets and API key consolidation tests."""

from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace

import pytest
from flask import Flask, g

pytestmark = pytest.mark.unit


@pytest.fixture(name="site_access_app")
def fixture_site_access_app():
    from api.site_access import authorize_site_access

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/api/test/site/<site_id>")
    def _protected(site_id):
        site, denied = authorize_site_access(site_id, allow_site_api_key=True)
        if denied:
            return denied
        return {"success": True, "site_id": site.site_id}, 200

    return app


def test_query_param_api_key_rejected(site_access_app):
    with site_access_app.test_client() as client:
        resp = client.get("/api/test/site/example.com?api_key=lm_query_only_key")
        assert resp.status_code == 401
        payload = resp.get_json()
        assert payload["code"] == "QUERY_PARAM_API_KEY_REJECTED"


def test_header_api_key_still_resolves(site_access_app, monkeypatch):
    site = SimpleNamespace(site_id="example.com", site_domain="example.com")

    monkeypatch.setattr(
        "api.site_access.resolve_site_from_api_key",
        lambda api_key=None: site if api_key == "lm_header_key" else None,
    )

    with site_access_app.test_client() as client:
        resp = client.get(
            "/api/test/site/example.com",
            headers={"X-API-Key": "lm_header_key"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["site_id"] == "example.com"


def test_generate_additional_api_key_persists_hash_only(monkeypatch):
    from api.customer_accounts import CustomerAccountManager

    manager = CustomerAccountManager.__new__(CustomerAccountManager)
    manager.db_available = False
    manager.api_key_to_customer = {}
    manager.customers = {
        "cus_test": SimpleNamespace(
            customer_id="cus_test",
            api_keys=[],
            status="active",
            name="Test",
            company="Co",
            subscription_status="none",
        )
    }
    manager.generate_api_key = lambda prefix="lm": "lm_section7_test_key_value"
    manager._store_customer_in_memory = lambda customer: None

    monkeypatch.setattr(
        "api.storage_helpers.upsert_api_key_to_postgres",
        lambda *args, **kwargs: True,
    )

    result = manager.generate_additional_api_key("cus_test", "Site Key", site_id="example.com")
    assert result["success"] is True
    assert result["api_key"] == "lm_section7_test_key_value"

    stored = manager.customers["cus_test"].api_keys[0]
    assert "key" not in stored
    assert stored["key_hash"] == hashlib.sha256(b"lm_section7_test_key_value").hexdigest()
    assert stored["key_hint"] == "ey_value"


def test_revoked_key_fails_validate_api_key(monkeypatch):
    from api.customer_accounts import CustomerAccountManager

    raw_key = "lm_active_then_revoked"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_data = {
        "key_hash": key_hash,
        "key_hint": raw_key[-8:],
        "site_id": "example.com",
        "status": "revoked",
        "name": "Revoked",
    }
    customer = SimpleNamespace(
        customer_id="cus_revoke",
        status="active",
        name="Test",
        company="Co",
        subscription_status="none",
        api_keys=[key_data],
    )

    manager = CustomerAccountManager.__new__(CustomerAccountManager)
    manager.db_available = False
    manager.api_key_to_customer = {key_hash: "cus_revoke"}
    manager.customers = {"cus_revoke": customer}
    manager.get_customer = lambda customer_id: manager.customers.get(customer_id)
    manager.get_customer_by_api_key = CustomerAccountManager.get_customer_by_api_key.__get__(manager)
    manager.hash_api_key = CustomerAccountManager.hash_api_key.__get__(manager)
    manager._apply_api_key_revocation = lambda entry: None

    validation = manager.validate_api_key(raw_key)
    assert validation["valid"] is False


def test_resolve_site_from_api_key_ignores_legacy_site_column(monkeypatch):
    from api.database import Site
    from api.site_access import resolve_site_from_api_key

    class _FakeQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return Site(
                site_id="legacy.example.com",
                site_domain="legacy.example.com",
                company_name="Legacy",
                admin_email="ops@legacy.example.com",
                api_key="lm_legacy_direct_key",
                oauth_client_id="oc_legacy",
                oauth_client_secret="secret",
            )

    class _FakeSession:
        def query(self, _model):
            return _FakeQuery()

        def close(self):
            return None

    monkeypatch.setattr("api.database.SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        "api.site_access.validate_site_api_key",
        lambda api_key=None: {"valid": False, "error": "Invalid API key"},
    )

    assert resolve_site_from_api_key("lm_legacy_direct_key") is None


def test_enforce_production_secret_distinctness_rejects_shared_values(monkeypatch):
    from api.config import LemmaSecrets, enforce_production_secret_distinctness

    monkeypatch.setattr("api.config.is_production", lambda: True)
    shared = "x" * 40
    secrets = LemmaSecrets.__new__(LemmaSecrets)
    secrets.flask_secret = shared
    secrets.oauth_jwt_secret = shared
    secrets.network_auth_key = "y" * 40
    secrets.ppid_root_key = "z" * 40
    secrets.identity_root_pepper = "a" * 40
    secrets.person_root_salt = "b" * 40
    secrets.billing_hmac_secret = "c" * 40
    secrets.hpke_server_key = "d" * 40
    secrets.wallet_salt = "e" * 40

    with pytest.raises(RuntimeError, match="must be distinct"):
        enforce_production_secret_distinctness(secrets)


def test_enforce_production_secret_distinctness_rejects_weak_default(monkeypatch):
    from api.config import LemmaSecrets, enforce_production_secret_distinctness

    monkeypatch.setattr("api.config.is_production", lambda: True)
    secrets = LemmaSecrets.__new__(LemmaSecrets)
    secrets.flask_secret = "dev-secret-key-for-testing"
    secrets.oauth_jwt_secret = "o" * 40
    secrets.network_auth_key = "n" * 40
    secrets.ppid_root_key = "p" * 40
    secrets.identity_root_pepper = "i" * 40
    secrets.person_root_salt = "r" * 40
    secrets.billing_hmac_secret = "b" * 40
    secrets.hpke_server_key = "h" * 40
    secrets.wallet_salt = "w" * 40

    with pytest.raises(RuntimeError, match="weak/default"):
        enforce_production_secret_distinctness(secrets)


def test_create_app_uses_config_secret_not_dev_default(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-32chars-minimum!!")
    monkeypatch.setenv("FLASK_ENV", "development")

    from importlib import reload
    import api.config as config_mod

    reload(config_mod)
    from app import create_app

    app = create_app()
    assert app.config["SECRET_KEY"] == "unit-test-secret-key-32chars-minimum!!"
    assert app.config["SECRET_KEY"] != "dev-secret-key-for-testing"
