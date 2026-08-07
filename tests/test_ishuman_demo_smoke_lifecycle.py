"""API-level smoke test mirroring the demo Operations Check lifecycle."""

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


@pytest.fixture(name="demo_control_auth")
def fixture_demo_control_auth(monkeypatch):
    def _fake(site_domain, presentation):
        if isinstance(presentation, dict):
            ppid = presentation.get("_test_ppid")
            if ppid:
                return str(ppid), None
        return None, "presentation_missing"

    monkeypatch.setattr("api.ishuman_demo._verified_ppid_from_presentation", _fake)


def _demo_control_body(slug: str, ppid: str, **extra) -> dict:
    presentation = {"credential": {"id": "test-control"}, "_test_ppid": ppid}
    body = {
        "site_slug": slug,
        "ppid": ppid,
        "presentation": presentation,
        "presentations": {
            "tickets": presentation,
            "trials": presentation,
        },
    }
    body.update(extra)
    return body


def test_demo_lifecycle_site_block_unblock_and_escalation(
    ishuman_demo_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    demo_control_auth,
):
    from api.database import Site, SiteBlock, SiteDoubt

    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN", "demo-admin-token")

    fake_ishuman_db_session_factory.store.data[Site.__name__] = [
        Site(
            site_id="site_demo_tickets",
            site_domain="lemma-demo-tickets-1d3d7411af33.herokuapp.com",
            company_name="Demo Tickets",
            admin_email="demo@lemma.id",
        ),
        Site(
            site_id="site_demo_trials",
            site_domain="lemma-demo-trials-7090f46cae0d.herokuapp.com",
            company_name="Demo Trials",
            admin_email="demo@lemma.id",
        ),
    ]

    ppid = "did:lemma:ppid_demo_lifecycle"

    config = ishuman_demo_client.get("/api/demo/ishuman/config").get_json()
    assert config["success"] is True
    assert {site["site_domain"] for site in config["sites"]} == {
        "lemma-demo-tickets-1d3d7411af33.herokuapp.com",
        "lemma-demo-trials-7090f46cae0d.herokuapp.com",
    }

    doubt = ishuman_demo_client.post(
        "/api/demo/ishuman/require-ishuman",
        headers={"X-Demo-Admin-Token": "demo-admin-token"},
        json={"site_slug": "tickets", "ppid": ppid},
    ).get_json()
    assert doubt["doubt_required"] is True
    assert len(fake_ishuman_db_session_factory.store.data[SiteDoubt.__name__]) == 1

    block = ishuman_demo_client.post(
        "/api/demo/ishuman/site-block",
        json=_demo_control_body("tickets", ppid, reason="smoke test block"),
    ).get_json()
    assert block["success"] is True
    assert block["site_id"] == "site_demo_tickets"
    blocks = fake_ishuman_db_session_factory.store.data[SiteBlock.__name__]
    assert len(blocks) == 1
    assert blocks[0].site_id == "site_demo_tickets"

    rotation = ishuman_demo_client.post(
        "/api/demo/ishuman/rotation-check",
        json={"site_slug": "tickets", "ppids": [ppid, "did:lemma:ppid_fresh_rotation"]},
    ).get_json()
    assert rotation["success"] is True
    assert rotation["results"][ppid]["blocked"] is True
    assert rotation["results"]["did:lemma:ppid_fresh_rotation"]["blocked"] is False


def test_relying_site_preflight_endpoint_shape(ishuman_demo_client, monkeypatch):
    def fake_preflight(_url, timeout=8):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                if "health" in _url:
                    return b'{"success": true, "site_id": "tickets-demo.lemma.id"}'
                return b'{"success": true, "site_id": "tickets-demo.lemma.id", "required_assurance": "passkey"}'

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_preflight)
    payload = ishuman_demo_client.get("/api/demo/ishuman/relying-site-preflight").get_json()

    assert payload["success"] is True
    assert payload["sites"]["tickets"]["success"] is True
    assert payload["sites"]["trials"]["success"] is True
