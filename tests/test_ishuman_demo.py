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
    resp = ishuman_demo_client.get("/demo")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "One lemma.id. A different private ID on every site." in body
    assert "passkey-protected private proof container" in body
    assert "Human proofs + lemma.id demo" in body
    assert "Get started" in body
    assert "View developer docs" in body
    assert "/static/img/lemma_logo.svg" in body
    assert "ih-control-outcome-banner" in body
    assert "demo-outcome-footer" in body
    assert "ih-get-started" in body
    assert "ih-run-quick-demo" not in body
    assert "ih-quick-progress" not in body
    assert "ih-quick-insight" not in body
    assert "Why integrators use lemma.id" in body
    assert 'id="ih-advanced-panel"' in body
    assert "Advanced — operator tools" in body
    assert "1. Create your lemma.id" in body
    assert "2. Verify on two sites" in body
    assert "3. Enforce on your site" in body
    assert "Choose the assurance your flow requires" in body
    assert "Add a human proof to your lemma.id" in body
    assert "ih-human-cta" in body
    assert "free" not in body.split("demo-workflow")[1].split("demo-outcome-footer")[0].lower()
    assert "ih-step-rotation" not in body
    assert "ih-step-human" in body
    assert "ih-simulate-rotation-btn" not in body
    assert "ih-wallet-slots" in body
    assert "ih-abuse-block-btn" in body
    assert "ih-trials-ishuman-toggle" in body
    assert "Trials requires human proof" in body
    assert "ih-raise-tickets-policy-btn" in body
    assert "ih-complete-human-main-btn" in body
    assert "ih-control-escalation" in body
    assert "One lemma.id → different private IDs per site" in body
    assert "demo-diagram-stage" in body
    assert "demo-diagram-footnotes" in body
    assert "ih-proof-receipt" in body
    # Standalone open-site CTA removed — each site card carries its own link.
    assert "ih-link-tickets-main" not in body
    assert "Quick demo" not in body
    assert "Integrator demo" not in body
    assert "Step 5 — Revoke on one site" not in body
    assert "verifyForBackend" in body
    assert "demo-workflow" in body
    assert "Operations Check" in body
    assert "ih-operations-check" in body
    assert "ih-run-all-operations" in body
    assert "Developer details" not in body
    assert "Advanced integrator walkthrough" not in body
    assert "Advanced / Developer details" not in body
    assert "Run full guided demo" not in body
    assert "ih-run-guided-demo" not in body
    assert "autoProvision: true" in body
    assert "ih-step-1" in body
    assert "ih-step1-primary-btn" in body
    assert "ih-step1-continue-banner" in body
    assert "Your lemma.id is ready" in body
    assert "ih-create-lemma-btn" not in body
    assert "ih-unlock-lemma-btn" not in body
    assert "ih-network-pill" not in body
    assert "ih-verify-tickets-btn" in body
    assert "ih-verify-trials-btn" in body
    assert "Verify on ticketing site" in body
    assert "ih-verify-sites-btn" in body
    assert "ih-link-tickets-step2" in body
    assert "ih-link-trials-step2" in body
    assert "ih-verify-tickets-step2" in body
    assert "ih-verify-trials-step2" in body
    assert "Open ticketing demo →" in body
    assert "Open trials demo →" in body
    adv_start = body.index('id="ih-advanced-panel"')
    assert body.index("ih-verify-tickets-btn") > adv_start
    step2_start = body.index('id="ih-step-2"')
    chapter2_start = body.index("<!-- Act 3")
    assert "ih-verify-tickets-btn" not in body[step2_start:chapter2_start]
    assert "ih-verify-tickets-step2" in body[step2_start:chapter2_start]
    assert "ih-verify-trials-step2" in body[step2_start:chapter2_start]
    assert "Test-mode automation" not in body
    assert "Unlock wallet" not in body
    assert "ih-try-qr-demo-btn" not in body
    assert "Popup &amp; redirect UI preview" not in body
    assert "Start live demo" not in body
    assert "id=\"lemma-demo\"" in body
    assert "/sdk/ishuman-verifier.js" in body
    assert "/static/js/demo/ishuman-demo.js" in body
    assert "/static/css/demo/ishuman-demo.css" in body
    assert "/static/js/demo/ishuman-demo.js?v=58" in body
    assert "/static/css/demo/ishuman-demo.css?v=32" in body
    assert "\U0001f511" not in body
    assert "\U0001f6e1" not in body
    assert "site-card-icon" in body
    assert "ticket drops" in body or "SaaS trials" in body
    assert "ih-simulation-banner" not in body
    assert "Staging simulation only" not in body
    assert "ih-start-simulated-demo" not in body
    assert 'data-quick-act="3"' not in body
    assert 'data-quick-act="4"' not in body
    assert 'data-quick-act="5"' not in body
    human_start = body.index('id="ih-step-human"')
    adv_start = body.index('id="ih-advanced-panel"')
    assert body.index("ih-stepup-compare") < adv_start
    assert human_start < adv_start


def test_ishuman_demo_js_has_no_rotation_simulation():
    # The rotation simulation was cut from the demo narrative; the backend
    # rotation-check endpoint remains but the page no longer calls it.
    js = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")
    assert "/api/demo/ishuman/rotation-check" not in js
    assert "simulateRotation" not in js
    assert "raiseTicketsPolicySimulated" in js


def test_ishuman_demo_rotation_check_unknown_site(ishuman_demo_client):
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/rotation-check",
        json={"site_slug": "unknown", "ppids": ["did:lemma:ppid_test"]},
    )
    payload = resp.get_json()
    assert resp.status_code == 404
    assert payload["error"] == "unknown demo site"


def test_ishuman_demo_rotation_check_requires_ppids(ishuman_demo_client):
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/rotation-check",
        json={"site_slug": "tickets", "ppids": []},
    )
    payload = resp.get_json()
    assert resp.status_code == 400
    assert payload["error"] == "ppids required"


def test_ishuman_demo_rotation_check_reads_block_state(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
):
    from api.database import SiteBlock

    ishuman_demo_client.get("/api/demo/ishuman/config")
    blocked_ppid = "did:lemma:ppid_rotation_blocked"
    fresh_ppid = "did:lemma:ppid_rotation_fresh"
    ishuman_demo_client.post(
        "/api/demo/ishuman/site-block",
        json={"site_slug": "tickets", "ppid": blocked_ppid, "reason": "demo"},
    )

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/rotation-check",
        json={"site_slug": "tickets", "ppids": [blocked_ppid, fresh_ppid]},
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["results"][blocked_ppid]["blocked"] is True
    assert payload["results"][fresh_ppid]["blocked"] is False
    blocks = fake_ishuman_db_session_factory.store.data[SiteBlock.__name__]
    assert len(blocks) == 1


def test_ishuman_demo_js_exposes_quick_demo_entrypoint():
    js = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")
    assert "async function runQuickDemo()" in js
    assert "window.runQuickDemo = runQuickDemo" in js
    assert "ensureRealLemmaId" in js
    assert "waitForWalletId" in js
    assert "function renderProofReceipt()" in js
    assert "lemma_demo_ui_mode" not in js


def test_legacy_developer_ishuman_url_redirects_to_canonical_developer(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/developer/ishuman", follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["Location"].endswith("/developer")


def test_ishuman_demo_js_preserves_ppid_when_backend_denies():
    js = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")
    assert "resolveDisplayedPpid" in js
    assert "await resolveDisplayedPpid(verifier, backend, slug, options, requiredAssurance)" in js
    resolver = js.split("async function resolveDisplayedPpid", 1)[1].split("async function verifySite", 1)[0]
    assert "raw?.ppid" in resolver
    assert "resolveSitePpid(slug)" in resolver
    assert "function resolveSitePpid" in js
    assert "state.localBlocks[slug]" in js


def test_legacy_demo_ishuman_url_redirects_to_canonical_demo(ishuman_demo_client):
    resp = ishuman_demo_client.get("/demo/ishuman", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/demo")


def test_demo_create_button_always_enters_live_issuance():
    source = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")
    block = source.split("function createLemmaIdViaPopup()", 1)[1]
    block = block.split("// Cross-origin storage wipe", 1)[0]

    assert "Create lemma.id skipped" not in block
    assert block.index("setDemoMode('live')") < block.index("openIdvPopup")
    assert "passkey_setup" in block


def test_ishuman_demo_config_omits_retired_network_revocation(ishuman_demo_client):
    resp = ishuman_demo_client.get("/api/demo/ishuman/config")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert "network_revocation_enabled" not in payload
    assert "network_revoke_configured" not in payload


def test_ishuman_demo_page_never_shows_retired_network_revoke(
    ishuman_demo_client, monkeypatch,
):
    monkeypatch.setenv("LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED", "1")
    resp = ishuman_demo_client.get("/demo/ishuman", follow_redirects=True)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "ih-network-pill" not in body
    assert "Revoke everywhere" not in body
    assert "Network revocation drill" not in body


def test_ishuman_idv_popup_page_loads(ishuman_demo_client):
    resp = ishuman_demo_client.get("/wallet/ishuman-idv?origin=https%3A%2F%2Fexample.com&site_id=tickets-demo.lemma.id")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Prove you're human" in body or "Verify once" in body
    assert "ishuman-idv-preview-scenes.js" in body
    assert "LemmaIdvConsumerCopy" in body
    assert "lemma-keys.js" in body
    assert "wallet-at-rest-crypto.js" in body
    assert "lemma-wallet.js" in body
    assert "ISHUMAN_IDV_COMPLETE" in body


def test_ishuman_idv_popup_does_not_enable_test_verify_on_production(
    ishuman_demo_client,
    monkeypatch,
):
    """Production must use live Didit IDV, not the demo verify-once shortcut."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "prod-leak-token")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED", "true")

    resp = ishuman_demo_client.get(
        "/wallet/ishuman-idv?origin=https%3A%2F%2Fexample.com&site_id=trials-demo.lemma.id"
    )
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'data-test-verify-enabled="false"' in body


def test_ishuman_demo_config_disables_test_verify_on_production(
    ishuman_demo_client,
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")

    resp = ishuman_demo_client.get("/api/demo/ishuman/config")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["test_verify_enabled"] is False


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
    monkeypatch,
):
    from api.database import SiteBlock

    monkeypatch.setenv("LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED", "1")
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

    assert resp.status_code == 410
    assert payload["error"] == "network_revocation_retired"
    blocks = fake_ishuman_db_session_factory.store.data[SiteBlock.__name__]
    assert blocks == []


def test_ishuman_demo_network_review_disabled_by_default(ishuman_demo_client):
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/network-revoke-request",
        json={
            "site_slug": "tickets",
            "ppid": "did:lemma:ppid_demo_ticket",
            "reason": "escalate demo block",
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 410
    assert payload["error"] == "network_revocation_retired"


def test_ishuman_demo_network_approve_requires_demo_admin_token(ishuman_demo_client, monkeypatch):
    monkeypatch.setenv("LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED", "1")
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/approve-network-revocation",
        json={"wallet_id": "wallet_demo_001"},
    )
    payload = resp.get_json()

    assert resp.status_code == 410
    assert payload["error"] == "network_revocation_retired"


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
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
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
    # The demo completion path derives a real person-root PPID from the test
    # fixture (no longer the monkeypatched _derive_ppid_for_site), so assert the
    # canonical did:lemma:ppid_<hex> shape rather than a brittle literal.
    assert row.ppid.startswith("did:lemma:ppid_")
    assert len(row.ppid) == len("did:lemma:ppid_") + 64


def test_ishuman_demo_network_approve_revokes_demo_wallet_when_token_matches(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    make_derived_credential,
    monkeypatch,
):
    from api.database import IsHumanVerification, RevocationList

    monkeypatch.setenv("LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED", "1")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "demo-token")
    fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__].append(
        make_ishuman_verification(
            wallet_id="wallet_demo_001",
            credential_id="ishuman_master_demo_001",
            status="verified",
        )
    )
    fake_ishuman_db_session_factory.store.data["DerivedCredential"].append(
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

    assert resp.status_code == 410
    assert payload["error"] == "network_revocation_retired"
    assert fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__][0].status == "verified"
    assert fake_ishuman_db_session_factory.store.data["DerivedCredential"][0].is_active is True
    assert len(fake_ishuman_db_session_factory.store.data[RevocationList.__name__]) == 0


def test_ishuman_demo_js_uses_real_verifier_with_two_site_bindings():
    js = (ROOT / "static" / "js" / "demo" / "ishuman-demo.js").read_text(encoding="utf-8")

    assert "new window.IsHumanVerifier" in js
    assert "tickets-demo.lemma.id" in js
    assert "trials-demo.lemma.id" in js
    assert "lemmaOrigin: window.location.origin" in js
    assert "autoProvision: true" in js
    assert "runGuidedDemo" in js
    assert "runAllOperations" in js
    assert "runPreflightCheck" in js
    assert "assertSamePpidAfterStepUp" in js
    assert "assertSiteScopedRevocation" in js
    assert "/api/demo/ishuman/relying-site-preflight" in js
    assert "/api/demo/ishuman/verify-once-test-mode" in js
    assert "/api/demo/ishuman/probe-derive" in js
    assert "verifyForBackend" in js
    assert "/api/demo/ishuman/require-ishuman" in js
    assert "headers: demoHeaders()" in js
    assert "createLemmaIdViaPopup" in js
    assert "startLiveDemo" in js
    assert "startSimulatedDemo" not in js
    assert "/api/ishuman/start-verification" in js
    assert "/api/ishuman/verification-status/" in js


def test_ishuman_demo_verify_once_requires_test_mode(ishuman_demo_client):
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/verify-once-test-mode",
        json={"wallet_id": "wallet_demo_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "test_verify_disabled"


def test_ishuman_demo_verify_once_requires_token_header(ishuman_demo_client, monkeypatch):
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/verify-once-test-mode",
        json={"wallet_id": "wallet_demo_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "demo_test_token_required"


def test_ishuman_demo_test_complete_blocked_when_environment_is_production(
    ishuman_demo_client,
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/test-complete-verification",
        headers={"X-Demo-Test-Token": "test-token"},
        json={"session_id": "ishuman_sess_demo_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "prod_test_verify_forbidden"


def test_ishuman_demo_page_omits_tokens_on_production(ishuman_demo_client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "super-secret-test-token")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "super-secret-admin-token")

    resp = ishuman_demo_client.get("/demo/ishuman", follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "super-secret-test-token" not in body
    assert "super-secret-admin-token" not in body


def test_ishuman_demo_test_complete_requires_stripe_test_key_when_flag_enabled(
    ishuman_demo_client,
    monkeypatch,
):
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_should_fail")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/test-complete-verification",
        headers={"X-Demo-Test-Token": "test-token"},
        json={"session_id": "ishuman_sess_demo_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "stripe_test_key_required"


def test_ishuman_demo_probe_derive_requires_credentials(ishuman_demo_client):
    ishuman_demo_client.get("/api/demo/ishuman/config")
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/probe-derive",
        json={"site_slug": "tickets"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["code"] == "wallet_assertion_required"


def test_ishuman_demo_force_reverify_requires_ppid(ishuman_demo_client):
    ishuman_demo_client.get("/api/demo/ishuman/config")
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/force-reverify",
        json={},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["code"] == "wallet_assertion_required"


def test_skeleton_idv_flow_issues_short_lived_credential(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")
    monkeypatch.setenv("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED", "true")
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_skeleton",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, ttl_seconds=None, **kwargs: {
            "id": "ishuman_master_skeleton_test",
            "issuerInfo": {"did": "did:lemma:issuer:test"},
            "claims": {
                "isHuman": True,
                "siteId": site_id or "lemma.id",
                "expiresAt": str(int(__import__("time").time()) + (ttl_seconds or 900)),
            },
            "subject": ppid,
        },
    )

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/skeleton-idv-flow",
        headers={"X-Demo-Test-Token": "test-token"},
        json={
            "wallet_id": "wallet_skeleton_demo_001",
            "wallet_secret": "ab" * 32,
            "credential_ttl_seconds": 900,
            "complete_immediately": True,
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["session_id"].startswith("ishuman_skeleton_")
    assert payload["credential_id"]
    assert payload["credential"]["claims"]["expiresAt"]
    assert payload["credential_ttl_seconds"] == 900


def test_skeleton_idv_blocked_on_production(ishuman_demo_client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/skeleton-idv-flow",
        headers={"X-Demo-Test-Token": "test-token"},
        json={"wallet_id": "wallet_skeleton_demo_002"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "skeleton_idv_disabled"


def test_qr_demo_idv_flow_prepares_skeleton_session(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")
    monkeypatch.setenv("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_QR_CREDENTIAL_TTL_SECONDS", "900")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/qr-demo-idv-flow",
        headers={"X-Demo-Test-Token": "test-token"},
        json={
            "wallet_id": "wallet_qr_demo_001",
            "wallet_secret": "ab" * 32,
            "return_url": "https://lemma.id/wallet/ishuman-idv?verification_return=true",
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["session_id"].startswith("ishuman_skeleton_")
    assert payload["mode"] == "qr_demo_idv_flow"
    assert payload["credential_ttl_seconds"] == 900


def test_qr_demo_idv_enabled_on_production_with_explicit_flag(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "test-token")

    config = ishuman_demo_client.get("/api/demo/ishuman/config").get_json()
    assert config["qr_demo_idv_enabled"] is True
    assert config["skeleton_idv_enabled"] is False

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/qr-demo-idv-flow",
        headers={"X-Demo-Test-Token": "test-token"},
        json={
            "wallet_id": "wallet_qr_prod_001",
            "return_url": "https://lemma.id/wallet/ishuman-idv?verification_return=true",
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["mode"] == "qr_demo_idv_flow"


def test_ishuman_demo_config_exposes_assurance_flags(ishuman_demo_client, monkeypatch):
    monkeypatch.setenv("LEMMA_ONE_PPID_ASSURANCE_MODEL", "1")
    monkeypatch.setenv("LEMMA_PASSKEY_ASSURANCE_ENABLED", "1")
    resp = ishuman_demo_client.get("/api/demo/ishuman/config")
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["one_ppid_enabled"] is True
    assert payload["passkey_assurance_enabled"] is True
    assert payload["assurance_demo_mode"] is True


def test_require_ishuman_requires_demo_admin_token(ishuman_demo_client, monkeypatch):
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "demo-admin-token")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/require-ishuman",
        json={"site_slug": "tickets", "ppid": "did:lemma:ppid_demo_ticket"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "demo_admin_token_required"


def test_require_ishuman_creates_site_doubt(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import Site, SiteDoubt

    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "demo-admin-token")
    fake_ishuman_db_session_factory.store.data[Site.__name__] = [
        Site(
            site_id="site_demo_tickets",
            site_domain="tickets-demo.lemma.id",
            company_name="Demo Tickets",
            admin_email="demo@lemma.id",
            api_key="test",
        )
    ]
    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/require-ishuman",
        headers={"X-Demo-Admin-Token": "demo-admin-token"},
        json={"site_slug": "tickets", "ppid": "did:lemma:ppid_demo_ticket"},
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["doubt_required"] is True
    rows = fake_ishuman_db_session_factory.store.data[SiteDoubt.__name__]
    assert len(rows) == 1
    assert rows[0].is_active is True


def test_assurance_status_unbound_wallet(ishuman_demo_client):
    resp = ishuman_demo_client.get(
        "/api/demo/ishuman/assurance-status?wallet_id=wallet_unbound_demo",
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["person_bound"] is False
    assert payload["provisional"] is False
