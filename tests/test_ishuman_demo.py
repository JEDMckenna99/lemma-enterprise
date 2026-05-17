from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(name="ishuman_demo_client")
def fixture_ishuman_demo_client(fake_ishuman_db_session_factory, monkeypatch):
    from api.ishuman_demo import ishuman_demo_bp

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_demo_bp)
    with app.test_client() as client:
        yield client


def test_ishuman_demo_page_loads_expected_assets(ishuman_demo_client):
    resp = ishuman_demo_client.get("/demo/ishuman")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Verify once. Prove locally across sites." in body
    assert "/sdk/ishuman-verifier.js" in body
    assert "/static/js/demo/ishuman-demo.js" in body
    assert "Commercial deployment requires an approved IDV-provider path" in body


def test_ishuman_demo_config_seeds_sites_without_exposing_api_keys(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
):
    from api.database import Site

    resp = ishuman_demo_client.get("/api/demo/ishuman/config")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert {site["site_domain"] for site in payload["sites"]} == {
        "tickets-demo.lemma.id",
        "trials-demo.lemma.id",
    }
    assert all("api_key" not in site for site in payload["sites"])
    assert len(fake_ishuman_db_session_factory.store.data[Site.__name__]) == 2


def test_ishuman_demo_site_block_is_scoped_to_seeded_demo_site(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
):
    from api.database import SiteBlock

    ishuman_demo_client.get("/api/demo/ishuman/config")
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/site-block",
        json={
            "site_slug": "tickets",
            "ppid": "did:lemma:ppid_demo_ticket",
            "reason": "automated ticketing behavior",
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["site_id"] == "site_demo_tickets"
    blocks = fake_ishuman_db_session_factory.store.data[SiteBlock.__name__]
    assert len(blocks) == 1
    assert blocks[0].site_id == "site_demo_tickets"
    assert blocks[0].ppid == "did:lemma:ppid_demo_ticket"


def test_ishuman_demo_network_review_request_stays_site_scoped(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
):
    from api.database import SiteBlock

    ishuman_demo_client.get("/api/demo/ishuman/config")
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/network-revoke-request",
        json={
            "site_slug": "tickets",
            "ppid": "did:lemma:ppid_demo_ticket",
            "reason": "escalate demo block",
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["status"] == "pending_review"
    blocks = fake_ishuman_db_session_factory.store.data[SiteBlock.__name__]
    assert len(blocks) == 1
    assert blocks[0].site_id == "site_demo_tickets"
    assert blocks[0].network_revocation_requested is True
    assert blocks[0].network_revocation_status == "pending_review"


def test_ishuman_demo_network_approve_requires_demo_admin_token(ishuman_demo_client):
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/approve-network-revocation",
        json={"wallet_id": "wallet_demo_001"},
    )
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["error"] == "demo_admin_token_required"


def test_ishuman_demo_test_complete_requires_explicit_test_mode(ishuman_demo_client):
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/test-complete-verification",
        json={"session_id": "ishuman_sess_demo_001"},
    )
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["error"] == "test_verify_disabled"


def test_ishuman_demo_test_complete_verifies_pending_session_when_guarded(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    from api.database import IsHumanVerification

    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__].append(
        make_ishuman_verification(
            session_id="ishuman_sess_demo_001",
            stripe_session_id="vs_test_demo_001",
            wallet_id="wallet_demo_001",
            credential_id=None,
            ppid=None,
            status="pending",
            verified_at=None,
            issued_at=None,
            expires_at=None,
        )
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_test_complete",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None: {
            "id": "ishuman_master_test_complete",
            "issuerInfo": {"did": "did:lemma:issuer:test"},
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id", "expiresAt": "4102444800"},
            "subject": ppid,
        },
    )

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/test-complete-verification",
        headers={"X-Demo-Test-Token": "test-token"},
        json={"session_id": "ishuman_sess_demo_001"},
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["credential_id"] == "ishuman_master_test_complete"
    row = fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__][0]
    assert row.status == "verified"
    assert row.ppid == "did:lemma:ppid_test_complete"


def test_ishuman_demo_network_approve_revokes_demo_wallet_when_token_matches(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    make_derived_credential,
    monkeypatch,
):
    from api.database import IsHumanVerification, DerivedCredential, RevocationList

    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "demo-token")
    fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__].append(
        make_ishuman_verification(
            wallet_id="wallet_demo_001",
            credential_id="ishuman_master_demo_001",
            status="verified",
        )
    )
    fake_ishuman_db_session_factory.store.data[DerivedCredential.__name__].append(
        make_derived_credential(
            wallet_id="wallet_demo_001",
            master_credential_id="ishuman_master_demo_001",
            derived_credential_id="ishuman_site_demo_tickets_001",
            target_site="tickets-demo.lemma.id",
            derived_ppid="did:lemma:ppid_demo_ticket",
        )
    )

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/approve-network-revocation",
        headers={"X-Demo-Admin-Token": "demo-token"},
        json={"wallet_id": "wallet_demo_001", "master_credential_id": "ishuman_master_demo_001"},
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert "wallet_demo_001" in payload["revoked_credential_ids"]
    assert "ishuman_master_demo_001" in payload["revoked_credential_ids"]
    assert "ishuman_site_demo_tickets_001" in payload["revoked_credential_ids"]
    assert fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__][0].status == "revoked"
    assert fake_ishuman_db_session_factory.store.data[DerivedCredential.__name__][0].is_active is False
    assert len(fake_ishuman_db_session_factory.store.data[RevocationList.__name__]) == 3


def test_ishuman_demo_js_uses_real_verifier_with_two_site_bindings():
    js = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")

    assert "new window.IsHumanVerifier" in js
    assert "tickets-demo.lemma.id" in js
    assert "trials-demo.lemma.id" in js
    assert "lemmaOrigin: window.location.origin" in js
    assert "/api/ishuman/start-verification" in js
    assert "/api/ishuman/verification-status/" in js
