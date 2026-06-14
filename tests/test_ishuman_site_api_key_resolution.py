"""Tests for unified isHuman site API key resolution."""

from __future__ import annotations

import pytest
from flask import Flask


@pytest.fixture(name="site_key_client")
def fixture_site_key_client(fake_ishuman_db_session_factory, monkeypatch):
    from api.database import Site
    from api.ishuman import ishuman_bp

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)

    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="site_key_legacy",
            site_domain="legacy.example.com",
            company_name="Legacy",
            admin_email="ops@legacy.example.com",
            api_key="lm_legacy_direct_key",
            oauth_client_id="oc_legacy",
            oauth_client_secret="secret",
        )
    )
    store.data[Site.__name__].append(
        Site(
            site_id="site_key_customer",
            site_domain="customer.example.com",
            company_name="Customer",
            admin_email="ops@customer.example.com",
            api_key="lm_old_unused_key",
            oauth_client_id="oc_customer",
            oauth_client_secret="secret",
        )
    )

    def _validate(api_key: str):
        if api_key == "lm_customer_issued_key":
            return {"valid": True, "site_id": "site_key_customer"}
        return {"valid": False, "error": "Invalid API key"}

    monkeypatch.setattr("api.customer_accounts.customer_manager.validate_api_key", _validate)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_bp)
    with app.test_client() as client:
        yield client, fake_ishuman_db_session_factory


@pytest.mark.unit
def test_site_block_accepts_legacy_sites_api_key(site_key_client, monkeypatch):
    client, _factory = site_key_client
    monkeypatch.setattr(
        "api.site_ppid_revocation.revoke_site_bound_ppid",
        lambda *args, **kwargs: {"block_id": 1, "block_created": True, "event_published": True},
    )

    resp = client.post(
        "/api/ishuman/site-block",
        headers={"X-API-Key": "lm_legacy_direct_key", "Content-Type": "application/json"},
        json={"ppid": "did:lemma:ppid_" + ("a" * 64), "reason": "test"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


@pytest.mark.unit
def test_site_block_accepts_customer_issued_api_key(site_key_client, monkeypatch):
    client, factory = site_key_client
    from api.database import Site

    monkeypatch.setattr(
        "api.site_ppid_revocation.revoke_site_bound_ppid",
        lambda *args, **kwargs: {"block_id": 2, "block_created": True, "event_published": True},
    )

    resp = client.post(
        "/api/ishuman/site-block",
        headers={"X-API-Key": "lm_customer_issued_key", "Content-Type": "application/json"},
        json={"ppid": "did:lemma:ppid_" + ("b" * 64), "reason": "test"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    site = factory.store.data[Site.__name__][1]
    assert site.api_key == "lm_customer_issued_key"


@pytest.mark.unit
def test_site_block_rejects_invalid_key(site_key_client):
    client, _factory = site_key_client
    resp = client.post(
        "/api/ishuman/site-block",
        headers={"X-API-Key": "lm_invalid", "Content-Type": "application/json"},
        json={"ppid": "did:lemma:ppid_" + ("c" * 64), "reason": "test"},
    )
    assert resp.status_code == 401
