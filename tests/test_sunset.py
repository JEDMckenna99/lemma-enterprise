from __future__ import annotations

import pytest


@pytest.fixture(name="sunset_client")
def fixture_sunset_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("LEMMA_SUNSET", "1")
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.mark.integration
def test_sunset_serves_tombstone_on_product_pages(sunset_client):
    resp = sunset_client.get("/", headers={"Accept": "text/html"})
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "lemma.id has shut down" in body
    assert "privacy@lemma.id" in body
    assert "Get Started" not in body


@pytest.mark.integration
def test_sunset_keeps_privacy_and_health(sunset_client):
    privacy = sunset_client.get("/privacy", headers={"Accept": "text/html"})
    assert privacy.status_code == 200
    assert "Privacy Policy" in privacy.get_data(as_text=True)

    health = sunset_client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "healthy"


@pytest.mark.integration
def test_sunset_closes_apis_and_sdk(sunset_client):
    api = sunset_client.post("/api/ishuman/verify-presentation", json={})
    assert api.status_code == 410
    assert api.get_json()["error"] == "service_shutdown"

    sdk = sunset_client.get("/sdk/proof-verifier.js")
    assert sdk.status_code == 410
