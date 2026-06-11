"""Tests for admin Trust & Safety queue endpoints."""

from __future__ import annotations

import base64
import json
from datetime import datetime

import pytest
from flask import Flask


def _encode_lemma_header(lemma: dict) -> str:
    raw = json.dumps(lemma, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _admin_headers():
    lemma = {
        "id": "cred_admin_trust_test",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_" + ("a" * 64),
        "claims": {
            "siteId": "lemma.id",
            "permissionId": "admin_access",
            "scope": "admin,write,read",
        },
    }
    return {"X-Lemma-Credential": _encode_lemma_header(lemma)}


def _customer_headers():
    lemma = {
        "id": "cred_customer_trust_test",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_" + ("b" * 64),
        "claims": {
            "siteId": "lemma.id",
            "permissionId": "customer_access",
            "scope": "read",
        },
    }
    return {"X-Lemma-Credential": _encode_lemma_header(lemma)}


@pytest.fixture(name="admin_trust_client")
def fixture_admin_trust_client(fake_ishuman_db_session_factory, monkeypatch):
    from api.admin_trust import admin_trust_bp
    from api.ishuman import ishuman_bp

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": True, "reason": "ok"},
    )
    monkeypatch.setattr(
        "api.dashboard_api._load_admin_sites",
        lambda: [{"site_id": "site_demo_tickets", "site_domain": "tickets.demo.lemma.id"}],
    )
    monkeypatch.setattr("api.audit_logger.log_event", lambda *args, **kwargs: None)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_trust_bp)
    app.register_blueprint(ishuman_bp)
    with app.test_client() as client:
        yield client, fake_ishuman_db_session_factory


def _seed_pending_block(factory, ppid: str = "did:lemma:ppid_" + ("c" * 64)):
    from api.database import DerivedCredential, SiteBlock

    factory.store.data[SiteBlock.__name__].append(
        SiteBlock(
            id=1,
            site_id="site_demo_tickets",
            ppid=ppid,
            reason="bot activity",
            evidence_url="https://example.com/evidence",
            blocked_at=datetime.utcnow(),
            blocked_by="site_api",
            is_active=True,
            network_revocation_requested=True,
            network_revocation_status="pending_review",
        )
    )
    factory.store.data[DerivedCredential.__name__].append(
        DerivedCredential(
            id=1,
            master_credential_id="ishuman_master_test",
            derived_credential_id="ishuman_derived_test",
            wallet_id="wallet_trust_test",
            target_site="tickets.demo.lemma.id",
            derived_ppid=ppid,
            is_active=True,
            created_at=datetime.utcnow(),
        )
    )


def test_trust_queue_lists_pending_only(admin_trust_client):
    client, factory = admin_trust_client
    from api.database import SiteBlock

    _seed_pending_block(factory)
    factory.store.data[SiteBlock.__name__].append(
        SiteBlock(
            id=2,
            site_id="site_demo_tickets",
            ppid="did:lemma:ppid_" + ("d" * 64),
            reason="other",
            is_active=True,
            network_revocation_status="approved",
        )
    )

    resp = client.get("/api/admin/trust/queue", headers=_admin_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["total"] == 1
    assert body["queue"][0]["block_id"] == 1
    assert body["queue"][0]["wallet_id"] == "wallet_trust_test"


def test_trust_queue_rejects_non_admin(admin_trust_client):
    client, factory = admin_trust_client
    _seed_pending_block(factory)

    resp = client.get("/api/admin/trust/queue", headers=_customer_headers())
    assert resp.status_code == 403


def test_trust_queue_reject_sets_status(admin_trust_client):
    client, factory = admin_trust_client
    _seed_pending_block(factory)

    resp = client.post(
        "/api/admin/trust/queue/1/reject",
        headers={**_admin_headers(), "Content-Type": "application/json"},
        json={"reason": "insufficient evidence"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["status"] == "rejected"
    assert body["site_block_active"] is True

    from api.database import SiteBlock

    block = factory.store.data[SiteBlock.__name__][0]
    assert block.network_revocation_status == "rejected"
    assert block.is_active is True


def test_approve_revocation_with_block_id(admin_trust_client, monkeypatch):
    client, factory = admin_trust_client
    from api.database import IsHumanVerification

    ppid = "did:lemma:ppid_" + ("c" * 64)
    _seed_pending_block(factory, ppid=ppid)
    factory.store.data[IsHumanVerification.__name__].append(
        IsHumanVerification(
            id=1,
            session_id="ishuman_sess_trust",
            wallet_id="wallet_trust_test",
            ppid=ppid,
            credential_id="ishuman_master_test",
            status="verified",
            verified_at=datetime.utcnow(),
        )
    )

    published = []
    monkeypatch.setattr(
        "api.revocation_sync.get_event_bus",
        lambda: type("Bus", (), {"publish_revocation": lambda self, rid, credential_type=None: published.append(rid)})(),
    )
    monkeypatch.setattr("api.audit_logger.log_event", lambda *args, **kwargs: None)

    resp = client.post(
        "/api/ishuman/approve-revocation",
        headers={**_admin_headers(), "Content-Type": "application/json"},
        json={"block_id": 1, "reason": "confirmed abuse"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["wallet_id"] == "wallet_trust_test"
    assert body["total_revoked"] >= 1

    from api.database import SiteBlock

    assert factory.store.data[SiteBlock.__name__][0].network_revocation_status == "approved"


def test_ishuman_overview_route_auth(monkeypatch, fake_ishuman_db_session_factory):
    from api.dashboard_api import dashboard_bp

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": True, "reason": "ok"},
    )
    monkeypatch.setattr("api.dashboard_api._load_admin_sites", lambda: [])
    monkeypatch.setattr("api.dashboard_api._get_slo_snapshot", lambda: {})

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(dashboard_bp)

    with app.test_client() as client:
        ok = client.get("/api/admin/ishuman-overview", headers=_admin_headers())
        assert ok.status_code == 200
        assert ok.get_json()["success"] is True

        denied = client.get("/api/admin/ishuman-overview", headers=_customer_headers())
        assert denied.status_code == 403
