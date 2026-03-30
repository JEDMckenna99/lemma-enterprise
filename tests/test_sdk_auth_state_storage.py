import urllib.parse

from flask import Flask

from api.sdk_auth import sdk_auth_bp


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(sdk_auth_bp)
    return app


def test_sdk_auth_state_is_one_time_consumed(monkeypatch):
    app = _build_app()
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
        login_redirect = start.headers["Location"]
        query = urllib.parse.urlparse(login_redirect).query
        state = urllib.parse.parse_qs(query)["sdk_state"][0]

        first_callback = client.get(f"/auth/sdk-callback?state={state}")
        assert first_callback.status_code == 302
        assert "lemma_auth=success" in first_callback.headers["Location"]

        replay_callback = client.get(f"/auth/sdk-callback?state={state}")
        assert replay_callback.status_code == 400
        payload = replay_callback.get_json()
        assert payload["error"] == "Invalid or expired session"

