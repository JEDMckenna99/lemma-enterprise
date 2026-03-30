import json
import sys
import types

from scripts import lemma_firewall as firewall


def _sample_lemma_credential(scope=None, actions=None, taint_epoch=None):
    payload = {
        "id": "cred_localops_1",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_test",
        "claims": {
            "scope": scope or ["read", "write"],
            "site_id": "lemma.id",
        },
    }
    if actions is not None:
        payload["claims"]["actions"] = actions
    if taint_epoch is not None:
        payload["claims"]["taint_epoch"] = taint_epoch
    return json.dumps(payload)


def _setup_base(monkeypatch, credential_scope=None, credential_actions=None, taint_epoch=None):
    """Common test fixture: disable sync, clear caches, stub credential validation."""
    firewall.LOCAL_OPS_GATE_ENABLED = True
    firewall.LOCAL_OPS_LOG_DECISIONS = False
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = set()
    firewall.PROOF_REQUIRED_TIERS = set()
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall.ONLINE_CHECK_ON_STALE_NONCRITICAL = False
    firewall.TAINT_ENFORCEMENT_ENABLED = False
    firewall.PASSKEY_AGE_ENFORCEMENT_ENABLED = False
    firewall._SYNC_STATE["revoked_credential_ids"] = set()
    firewall._SYNC_STATE["revoked_proof_ids"] = set()
    firewall._SYNC_STATE["revoked_root_grant_ids"] = set()
    firewall._SYNC_STATE["min_revocation_epoch"] = 0
    firewall._RUNTIME_STATE_CACHE.clear()
    firewall._RUNTIME_AUTHZ_CACHE.clear()
    firewall._LOCAL_OPS_COUNTERS["allow"] = 0
    firewall._LOCAL_OPS_COUNTERS["deny"] = 0

    result_payload = {
        "scope": credential_scope or ["read", "write"],
        "credential_id": "cred_localops_1",
    }
    if credential_actions is not None:
        result_payload["actions"] = credential_actions
    if taint_epoch is not None:
        result_payload["taint_epoch"] = taint_epoch

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(
        firewall,
        "_validate_lemma_credential",
        lambda _cred: (True, dict(result_payload)),
    )


# ---------------------------------------------------------------------------
# Basic allow / deny
# ---------------------------------------------------------------------------

def test_authorize_allows_read_action(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"])
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed"] is True
    assert body["action"] == "file.read"
    assert body["resource"] == "/src/main.py"
    assert body["risk"] == "low"
    assert body["required_scope"] == "read"
    assert body.get("decision_id", "").startswith("lop_")


def test_authorize_denies_missing_auth(monkeypatch):
    _setup_base(monkeypatch)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/etc/passwd"},
    )
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "missing_auth"


def test_authorize_rejects_missing_action(monkeypatch):
    _setup_base(monkeypatch)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"resource": "/foo"},
        headers={"X-Lemma-Credential": _sample_lemma_credential()},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "action_required"


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------

def test_authorize_denies_insufficient_scope(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read"])
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.write", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read"])},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "insufficient_scope"
    assert body["required_scope"] == "write"


def test_authorize_allows_admin_scope_for_critical_action(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["admin", "write", "read"])
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "shell.exec", "resource": "rm -rf /tmp/test"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["admin", "write", "read"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed"] is True
    assert body["risk"] == "critical"


# ---------------------------------------------------------------------------
# Action taxonomy enforcement with path bounds
# ---------------------------------------------------------------------------

def test_authorize_denies_action_not_in_actions_map(monkeypatch):
    actions = {"file.read": True, "file.list": True}
    _setup_base(monkeypatch, credential_scope=["read", "write"], credential_actions=actions)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.write", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "action_not_granted"


def test_authorize_denies_action_outside_path_bounds(monkeypatch):
    actions = {
        "file.read": True,
        "file.write": {"paths": ["/src/**"]},
    }
    _setup_base(monkeypatch, credential_scope=["read", "write"], credential_actions=actions)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.write", "resource": "/etc/shadow"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "action_not_granted"
    assert body["reason"] == "action_path_not_allowed"


def test_authorize_allows_action_within_path_bounds(monkeypatch):
    actions = {
        "file.read": True,
        "file.write": {"paths": ["/src/**"]},
    }
    _setup_base(monkeypatch, credential_scope=["read", "write"], credential_actions=actions)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.write", "resource": "/src/utils/helpers.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed"] is True


# ---------------------------------------------------------------------------
# Revocation enforcement
# ---------------------------------------------------------------------------

def test_authorize_denies_revoked_credential(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"])
    firewall._SYNC_STATE["revoked_credential_ids"] = {"cred_localops_1"}
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "revoked_credential_local"


# ---------------------------------------------------------------------------
# Runtime kill switch
# ---------------------------------------------------------------------------

def test_authorize_denies_killed_runtime(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"])
    auth_payload = {"scope": ["read", "write"], "credential_id": "cred_localops_1"}
    firewall._runtime_state_update(
        runtime_id="lemma-firewall-default",
        auth_payload=auth_payload,
        active=False,
        source="test_kill",
    )
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "runtime_inactive_local"


# ---------------------------------------------------------------------------
# Taint epoch enforcement
# ---------------------------------------------------------------------------

def test_authorize_denies_stale_taint_epoch(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"], taint_epoch=5)
    firewall.TAINT_ENFORCEMENT_ENABLED = True
    with firewall._SYNC_LOCK:
        firewall._RUNTIME_TAINT_CACHE["lemma-firewall-default"] = 10
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["error"] == "proof_taint_epoch_stale"
    assert body["proof_taint_epoch"] == 5
    assert body["runtime_taint_epoch"] == 10


def test_authorize_allows_current_taint_epoch(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"], taint_epoch=10)
    firewall.TAINT_ENFORCEMENT_ENABLED = True
    with firewall._SYNC_LOCK:
        firewall._RUNTIME_TAINT_CACHE["lemma-firewall-default"] = 10
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/src/main.py"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed"] is True


# ---------------------------------------------------------------------------
# Local ops gate disabled
# ---------------------------------------------------------------------------

def test_authorize_passthrough_when_gate_disabled(monkeypatch):
    _setup_base(monkeypatch)
    firewall.LOCAL_OPS_GATE_ENABLED = False
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "shell.exec", "resource": "rm -rf /"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["allowed"] is True
    assert body["reason"] == "local_ops_gate_disabled"


# ---------------------------------------------------------------------------
# Unknown action defaults to critical/admin
# ---------------------------------------------------------------------------

def test_authorize_unknown_action_defaults_critical(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read"])
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "custom.dangerous.thing", "resource": "/foo"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read"])},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["allowed"] is False
    assert body["risk"] == "critical"
    assert body["error"] == "insufficient_scope"


# ---------------------------------------------------------------------------
# Risk override
# ---------------------------------------------------------------------------

def test_authorize_respects_risk_override(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"])
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/src/main.py", "risk": "critical"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["risk"] == "critical"


# ---------------------------------------------------------------------------
# Batch authorization
# ---------------------------------------------------------------------------

def test_batch_authorize_mixed_results(monkeypatch):
    actions = {"file.read": True, "file.list": True}
    _setup_base(monkeypatch, credential_scope=["read", "write"], credential_actions=actions)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize/batch",
        json={
            "operations": [
                {"action": "file.read", "resource": "/src/main.py"},
                {"action": "file.write", "resource": "/src/main.py"},
            ]
        },
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["results"]) == 2
    assert body["results"][0]["allowed"] is True
    assert body["results"][1]["allowed"] is False
    assert body["all_allowed"] is False


def test_batch_authorize_all_allowed(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read", "write"])
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize/batch",
        json={
            "operations": [
                {"action": "file.read", "resource": "/a.txt"},
                {"action": "file.list", "resource": "/src"},
            ]
        },
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read", "write"])},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["all_allowed"] is True
    assert all(r["allowed"] for r in body["results"])


def test_batch_authorize_rejects_empty(monkeypatch):
    _setup_base(monkeypatch)
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize/batch",
        json={"operations": []},
        headers={"X-Lemma-Credential": _sample_lemma_credential()},
    )
    assert resp.status_code == 400


def test_batch_authorize_passthrough_when_disabled(monkeypatch):
    _setup_base(monkeypatch)
    firewall.LOCAL_OPS_GATE_ENABLED = False
    client = firewall.APP.test_client()
    resp = client.post(
        "/aim/authorize/batch",
        json={"operations": [{"action": "shell.exec", "resource": "rm -rf /"}]},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["all_allowed"] is True


# ---------------------------------------------------------------------------
# Decision counters
# ---------------------------------------------------------------------------

def test_decision_counters_increment(monkeypatch):
    _setup_base(monkeypatch, credential_scope=["read"])
    client = firewall.APP.test_client()

    client.post(
        "/aim/authorize",
        json={"action": "file.read", "resource": "/a.txt"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read"])},
    )
    assert firewall._LOCAL_OPS_COUNTERS["allow"] == 1

    client.post(
        "/aim/authorize",
        json={"action": "shell.exec", "resource": "whoami"},
        headers={"X-Lemma-Credential": _sample_lemma_credential(["read"])},
    )
    assert firewall._LOCAL_OPS_COUNTERS["deny"] == 1


# ---------------------------------------------------------------------------
# Health endpoint includes local ops gate
# ---------------------------------------------------------------------------

def test_health_includes_local_ops_gate(monkeypatch):
    _setup_base(monkeypatch)
    monkeypatch.setattr(firewall, "CONTROL_PLANE_SYNC_ENABLED", False)
    client = firewall.APP.test_client()
    resp = client.get("/aim/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "local_ops_gate" in body
    gate = body["local_ops_gate"]
    assert "enabled" in gate
    assert "decisions_allow" in gate
    assert "decisions_deny" in gate
