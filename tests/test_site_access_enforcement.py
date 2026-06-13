import os
import sys

from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.agent_credentials import require_agent_or_user_auth  # noqa: E402
from api.site_access import require_site_ownership  # noqa: E402
import api.site_access as site_access  # noqa: E402


OWNER_PPID = "did:lemma:ppid_" + ("a" * 64)
OTHER_PPID = "did:lemma:ppid_" + ("b" * 64)
PROOF_HEADER = {"X-Lemma-Proof": "{}"}
CREDENTIAL_HEADER = {"X-Lemma-Credential": "{}"}


def _proof_env(monkeypatch):
    monkeypatch.setenv("LEMMA_AUTHZ_PROOF_SHADOW", "0")


def _make_test_app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/api/developer/sites/<site_id>/users", methods=["GET", "POST"])
    @require_agent_or_user_auth(required_scope="read")
    def _users(site_id):
        denied = require_site_ownership(site_id)
        if denied:
            return denied
        return jsonify({"success": True, "site_id": site_id}), 200

    return app


def test_non_owner_ppid_rejected(monkeypatch):
    app = _make_test_app()
    _proof_env(monkeypatch)
    monkeypatch.setattr(
        site_access,
        "verify_site_ownership",
        lambda site_id, ppid: ppid == OWNER_PPID,
    )

    from api.authz_engine import AuthzPrincipal
    import api.agent_credentials as agent_credentials

    monkeypatch.setattr(
        agent_credentials,
        "extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid=OTHER_PPID,
                credential_id="cred_other",
                permission_id="admin_access",
                scope=["admin", "read"],
                site_binding="site_abc",
            ),
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))
    monkeypatch.setattr(
        agent_credentials,
        "infer_requested_site_ids",
        lambda: ["site_abc"],
    )

    with app.test_client() as client:
        resp = client.get("/api/developer/sites/site_abc/users", headers=PROOF_HEADER)
        assert resp.status_code == 403
        payload = resp.get_json()
        assert payload.get("code") == "UNAUTHORIZED_SITE_ACCESS"


def test_owner_ppid_allowed(monkeypatch):
    app = _make_test_app()
    _proof_env(monkeypatch)
    monkeypatch.setattr(
        site_access,
        "verify_site_ownership",
        lambda site_id, ppid: ppid == OWNER_PPID,
    )

    from api.authz_engine import AuthzPrincipal
    import api.agent_credentials as agent_credentials

    monkeypatch.setattr(
        agent_credentials,
        "extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid=OWNER_PPID,
                credential_id="cred_owner",
                permission_id="admin_access",
                scope=["admin", "read"],
                site_binding="site_abc",
            ),
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))
    monkeypatch.setattr(
        agent_credentials,
        "infer_requested_site_ids",
        lambda: ["site_abc"],
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/developer/sites/site_abc/users",
            headers={**PROOF_HEADER, **CREDENTIAL_HEADER},
        )
        assert resp.status_code == 200
        assert resp.get_json()["site_id"] == "site_abc"
