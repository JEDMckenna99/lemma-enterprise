"""Tests for admin site detail and revoke endpoints."""

from __future__ import annotations

import base64
import json

import pytest
from flask import Flask


def _encode_lemma_header(lemma: dict) -> str:
    raw = json.dumps(lemma, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _admin_headers():
    lemma = {
        "id": "cred_admin_sites_test",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_" + ("d" * 64),
        "claims": {
            "siteId": "lemma.id",
            "permissionId": "admin_access",
            "scope": "admin,write,read",
        },
    }
    return {"X-Lemma-Credential": _encode_lemma_header(lemma)}


def _customer_headers():
    lemma = {
        "id": "cred_customer_sites_test",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_" + ("e" * 64),
        "claims": {
            "siteId": "lemma.id",
            "permissionId": "customer_access",
            "scope": "read",
        },
    }
    return {"X-Lemma-Credential": _encode_lemma_header(lemma)}


@pytest.fixture(name="admin_sites_client")
def fixture_admin_sites_client(monkeypatch):
    from api.admin_billing import admin_billing_bp
    from api.dashboard_api import dashboard_bp

    sample_site = {
        "site_id": "site_test_abc",
        "site_domain": "test.example.com",
        "company_name": "Test Co",
        "admin_email": "dev@test.example.com",
        "plan": "starter",
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
    }

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": True, "reason": "ok"},
    )
    monkeypatch.setattr("api.dashboard_api._load_admin_sites", lambda: [sample_site])
    monkeypatch.setattr(
        "api.dashboard_api._site_block_counts",
        lambda site_id: {"active_blocks_count": 1, "pending_review_count": 0},
    )
    monkeypatch.setattr("api.dashboard_api._site_activity_count", lambda site_id, domain: 3)
    monkeypatch.setattr("api.dashboard_api.get_monthly_active_users", lambda site_id: 42)
    monkeypatch.setattr("api.dashboard_api._lookup_stripe_customer_for_site", lambda site: "cus_test123")
    monkeypatch.setattr("api.audit_logger.log_event", lambda *args, **kwargs: None)

    class FakeCursor:
        rowcount = 1

        def execute(self, *args, **kwargs):
            return None

        def close(self):
            return None

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("psycopg2.connect", lambda url: FakeConn())
    monkeypatch.setenv("DATABASE_URL", "postgres://test")

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_billing_bp)
    with app.test_client() as client:
        yield client


def test_get_admin_site_detail(admin_sites_client):
    resp = admin_sites_client.get("/api/admin/sites/site_test_abc", headers=_admin_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["site"]["site_id"] == "site_test_abc"
    assert body["site"]["mau_current"] == 42
    assert body["site"]["active_blocks_count"] == 1


def test_get_admin_site_detail_not_found(admin_sites_client):
    resp = admin_sites_client.get("/api/admin/sites/missing_site", headers=_admin_headers())
    assert resp.status_code == 404


def test_revoke_admin_site(admin_sites_client):
    resp = admin_sites_client.post(
        "/api/admin/sites/site_test_abc/revoke",
        headers={**_admin_headers(), "Content-Type": "application/json"},
        json={"reason": "test revoke"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["status"] == "suspended"


def test_admin_site_routes_require_admin(admin_sites_client):
    resp = admin_sites_client.get("/api/admin/sites/site_test_abc", headers=_customer_headers())
    assert resp.status_code == 403


def test_billing_summary(admin_sites_client):
    resp = admin_sites_client.get("/api/admin/billing/summary", headers=_admin_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["total_sites"] == 1
    assert body["sites"][0]["mau_current"] == 42
