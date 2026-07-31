"""Phase 0 CIAM hardening: retired OAuth, quarantined SDK callback."""

from __future__ import annotations

import os
import sys

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.permission_management_api as pma  # noqa: E402
from api.sdk_auth import sdk_auth_bp  # noqa: E402


def _permission_client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(pma.permission_api)
    return app.test_client()


def test_oauth_authorize_returns_410():
    client = _permission_client()
    resp = client.get(
        "/api/v1/oauth/authorize?client_id=lemma_oauth_site123&redirect_uri=https://example.com/cb"
    )
    assert resp.status_code == 410
    payload = resp.get_json()
    assert payload["code"] == "oauth_removed"


def test_oauth_token_returns_410():
    client = _permission_client()
    resp = client.post(
        "/api/v1/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": "auth_dead",
            "client_id": "lemma_oauth_site123",
            "client_secret": "secret",
        },
    )
    assert resp.status_code == 410
    payload = resp.get_json()
    assert payload["code"] == "oauth_removed"


def test_sdk_callback_does_not_emit_success(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(sdk_auth_bp)
    state_store = {}

    def _store(state, payload):
        state_store[state] = payload
        return True

    def _consume(state):
        return state_store.pop(state, None)

    monkeypatch.setattr("api.sdk_auth._store_pending_sdk_request", _store)
    monkeypatch.setattr("api.sdk_auth._consume_pending_sdk_request", _consume)

    with app.test_client() as client:
        start = client.get(
            "/auth/sdk-request?site=test.example.com&return=https://test.example.com/callback"
        )
        assert start.status_code == 302
        query = start.headers["Location"].split("?", 1)[1]
        import urllib.parse

        state = urllib.parse.parse_qs(query)["sdk_state"][0]

        first_callback = client.get(f"/auth/sdk-callback?state={state}")
        assert first_callback.status_code == 302
        assert "lemma_auth=error" in first_callback.headers["Location"]
        assert "callback_unbound" in first_callback.headers["Location"]
        assert "lemma_auth=success" not in first_callback.headers["Location"]

        replay_callback = client.get(f"/auth/sdk-callback?state={state}")
        assert replay_callback.status_code == 401
        assert replay_callback.get_json()["code"] == "callback_unbound"
