"""Public documentation exposes only the isHuman product."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_legacy_agent_docs_redirect_to_ishuman_docs(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        for path in (
            "/docs/agents",
            "/docs/overview",
            "/docs/quickstart",
            "/docs/installation",
            "/docs/cli",
            "/docs/api/auth",
            "/docs/examples",
        ):
            response = client.get(path, follow_redirects=True)
            assert response.status_code == 200
            assert response.request.path == "/docs"
            assert b"proof of humanity" in response.data.lower()
