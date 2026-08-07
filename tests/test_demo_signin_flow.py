"""Dogfooded Sign in with lemma.id demo flow ( /demo ) routing and markup."""

from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(name="demo_client")
def fixture_demo_client(fake_ishuman_db_session_factory, monkeypatch):
    from api.ishuman_demo import ishuman_demo_bp

    monkeypatch.setattr(
        "api.database.SessionLocal", fake_ishuman_db_session_factory.session_local
    )
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_demo_bp)
    with app.test_client() as client:
        yield client


def test_demo_is_the_dogfooded_signin_flow(demo_client):
    resp = demo_client.get("/demo")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'data-mock="0"' in body
    # All flow states present in the markup (signed-in goes straight to manager).
    assert 'id="sf-state-create"' in body
    assert 'id="sf-state-signin"' in body
    assert 'id="sf-state-success"' not in body
    assert 'id="sf-state-gate"' in body
    assert 'id="sf-state-manager"' in body
    assert 'sf-open-manager-btn' not in body
    # Real SDK, not the mock driver.
    assert "/sdk/proof-verifier.js" in body
    assert "signin-flow.js" in body
    # Site binding is a hostname, never an internal site_... id.
    assert 'data-site-id="site_' not in body
    # Builder hub is linked, not inlined.
    assert "/demo/how-it-works" in body


def test_demo_how_it_works_serves_builder_hub(demo_client):
    resp = demo_client.get("/demo/how-it-works")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "ih-lifecycle-panel" in body


def test_demo_mock_is_design_review_only(demo_client, monkeypatch):
    resp = demo_client.get("/demo/mock")
    assert resp.status_code == 200
    assert 'data-mock="1"' in resp.get_data(as_text=True)

    monkeypatch.setenv("ENVIRONMENT", "production")
    prod = demo_client.get("/demo/mock", follow_redirects=False)
    assert prod.status_code == 302
    assert prod.headers["Location"].endswith("/demo")


def test_dev_root_pubkey_never_exposed_in_production(demo_client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LEMMA_DEV_INSECURE_ISSUER", "1")
    resp = demo_client.get("/demo")
    body = resp.get_data(as_text=True)
    assert 'data-dev-root-pubkey=""' in body


def test_flow_narration_panels_shared_with_manager():
    """The demo's manager preview and /app render the same panels include."""
    signin = (ROOT / "templates" / "demo" / "signin.html").read_text(encoding="utf-8")
    manager = (ROOT / "templates" / "wallet_simple.html").read_text(encoding="utf-8")
    panels = (ROOT / "templates" / "demo" / "_signin_panels.html").read_text(
        encoding="utf-8"
    )

    assert 'include "demo/_signin_panels.html"' in signin
    assert 'include "demo/_signin_panels.html"' in manager
    assert "show_signin_panels" in manager
    assert 'id="sf-manager-panels"' in panels
    # The compare rows must not use *.lemma.id subdomains: derivePPID
    # short-circuits those to the platform credential's PPID.
    assert "tickets-demo.lemma.id</dt>" not in panels
    assert "a-ticket-shop.example" in panels
    assert "a-news-site.example" in panels


def test_signin_flow_js_uses_sdk_and_session_endpoint():
    js = (ROOT / "static" / "js" / "demo" / "signin-flow.js").read_text(
        encoding="utf-8"
    )

    # Real driver: SDK verify + POST the presentation to the session endpoint.
    assert "verifyForBackend" in js
    assert "autoProvision: true" in js
    assert "requiredAssurance: 'passkey'" in js
    assert "'/api/auth/session'" in js
    assert "X-Lemma-CSRF" in js
    # Create continues into session mint so the user lands signed in.
    assert "postSession" in js
    assert "signedIn" in js
    assert "openManager()" in js
    # The signed presentation is sent; a bare ppid never is.
    assert "presentation: presentation" in js
    assert "JSON.stringify({ ppid" not in js
