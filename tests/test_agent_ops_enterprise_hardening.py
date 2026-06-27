import json
import os
import sys

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import api.services.wallet_service as wallet_service
from api.authz_control_plane import _revocation_shape_fields


def _wallet_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(wallet_service.wallet_service_bp)
    return app


def test_revocation_shape_fields_maps_proof_and_token():
    proof_shape = _revocation_shape_fields("prf_123", None)
    assert proof_shape["subject_type"] == "proof"
    assert proof_shape["proof_id"] == "prf_123"
    assert "prf_123" in proof_shape["ancestor_ids"]

    token_shape = _revocation_shape_fields("token:agt_live_1", "token")
    assert token_shape["subject_type"] == "token"
    assert token_shape["token_id"] == "agt_live_1"
    assert "agt_live_1" in token_shape["ancestor_ids"]


def test_runtime_authorize_denies_stale_taint_epoch(monkeypatch):
    app = _wallet_app()
    events = []
    monkeypatch.setattr(wallet_service, "_extract_ppid_from_lemma_header", lambda: "did:lemma:ppid_" + ("a" * 64))
    monkeypatch.setattr(
        wallet_service,
        "_extract_lemma_trust_claims",
        lambda: {
            "taint_epoch": 2,
            "step_up_required": False,
            "scope": ["api.internal.admin"],
            "credential_id": "prf_stale_1",
        },
    )
    monkeypatch.setattr(
        wallet_service,
        "_runtime_record_for_ppid",
        lambda **kwargs: {
            "active": True,
            "policy_profile": "lemma_firewall_default_v1",
            "risk_defaults": {},
            "trust_state": "tainted_external",
            "taint_epoch": 3,
        },
    )
    def _record_events(payload):
        events.extend(payload)

    monkeypatch.setattr(wallet_service, "record_agent_ops_decision_logs", _record_events)

    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/lemma-firewall-default/authorize",
            json={"action": "api.internal.admin"},
        )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "deny_taint_epoch_stale"
    assert events
    assert events[-1]["metadata_json"]["reason_code"] == "deny_taint_epoch_stale"


def test_runtime_authorize_denies_when_step_up_required(monkeypatch):
    app = _wallet_app()
    events = []
    monkeypatch.setattr(wallet_service, "_extract_ppid_from_lemma_header", lambda: "did:lemma:ppid_" + ("a" * 64))
    monkeypatch.setattr(
        wallet_service,
        "_extract_lemma_trust_claims",
        lambda: {
            "taint_epoch": 3,
            "step_up_required": True,
            "scope": ["api.internal.admin"],
            "credential_id": "prf_step_up_1",
        },
    )
    monkeypatch.setattr(
        wallet_service,
        "_runtime_record_for_ppid",
        lambda **kwargs: {
            "active": True,
            "policy_profile": "lemma_firewall_default_v1",
            "risk_defaults": {},
            "trust_state": "privileged_reauth_required",
            "taint_epoch": 3,
        },
    )
    def _record_events(payload):
        events.extend(payload)

    monkeypatch.setattr(wallet_service, "record_agent_ops_decision_logs", _record_events)

    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/lemma-firewall-default/authorize",
            json={"action": "api.internal.admin"},
        )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "deny_trust_state_step_up_required"
    assert events
    assert events[-1]["metadata_json"]["reason_code"] == "deny_trust_state_step_up_required"


def test_runtime_authorize_allows_current_taint_epoch(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "_extract_ppid_from_lemma_header", lambda: "did:lemma:ppid_" + ("b" * 64))
    monkeypatch.setattr(
        wallet_service,
        "_extract_lemma_trust_claims",
        lambda: {
            "taint_epoch": 9,
            "step_up_required": False,
            "scope": ["api.internal.admin"],
            "credential_id": "prf_fresh_1",
        },
    )
    monkeypatch.setattr(
        wallet_service,
        "_runtime_record_for_ppid",
        lambda **kwargs: {
            "active": True,
            "policy_profile": "lemma_firewall_default_v1",
            "risk_defaults": {"critical": "deny"},
            "trust_state": "tainted_external",
            "taint_epoch": 9,
        },
    )
    monkeypatch.setattr(wallet_service, "record_agent_ops_decision_logs", lambda payload: payload)

    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/lemma-firewall-default/authorize",
            json={"action": "api.internal.admin"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["trust_state"] == "tainted_external"
    assert body["taint_epoch"] == 9


def test_wallet_firewall_runtimes_and_decisions_omit_wallet_id(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "validate_session_token", lambda token: None)
    monkeypatch.setattr(wallet_service, "validate_unlock_token", lambda token: {"wallet_id": "wallet_hidden"})
    monkeypatch.setattr(wallet_service, "_resolve_wallet_ppid", lambda wallet_id: "did:lemma:ppid_" + ("c" * 64))
    monkeypatch.setattr(wallet_service, "_list_firewall_runtimes", lambda **kwargs: [])
    monkeypatch.setattr(wallet_service, "list_agent_ops_decisions", lambda **kwargs: [])

    headers = {"X-Lemma-Unlock": "unlock_test_token"}
    with app.test_client() as client:
        runtimes_resp = client.get("/api/wallet/runtimes", headers=headers)
        decisions_resp = client.get("/api/wallet/runtimes/decisions", headers=headers)
        legacy_runtimes_resp = client.get("/api/wallet/firewall/runtimes", headers=headers)

    assert runtimes_resp.status_code == 200
    assert decisions_resp.status_code == 200
    assert legacy_runtimes_resp.status_code == 200
    assert legacy_runtimes_resp.headers.get("Deprecation") == "true"
    assert "wallet_id" not in (runtimes_resp.get_json() or {})
    assert "wallet_id" not in (decisions_resp.get_json() or {})


def test_decision_export_includes_delegation_lineage(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "validate_session_token", lambda token: None)
    monkeypatch.setattr(wallet_service, "validate_unlock_token", lambda token: {"wallet_id": "wallet_hidden"})
    monkeypatch.setattr(wallet_service, "_resolve_wallet_ppid", lambda wallet_id: "did:lemma:ppid_" + ("d" * 64))
    monkeypatch.setattr(
        wallet_service,
        "list_agent_ops_decisions",
        lambda **kwargs: [
            {
                "decision_id": 1,
                "timestamp": "2026-01-01T00:00:00Z",
                "credential_ref": "agt_1",
                "action": "runtime.authorize",
                "resource": "lemma-firewall-default",
                "method": "POST",
                "path": "/api/wallet/runtimes/lemma-firewall-default/authorize",
                "status_code": 200,
                "decision": "allow",
                "reason_code": "ALLOW",
                "policy_profile": "lemma_firewall_default_v1",
                "runtime_id": "lemma-firewall-default",
                "delegator_ppid": "did:lemma:ppid_" + ("d" * 64),
                "request_correlation_id": "req_1",
                "delegation_lineage": {"delegation_id": "dlg_1"},
            }
        ],
    )
    headers = {"X-Lemma-Unlock": "unlock_test_token"}
    with app.test_client() as client:
        json_resp = client.get("/api/wallet/runtimes/decisions/export?format=json", headers=headers)
        csv_resp = client.get("/api/wallet/runtimes/decisions/export?format=csv", headers=headers)

    assert json_resp.status_code == 200
    payload = json_resp.get_json()
    assert payload["decisions"][0]["delegation_lineage"]["delegation_id"] == "dlg_1"

    assert csv_resp.status_code == 200
    csv_text = csv_resp.data.decode("utf-8")
    assert "delegation_lineage" in csv_text.splitlines()[0]
    assert "wallet_id" not in json.dumps(payload)


def test_wallet_runtime_list_propagates_tenant_scope(monkeypatch):
    app = _wallet_app()
    captured: dict[str, str] = {}
    monkeypatch.setattr(wallet_service, "validate_session_token", lambda token: None)
    monkeypatch.setattr(wallet_service, "validate_unlock_token", lambda token: {"wallet_id": "wallet_hidden"})
    monkeypatch.setattr(wallet_service, "_resolve_wallet_ppid", lambda wallet_id: "did:lemma:ppid_" + ("e" * 64))

    def _capture_list(**kwargs):
        captured["org_id"] = str(kwargs.get("org_id") or "")
        captured["environment"] = str(kwargs.get("environment") or "")
        return []

    monkeypatch.setattr(wallet_service, "_list_firewall_runtimes", _capture_list)
    headers = {
        "X-Lemma-Unlock": "unlock_test_token",
        "X-Lemma-Org-Id": "tenant_alpha",
        "X-Lemma-Environment": "staging",
    }
    with app.test_client() as client:
        resp = client.get("/api/wallet/runtimes", headers=headers)
    assert resp.status_code == 200
    assert captured["org_id"] == "tenant_alpha"
    assert captured["environment"] == "staging"


def test_wallet_decisions_propagate_tenant_scope(monkeypatch):
    app = _wallet_app()
    captured: dict[str, str] = {}
    monkeypatch.setattr(wallet_service, "validate_session_token", lambda token: None)
    monkeypatch.setattr(wallet_service, "validate_unlock_token", lambda token: {"wallet_id": "wallet_hidden"})
    monkeypatch.setattr(wallet_service, "_resolve_wallet_ppid", lambda wallet_id: "did:lemma:ppid_" + ("f" * 64))
    monkeypatch.setattr(wallet_service, "_list_firewall_runtimes", lambda **kwargs: [])

    def _capture_decisions(**kwargs):
        captured["org_id"] = str(kwargs.get("org_id") or "")
        captured["environment"] = str(kwargs.get("environment") or "")
        return []

    monkeypatch.setattr(wallet_service, "list_agent_ops_decisions", _capture_decisions)
    headers = {
        "X-Lemma-Unlock": "unlock_test_token",
        "X-Lemma-Org-Id": "tenant_beta",
        "X-Lemma-Environment": "dev",
    }
    with app.test_client() as client:
        resp = client.get("/api/wallet/runtimes/decisions", headers=headers)
    assert resp.status_code == 200
    assert captured["org_id"] == "tenant_beta"
    assert captured["environment"] == "dev"


def test_wallet_issue_proof_includes_tenant_and_root_type(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "validate_session_token", lambda token: None)
    monkeypatch.setattr(wallet_service, "validate_unlock_token", lambda token: {"wallet_id": "wallet_hidden"})
    monkeypatch.setattr(wallet_service, "_resolve_firewall_identity_ppid", lambda wallet_id: "did:lemma:ppid_" + ("1" * 64))
    monkeypatch.setattr(
        wallet_service,
        "_resolve_platform_role_for_ppid",
        lambda ppid, site_id: {
            "role": "admin",
            "permission_id": "admin_access",
            "scope": ["read", "write", "admin"],
            "source": "test",
        },
    )
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        wallet_service,
        "_build_firewall_proof_chain_artifact",
        lambda **kwargs: captured.update(
            {
                "root_type": str(kwargs.get("root_type") or ""),
                "org_id": str(kwargs.get("org_id") or ""),
                "environment": str(kwargs.get("environment") or ""),
            }
        )
        or {"root_proof": {}, "delegated_proof": {}, "proof_chain": []},
    )

    class _FakeSiteManager:
        def __init__(self):
            self.permissions = {}

        def add_permission(self, _payload):
            return None

        def issue_permission_lemma(self, **_kwargs):
            return {"id": "cred_test_issue", "permission_id": "admin_access"}

    import api.real_iam_manager as real_iam_manager

    monkeypatch.setattr(real_iam_manager, "get_site_manager", lambda _sid, _domain: _FakeSiteManager())
    monkeypatch.setattr(real_iam_manager, "get_or_create_site_manager", lambda _sid, _domain: _FakeSiteManager())

    headers = {
        "X-Lemma-Unlock": "unlock_test_token",
        "X-Lemma-Org-Id": "tenant_gamma",
        "X-Lemma-Environment": "staging",
    }
    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/issue-proof",
            headers=headers,
            json={"site_id": "lemma.id", "root_type": "workload_root"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["root_type"] == "workload_root"
    assert body["org_id"] == "tenant_gamma"
    assert body["environment"] == "staging"
    assert captured["root_type"] == "workload_root"
    assert captured["org_id"] == "tenant_gamma"
    assert captured["environment"] == "staging"


def test_wallet_issue_proof_maps_runtime_id_to_agent_key(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "validate_session_token", lambda token: None)
    monkeypatch.setattr(wallet_service, "validate_unlock_token", lambda token: {"wallet_id": "wallet_hidden"})
    monkeypatch.setattr(wallet_service, "_resolve_firewall_identity_ppid", lambda wallet_id: "did:lemma:ppid_" + ("2" * 64))
    monkeypatch.setattr(
        wallet_service,
        "_resolve_platform_role_for_ppid",
        lambda ppid, site_id: {
            "role": "admin",
            "permission_id": "admin_access",
            "scope": ["read", "write", "admin"],
            "source": "test",
        },
    )
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        wallet_service,
        "_build_firewall_proof_chain_artifact",
        lambda **kwargs: captured.update({"agent_key_id": str(kwargs.get("agent_key_id") or "")})
        or {"root_proof": {}, "delegated_proof": {}, "proof_chain": []},
    )

    class _FakeSiteManager:
        def __init__(self):
            self.permissions = {}

        def add_permission(self, _payload):
            return None

        def issue_permission_lemma(self, **_kwargs):
            return {"id": "cred_test_issue", "permission_id": "admin_access"}

    import api.real_iam_manager as real_iam_manager

    monkeypatch.setattr(real_iam_manager, "get_site_manager", lambda _sid, _domain: _FakeSiteManager())
    monkeypatch.setattr(real_iam_manager, "get_or_create_site_manager", lambda _sid, _domain: _FakeSiteManager())

    headers = {"X-Lemma-Unlock": "unlock_test_token"}
    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/issue-proof",
            headers=headers,
            json={
                "site_id": "lemma.id",
                "runtime_id": "openclaw-default",
                "task_id": "TASK-42",
                "granted_by": "agent_ops_ui",
            },
        )
    assert resp.status_code == 200
    assert captured["agent_key_id"] == "openclaw-default"
