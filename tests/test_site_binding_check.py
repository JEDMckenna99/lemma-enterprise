"""Tests for GET /api/ishuman/site-binding-check."""

from __future__ import annotations

import pytest
from flask import Flask


@pytest.fixture(name="binding_client")
def fixture_binding_client(fake_ishuman_db_session_factory, monkeypatch):
    from api.database import Site
    from api.ishuman import ishuman_bp

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)

    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="site_binding_test",
            site_domain="app.example.com",
            company_name="Example",
            admin_email="ops@example.com",
            api_key="lm_test_binding_key",
            oauth_client_id="oc_test",
            oauth_client_secret="secret",
        )
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_bp)
    with app.test_client() as client:
        yield client


@pytest.mark.unit
def test_binding_check_canonicalizes_hostname(binding_client):
    resp = binding_client.get(
        "/api/ishuman/site-binding-check",
        query_string={"hostname": "https://WWW.App.Example.com/path"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["canonical_hostname"] == "app.example.com"
    assert body["sdk_siteId_hint"] == "app.example.com"
    assert body["registered"] is True
    assert body["site_id"] == "site_binding_test"


@pytest.mark.unit
def test_binding_check_unregistered(binding_client):
    resp = binding_client.get(
        "/api/ishuman/site-binding-check",
        query_string={"hostname": "other.example.com"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["registered"] is False
    assert body["site_id"] is None


@pytest.mark.unit
def test_binding_check_rejects_internal_site_id(binding_client):
    resp = binding_client.get(
        "/api/ishuman/site-binding-check",
        query_string={"hostname": "site_abc123"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "internal_site_id_not_allowed"
