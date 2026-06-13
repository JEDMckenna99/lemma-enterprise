import os
import sys

from flask import Flask, jsonify

# pylint: disable=protected-access

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.agent_credentials import require_agent_or_user_auth, require_agent_or_user_session  # noqa: E402
from api.authz_engine import AuthzPrincipal  # noqa: E402
import api.agent_credentials as agent_credentials  # noqa: E402


PROOF_HEADER = {"X-Lemma-Proof": "{}"}


def _proof_env(monkeypatch):
    monkeypatch.setenv("LEMMA_AUTHZ_PROOF_SHADOW", "0")


def _make_test_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"

    @app.route("/api/developer/sites/<site_id>/bootstrap-admin", methods=["POST"])
    @require_agent_or_user_auth()
    def _bootstrap(site_id):
        return jsonify({"success": True, "site_id": site_id}), 200

    # Compat-bearer admin route (auth_mode defaults to compat_bearer) used to
    # exercise scope/principal/decision-header logic without the proof_required
    # mode gate that critical routes like bootstrap-admin now enforce.
    @app.route("/api/developer/sites/<site_id>/keys", methods=["POST"])
    @require_agent_or_user_auth()
    def _create_key(site_id):
        return jsonify({"success": True, "site_id": site_id}), 200

    @app.route("/api/auth/introspect", methods=["POST"])
    @require_agent_or_user_auth()
    def _introspect():
        return jsonify({"success": True}), 200

    @app.route("/api/agent/credentials/issue", methods=["POST"])
    @require_agent_or_user_session()
    def _issue():
        return jsonify({"success": True}), 200

    return app


def test_user_lemma_missing_scope_rejected_by_policy(monkeypatch):
    app = _make_test_app()
    _proof_env(monkeypatch)

    monkeypatch.setattr(
        agent_credentials,
        "extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid="did:lemma:ppid_" + ("a" * 64),
                credential_id="cred_test",
                permission_id="customer_access",
                scope=["read"],
                site_binding="lemma.id",
            ),
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))

    with app.test_client() as client:
        resp = client.post("/api/developer/sites/lemma.id/keys", headers=PROOF_HEADER)
        assert resp.status_code == 403
        payload = resp.get_json()
        assert payload["error"] == "missing_scope"
        assert payload["required_scope"] == ["admin"]


def test_user_lemma_principal_not_allowed_for_api_key_only_route(monkeypatch):
    app = _make_test_app()

    monkeypatch.setattr(
        agent_credentials,
        "extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid="did:lemma:ppid_" + ("b" * 64),
                credential_id="cred_test_2",
                permission_id="admin_access",
                scope=["admin", "write", "read"],
                site_binding="lemma.id",
            ),
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))

    with app.test_client() as client:
        resp = client.post("/api/auth/introspect")
        assert resp.status_code == 403
        payload = resp.get_json()
        assert payload["error"] == "principal_not_allowed"


def test_api_key_allowed_for_api_key_only_route(monkeypatch):
    app = _make_test_app()

    monkeypatch.setattr(agent_credentials, "extract_user_lemma_principal", lambda headers: (None, "missing_lemma_header"))
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (True, {"type": "platform"}))

    with app.test_client() as client:
        resp = client.post("/api/auth/introspect", headers={"X-API-Key": "lm_test_key"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


def test_api_key_rejected_on_developer_key_create(monkeypatch):
    app = _make_test_app()
    _proof_env(monkeypatch)

    monkeypatch.setattr(agent_credentials, "extract_user_lemma_principal", lambda headers: (None, "missing_lemma_header"))
    monkeypatch.setattr(
        agent_credentials,
        "_validate_request_api_key",
        lambda api_key: (True, {"type": "customer", "site_id": "site_abc"}),
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/developer/sites/site_abc/keys",
            headers={"X-API-Key": "lm_site_key", **PROOF_HEADER},
        )
        assert resp.status_code == 403
        payload = resp.get_json()
        assert payload["error"] == "principal_not_allowed"
        assert "api_key" not in payload.get("allowed_principals", [])


def test_user_lemma_write_scope_allowed_for_issue_session_decorator(monkeypatch):
    app = _make_test_app()

    monkeypatch.setattr(
        agent_credentials,
        "extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid="did:lemma:ppid_" + ("c" * 64),
                credential_id="cred_test_3",
                permission_id="developer_access",
                scope=["write", "read"],
                site_binding="lemma.id",
            ),
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))

    with app.test_client() as client:
        resp = client.post("/api/agent/credentials/issue")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


def test_agent_token_allow_sets_decision_headers(monkeypatch):
    app = _make_test_app()
    _proof_env(monkeypatch)

    monkeypatch.setattr(
        agent_credentials,
        "validate_agent_token_with_reason",
        lambda token: (
            {
                "credential_id": 1,
                "token_id": "agt_test_1",
                "authorized_by_ppid": "did:lemma:ppid_" + ("d" * 64),
                "requested_by_ppid": "did:lemma:ppid_" + ("d" * 64),
                "acting_for_ppid": "did:lemma:ppid_" + ("d" * 64),
                "scope": ["admin", "write", "read"],
                "allowed_sites": None,
                "allowed_paths": None,
                "task_description": None,
                "task_hash": None,
                "max_operations": None,
                "use_count": 0,
                "task_deviation_count": 0,
                "audience": "lemma.id",
            },
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_enforce_route_policy_for_principal", lambda **kwargs: None)
    monkeypatch.setattr(agent_credentials, "check_site_allowed", lambda credential_info: (True, None, None, []))
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))

    with app.test_client() as client:
        resp = client.post(
            "/api/developer/sites/lemma.id/keys",
            headers={"X-Agent-Token": "lm_agent_test", **PROOF_HEADER},
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Lemma-Decision-Id")
        assert resp.headers.get("X-Lemma-Decision-Signature")


def test_agent_token_invalid_includes_decision_receipt(monkeypatch):
    app = _make_test_app()
    _proof_env(monkeypatch)

    monkeypatch.setattr(agent_credentials, "validate_agent_token_with_reason", lambda token: (None, "invalid_token"))
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))

    with app.test_client() as client:
        resp = client.post(
            "/api/developer/sites/lemma.id/keys",
            headers={"X-Agent-Token": "lm_agent_bad", **PROOF_HEADER},
        )
        assert resp.status_code == 401
        payload = resp.get_json()
        assert payload["error"] == "invalid_token"
        assert payload.get("decision", {}).get("decision_id")
        assert resp.headers.get("X-Lemma-Decision-Id")


def test_proof_required_route_does_not_fallback_to_bearer_on_invalid_proof(monkeypatch):
    app = _make_test_app()
    monkeypatch.setenv("LEMMA_ENFORCE_PROOF_REQUIRED", "1")
    monkeypatch.setattr(
        agent_credentials,
        "validate_agent_token_with_reason",
        lambda token: (
            {
                "credential_id": 1,
                "token_id": "agt_test_2",
                "authorized_by_ppid": "did:lemma:ppid_" + ("e" * 64),
                "scope": ["admin", "write", "read"],
                "allowed_sites": None,
                "allowed_paths": None,
            },
            None,
        ),
    )
    monkeypatch.setattr(agent_credentials, "_validate_request_api_key", lambda api_key: (False, {}))

    # Invalid proof body on proof_required route must deny and not fallback to valid bearer token.
    with app.test_client() as client:
        resp = client.post(
            "/api/developer/sites/lemma.id/bootstrap-admin",
            headers={
                "X-Agent-Token": "lm_agent_test",
                "X-Lemma-Proof": "not-base64-json",
            },
        )
        assert resp.status_code == 403
        payload = resp.get_json()
        assert payload["error"] in {"AUTH_CHAIN_BROKEN", "AUTH_PROOF_OF_POSSESSION_FAILED"}


def test_apply_operation_quota_uses_redis_for_max_operations(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.values = {}

        def incr(self, key):
            self.values[key] = int(self.values.get(key, 0)) + 1
            return self.values[key]

        def expire(self, _key, _ttl):
            return True

    fake_redis = FakeRedis()
    monkeypatch.setattr(agent_credentials, "get_redis_client", lambda: fake_redis)
    info = {
        "credential_id": 7,
        "base_use_count": 10,
        "use_count": 10,
        "max_operations": 12,
    }
    updated, err = agent_credentials._apply_operation_quota(info)
    assert err is None
    assert updated["use_count"] == 11
    assert updated["quota_source"] == "redis"
    updated, err = agent_credentials._apply_operation_quota(updated)
    assert err is None
    assert updated["use_count"] == 12


def test_apply_operation_quota_denies_when_max_operations_exceeded(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.values = {}

        def incr(self, key):
            self.values[key] = int(self.values.get(key, 0)) + 1
            return self.values[key]

        def expire(self, _key, _ttl):
            return True

    fake_redis = FakeRedis()
    monkeypatch.setattr(agent_credentials, "get_redis_client", lambda: fake_redis)
    info = {
        "credential_id": 9,
        "base_use_count": 2,
        "use_count": 2,
        "max_operations": 3,
    }
    updated, err = agent_credentials._apply_operation_quota(info)
    assert err is None
    assert updated["use_count"] == 3
    updated, err = agent_credentials._apply_operation_quota(updated)
    assert updated is None
    assert err == "max_operations_exceeded"
