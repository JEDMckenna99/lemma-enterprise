import os
import sys

from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.agent_credentials import require_agent_or_user_session  # noqa: E402
import api.agent_credentials as agent_credentials  # noqa: E402


def _make_session_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"

    @app.route("/api/agent/credentials", methods=["GET"])
    @require_agent_or_user_session(required_scope="read")
    def _list_credentials():
        return jsonify({"success": True}), 200

    return app


def test_forged_lemma_header_without_valid_signature_rejected(monkeypatch):
    app = _make_session_app()
    monkeypatch.setattr(
        agent_credentials,
        "extract_user_lemma_principal",
        lambda headers: (None, "invalid_lemma"),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))
    monkeypatch.setattr(agent_credentials, "_try_wallet_delegation_principal", lambda: None)

    with app.test_client() as client:
        resp = client.get(
            "/api/agent/credentials",
            headers={"X-Lemma-Credential": "not-a-valid-credential"},
        )
        assert resp.status_code == 401


def test_wallet_delegation_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LEMMA_ALLOW_WALLET_DELEGATION", raising=False)
    assert agent_credentials._try_wallet_delegation_principal() is None
