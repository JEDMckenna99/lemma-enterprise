import os
import sys

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from auth.bootstrap import require_site_bootstrap_api_key  # noqa: E402
import api.agent_credentials as agent_credentials  # noqa: E402


def test_site_bootstrap_api_key_accepts_x_api_key(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/api/v1/iam/admin/self-issue", methods=["POST"])
    @require_site_bootstrap_api_key
    def _self_issue():
        from flask import g, jsonify

        return jsonify({"success": True, "api_key": g.api_key}), 200

    monkeypatch.setattr(
        agent_credentials,
        "_validate_request_api_key",
        lambda api_key: (api_key == "lm_site_test_key", {"type": "customer", "site_id": "site_abc"}),
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/v1/iam/admin/self-issue",
            headers={"X-API-Key": "lm_site_test_key"},
            json={"user_email": "admin@example.com"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["api_key"] == "lm_site_test_key"
