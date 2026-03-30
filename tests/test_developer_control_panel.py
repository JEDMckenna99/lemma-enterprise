"""Tests for the Lemma Developer Control Panel features.

Covers: auto-taint, local decision log, SSE stream, widen-scope,
tap-to-approve, scope parsing, and session replay.
"""

import json
import os
import threading
import time

import pytest

from scripts import lemma_firewall as firewall


def _sample_lemma_credential(scope=None, actions=None, taint_epoch=None):
    payload = {
        "id": "cred_dcp_1",
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
    firewall.TAINT_ON_VIOLATION_ENABLED = False
    firewall.APPROVAL_REQUIRED_ACTIONS = []
    firewall._SYNC_STATE["revoked_credential_ids"] = set()
    firewall._SYNC_STATE["revoked_proof_ids"] = set()
    firewall._SYNC_STATE["revoked_root_grant_ids"] = set()
    firewall._SYNC_STATE["min_revocation_epoch"] = 0
    firewall._RUNTIME_STATE_CACHE.clear()
    firewall._RUNTIME_AUTHZ_CACHE.clear()
    firewall._RUNTIME_TAINT_CACHE.clear()
    firewall._LOCAL_OPS_COUNTERS["allow"] = 0
    firewall._LOCAL_OPS_COUNTERS["deny"] = 0
    firewall._DECISION_RING.clear()
    firewall._DECISION_SUBSCRIBERS.clear()
    firewall._PENDING_APPROVALS.clear()
    firewall._APPROVAL_RESULTS.clear()
    firewall._SESSION_ACTIONS_MAP = None

    result_payload = {
        "scope": credential_scope or ["read", "write"],
        "credential_id": "cred_dcp_1",
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
# P1b: Auto-taint on scope violation
# ---------------------------------------------------------------------------

class TestAutoTaint:
    def test_auto_taint_on_scope_violation(self, monkeypatch):
        """Agent tries admin action with read scope -> taint bumps -> subsequent read denied."""
        _setup_base(monkeypatch, credential_scope=["read"])
        firewall.TAINT_ON_VIOLATION_ENABLED = True
        firewall.TAINT_ENFORCEMENT_ENABLED = True
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read"], taint_epoch=0)
        monkeypatch.setattr(
            firewall,
            "_validate_lemma_credential",
            lambda _cred: (True, {"scope": ["read"], "credential_id": "cred_dcp_1", "taint_epoch": 0}),
        )

        # Out-of-scope action triggers taint
        resp = client.post(
            "/aim/authorize",
            json={"action": "file.delete", "resource": "/important.db"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "insufficient_scope"

        # Taint epoch should have been bumped
        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default", 0) > 0

        # Now even a valid read action should fail due to stale taint
        resp2 = client.post(
            "/aim/authorize",
            json={"action": "file.read", "resource": "/readme.md"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp2.status_code == 403
        body2 = resp2.get_json()
        assert body2["error"] == "proof_taint_epoch_stale"

    def test_auto_taint_disabled_by_default(self, monkeypatch):
        """Scope violation does NOT taint when flag is off."""
        _setup_base(monkeypatch, credential_scope=["read"])
        firewall.TAINT_ON_VIOLATION_ENABLED = False
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read"])

        resp = client.post(
            "/aim/authorize",
            json={"action": "file.delete", "resource": "/important.db"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 403
        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default", 0) == 0

    def test_auto_taint_on_action_not_granted(self, monkeypatch):
        """Action taxonomy deny also bumps taint."""
        actions = {"file.read": True}
        _setup_base(monkeypatch, credential_scope=["read", "write"], credential_actions=actions)
        firewall.TAINT_ON_VIOLATION_ENABLED = True
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"], actions=actions)

        resp = client.post(
            "/aim/authorize",
            json={"action": "file.write", "resource": "/src/main.py"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "action_not_granted"
        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default", 0) > 0


# ---------------------------------------------------------------------------
# P1c: Local decision log
# ---------------------------------------------------------------------------

class TestLocalDecisionLog:
    def test_local_decision_log_written(self, monkeypatch, tmp_path):
        log_file = tmp_path / "session.jsonl"
        _setup_base(monkeypatch, credential_scope=["read", "write"])
        monkeypatch.setattr(firewall, "SESSION_LOG_FILE", str(log_file))
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        client.post(
            "/aim/authorize",
            json={"action": "file.read", "resource": "/src/main.py"},
            headers={"X-Lemma-Credential": cred},
        )
        client.post(
            "/aim/authorize",
            json={"action": "file.delete", "resource": "/important.db"},
            headers={"X-Lemma-Credential": cred},
        )

        lines = [json.loads(l) for l in log_file.read_text().strip().splitlines() if l.strip()]
        assert len(lines) >= 2
        assert lines[0]["allowed"] is True
        assert lines[0]["action"] == "file.read"
        assert "timestamp" in lines[0]
        assert lines[1]["allowed"] is False

    def test_no_log_when_file_not_set(self, monkeypatch, tmp_path):
        _setup_base(monkeypatch)
        monkeypatch.setattr(firewall, "SESSION_LOG_FILE", "")
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        client.post(
            "/aim/authorize",
            json={"action": "file.read", "resource": "/test"},
            headers={"X-Lemma-Credential": cred},
        )
        # No file created
        assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# P2a: Decision stream / ring buffer
# ---------------------------------------------------------------------------

class TestDecisionStream:
    def test_decision_ring_buffer_populated(self, monkeypatch):
        _setup_base(monkeypatch, credential_scope=["read", "write"])
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        client.post(
            "/aim/authorize",
            json={"action": "file.read", "resource": "/a.py"},
            headers={"X-Lemma-Credential": cred},
        )

        assert len(firewall._DECISION_RING) >= 1
        last = firewall._DECISION_RING[-1]
        assert last["action"] == "file.read"
        assert "timestamp" in last

    def test_decision_stream_sse(self, monkeypatch):
        _setup_base(monkeypatch, credential_scope=["read", "write"])
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        # Pre-populate a decision
        client.post(
            "/aim/authorize",
            json={"action": "file.read", "resource": "/b.py"},
            headers={"X-Lemma-Credential": cred},
        )

        resp = client.get("/aim/decisions/stream")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/event-stream")

    def test_dashboard_returns_html(self, monkeypatch):
        _setup_base(monkeypatch)
        client = firewall.APP.test_client()
        resp = client.get("/aim/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert b"Lemma AIM" in resp.data


# ---------------------------------------------------------------------------
# P2b: Scope widening
# ---------------------------------------------------------------------------

class TestWidenScope:
    def test_widen_scope_allows_previously_denied(self, monkeypatch):
        actions = {"file.read": True}
        _setup_base(monkeypatch, credential_scope=["read", "write"], credential_actions=actions)
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"], actions=actions)

        # file.write not in actions -> denied
        resp = client.post(
            "/aim/authorize",
            json={"action": "file.write", "resource": "/src/main.py"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "action_not_granted"

        # Widen scope to include file.write
        widen_resp = client.post(
            "/aim/widen-scope",
            json={"actions": {"file.write": {"paths": ["/src/**"]}}},
        )
        assert widen_resp.status_code == 200
        assert widen_resp.get_json()["success"] is True

        # Now retry -> should be allowed
        resp2 = client.post(
            "/aim/authorize",
            json={"action": "file.write", "resource": "/src/main.py"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["allowed"] is True

    def test_widen_scope_rejects_empty(self, monkeypatch):
        _setup_base(monkeypatch)
        client = firewall.APP.test_client()
        resp = client.post("/aim/widen-scope", json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# P3: Tap-to-approve
# ---------------------------------------------------------------------------

class TestTapToApprove:
    def test_approval_required_blocks_until_approved(self, monkeypatch):
        _setup_base(monkeypatch, credential_scope=["read", "write", "admin"])
        firewall.APPROVAL_REQUIRED_ACTIONS = ["shell.exec"]
        monkeypatch.setattr(firewall, "APPROVAL_TIMEOUT_SECONDS", 10)
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write", "admin"])

        result = {}

        def make_request():
            resp = client.post(
                "/aim/authorize",
                json={"action": "shell.exec", "resource": "ls -la"},
                headers={"X-Lemma-Credential": cred},
            )
            result["status"] = resp.status_code
            result["body"] = resp.get_json()

        t = threading.Thread(target=make_request)
        t.start()
        time.sleep(0.3)

        # Find the pending approval
        decision_id = None
        for d in firewall._DECISION_RING:
            if d.get("allowed") == "pending" and d.get("action") == "shell.exec":
                decision_id = d["decision_id"]
                break

        assert decision_id is not None, "No pending decision found"

        # Approve it
        approve_resp = client.post(
            f"/aim/approve/{decision_id}",
            json={"approved": True},
        )
        assert approve_resp.status_code == 200

        t.join(timeout=5)
        assert result.get("status") == 200
        assert result.get("body", {}).get("allowed") is True

    def test_approval_timeout_denies(self, monkeypatch):
        _setup_base(monkeypatch, credential_scope=["read", "write", "admin"])
        firewall.APPROVAL_REQUIRED_ACTIONS = ["file.delete"]
        monkeypatch.setattr(firewall, "APPROVAL_TIMEOUT_SECONDS", 1)
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write", "admin"])

        resp = client.post(
            "/aim/authorize",
            json={"action": "file.delete", "resource": "/important.db"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "approval_timeout"

    def test_approve_unknown_decision_returns_404(self, monkeypatch):
        _setup_base(monkeypatch)
        client = firewall.APP.test_client()
        resp = client.post("/aim/approve/nonexistent_id", json={"approved": True})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CLI: scope parsing
# ---------------------------------------------------------------------------

class TestScopeParse:
    def test_scope_parse_basic(self):
        from scripts.lemma_cli import _parse_scope_spec
        scopes, actions = _parse_scope_spec("read:~/project/** write:~/project/src/**")
        assert "read" in scopes
        assert "write" in scopes
        assert "file.read" in actions
        assert "file.write" in actions

    def test_scope_parse_no_paths(self):
        from scripts.lemma_cli import _parse_scope_spec
        scopes, actions = _parse_scope_spec("read")
        assert scopes == ["read"]
        assert "file.read" in actions
        assert actions["file.read"] is True

    def test_scope_parse_with_paths_has_bounds(self):
        from scripts.lemma_cli import _parse_scope_spec
        scopes, actions = _parse_scope_spec("read:/src/**")
        assert "file.read" in actions
        assert isinstance(actions["file.read"], dict)
        assert "/src/**" in actions["file.read"]["paths"]


# ---------------------------------------------------------------------------
# CLI: TTL parsing
# ---------------------------------------------------------------------------

class TestTTLParse:
    def test_ttl_minutes(self):
        from scripts.lemma_cli import _parse_ttl
        assert _parse_ttl("30m") == 1800

    def test_ttl_hours(self):
        from scripts.lemma_cli import _parse_ttl
        assert _parse_ttl("2h") == 7200

    def test_ttl_days(self):
        from scripts.lemma_cli import _parse_ttl
        assert _parse_ttl("1d") == 86400


# ---------------------------------------------------------------------------
# CLI: session replay summary
# ---------------------------------------------------------------------------

class TestSessionReplay:
    def test_session_replay_summary(self, tmp_path, monkeypatch):
        from scripts.lemma_cli import run_replay
        from argparse import Namespace

        log_file = tmp_path / "session_test123.jsonl"
        decisions = [
            {"allowed": True, "action": "file.read", "resource": "/a.py", "timestamp": 1000},
            {"allowed": True, "action": "file.write", "resource": "/b.py", "timestamp": 1001},
            {"allowed": False, "action": "file.delete", "resource": "/c.py", "error": "insufficient_scope", "timestamp": 1002},
        ]
        log_file.write_text("\n".join(json.dumps(d) for d in decisions) + "\n")

        # Point _ACTIVE_SESSION_FILE to a temp active file
        from scripts import lemma_cli
        active_file = tmp_path / "_active.json"
        active_file.write_text(json.dumps({"log_file": str(log_file)}))
        monkeypatch.setattr(lemma_cli, "_ACTIVE_SESSION_FILE", active_file)

        args = Namespace(json=True, last=True, session_id="")
        import io, sys
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)
        code = run_replay(args)
        monkeypatch.undo()

        assert code == 0
        output = json.loads(captured.getvalue())
        assert output["success"] is True
        assert output["total_decisions"] == 3
        assert output["allowed"] == 2
        assert output["denied"] == 1
        assert "file.read" in output["actions_breakdown"]


# ---------------------------------------------------------------------------
# Auto-taint on ingest actions
# ---------------------------------------------------------------------------

class TestIngestAutoTaint:
    def test_ingest_external_bumps_taint_epoch(self, monkeypatch):
        """Authorized ingest.external action should bump taint epoch."""
        _setup_base(monkeypatch, credential_scope=["read", "write"])
        firewall.TAINT_ENFORCEMENT_ENABLED = True
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default", 0) == 0

        resp = client.post(
            "/aim/authorize",
            json={"action": "ingest.external", "resource": "https://example.com/page"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["allowed"] is True
        assert body.get("taint_epoch_bumped") is True
        assert body.get("new_taint_epoch") == 1
        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default") == 1

    def test_ingest_user_content_bumps_taint_epoch(self, monkeypatch):
        """Authorized ingest.user_content action should bump taint epoch."""
        _setup_base(monkeypatch, credential_scope=["read", "write"])
        firewall.TAINT_ENFORCEMENT_ENABLED = True
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        resp = client.post(
            "/aim/authorize",
            json={"action": "ingest.user_content", "resource": "/uploads/doc.txt"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["allowed"] is True
        assert body.get("taint_epoch_bumped") is True

    def test_ingest_does_not_bump_when_taint_disabled(self, monkeypatch):
        """Ingest action should not bump epoch when taint enforcement is off."""
        _setup_base(monkeypatch, credential_scope=["read", "write"])
        firewall.TAINT_ENFORCEMENT_ENABLED = False
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"])

        resp = client.post(
            "/aim/authorize",
            json={"action": "ingest.external", "resource": "https://example.com"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["allowed"] is True
        assert body.get("taint_epoch_bumped") is None
        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default", 0) == 0

    def test_ingest_then_privileged_action_denied(self, monkeypatch):
        """Full containment loop: ingest bumps epoch, then write is denied."""
        _setup_base(monkeypatch, credential_scope=["read", "write"], taint_epoch=0)
        firewall.TAINT_ENFORCEMENT_ENABLED = True
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read", "write"], taint_epoch=0)

        # Ingest: allowed but bumps epoch
        resp1 = client.post(
            "/aim/authorize",
            json={"action": "ingest.external", "resource": "https://evil.com/inject"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp1.status_code == 200
        assert resp1.get_json()["allowed"] is True

        # Write: denied because proof taint_epoch (0) < runtime taint_epoch (1)
        resp2 = client.post(
            "/aim/authorize",
            json={"action": "file.write", "resource": "/src/main.py"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp2.status_code == 403
        body2 = resp2.get_json()
        assert body2["error"] == "proof_taint_epoch_stale"
        assert body2["proof_taint_epoch"] == 0
        assert body2["runtime_taint_epoch"] == 1

    def test_normal_read_does_not_bump_taint(self, monkeypatch):
        """Non-ingest read actions should NOT bump taint epoch."""
        _setup_base(monkeypatch, credential_scope=["read"])
        firewall.TAINT_ENFORCEMENT_ENABLED = True
        client = firewall.APP.test_client()
        cred = _sample_lemma_credential(["read"])

        resp = client.post(
            "/aim/authorize",
            json={"action": "file.read", "resource": "/src/main.py"},
            headers={"X-Lemma-Credential": cred},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["allowed"] is True
        assert body.get("taint_epoch_bumped") is None
        assert firewall._RUNTIME_TAINT_CACHE.get("lemma-firewall-default", 0) == 0


# ---------------------------------------------------------------------------
# Credential expiry enforcement
# ---------------------------------------------------------------------------

class TestCredentialExpiry:
    def test_expired_credential_rejected(self, monkeypatch):
        """Credential with expires_at in the past should be rejected."""
        firewall.LOCAL_PROOF_ENFORCEMENT = True

        def fake_verify(_credential):
            return {"valid": True}

        import sys
        import types
        fake_trusted = types.ModuleType("api.trusted_issuers")
        fake_trusted.verify_credential_with_trust = fake_verify
        monkeypatch.setitem(sys.modules, "api.trusted_issuers", fake_trusted)

        expired_cred = json.dumps({
            "id": "cred_expired_1",
            "issuer": "did:lemma:test",
            "subject": "did:lemma:ppid_test",
            "claims": {
                "scope": ["read"],
                "expires_at": int(time.time()) - 3600,
            },
        })
        ok, payload = firewall._validate_lemma_credential_local(expired_cred)
        assert ok is False
        assert payload["error"] == "credential_expired"

    def test_valid_credential_not_expired(self, monkeypatch):
        """Credential with future expires_at should pass."""
        firewall.LOCAL_PROOF_ENFORCEMENT = True

        def fake_verify(_credential):
            return {"valid": True}

        import sys
        import types
        fake_trusted = types.ModuleType("api.trusted_issuers")
        fake_trusted.verify_credential_with_trust = fake_verify
        monkeypatch.setitem(sys.modules, "api.trusted_issuers", fake_trusted)

        valid_cred = json.dumps({
            "id": "cred_valid_1",
            "issuer": "did:lemma:test",
            "subject": "did:lemma:ppid_test",
            "claims": {
                "scope": ["read", "write"],
                "expires_at": int(time.time()) + 3600,
            },
        })
        ok, payload = firewall._validate_lemma_credential_local(valid_cred)
        assert ok is True
        assert "read" in payload["scope"]

    def test_credential_without_expiry_allowed(self, monkeypatch):
        """Credential with no expires_at should pass (backward compat)."""
        firewall.LOCAL_PROOF_ENFORCEMENT = True

        def fake_verify(_credential):
            return {"valid": True}

        import sys
        import types
        fake_trusted = types.ModuleType("api.trusted_issuers")
        fake_trusted.verify_credential_with_trust = fake_verify
        monkeypatch.setitem(sys.modules, "api.trusted_issuers", fake_trusted)

        no_expiry_cred = json.dumps({
            "id": "cred_no_exp_1",
            "issuer": "did:lemma:test",
            "subject": "did:lemma:ppid_test",
            "claims": {
                "scope": ["read"],
            },
        })
        ok, payload = firewall._validate_lemma_credential_local(no_expiry_cred)
        assert ok is True


# ---------------------------------------------------------------------------
# Proxy taint_on_response
# ---------------------------------------------------------------------------

class TestProxyTaintOnResponse:
    def test_taint_on_response_flag_parsed(self):
        """Policy with taint_on_response: true should set the flag."""
        import tempfile
        policy_data = {
            "default_timeout_seconds": 5,
            "apis": {
                "search": {
                    "base_url": "https://search.example.com",
                    "allowed_methods": ["GET"],
                    "path_prefixes": ["/"],
                    "required_scope": "read",
                    "risk_tier": "low",
                    "taint_on_response": True,
                },
                "internal": {
                    "base_url": "https://internal.example.com",
                    "allowed_methods": ["GET"],
                    "path_prefixes": ["/"],
                    "required_scope": "read",
                    "risk_tier": "low",
                },
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            f.flush()
            apis, _ = firewall._load_policy(f.name)

        assert apis["search"].taint_on_response is True
        assert apis["internal"].taint_on_response is False

        import os
        os.unlink(f.name)
