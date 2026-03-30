import json
import sys
import types

from scripts import lemma_firewall as firewall


def _first_policy_route():
    api_id, policy = next(iter(firewall.POLICIES.items()))
    prefix = (policy.path_prefixes[0] if policy.path_prefixes else "/").strip()
    suffix = "probe" if prefix.endswith("/") else "/probe"
    path = prefix + suffix if prefix != "/" else "/probe"
    return api_id, path.lstrip("/")


def _sample_lemma_credential(scope=None):
    payload = {
        "id": "cred_test_1",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_test",
        "claims": {
            "scope": scope or ["read", "write"],
            "site_id": "lemma.id",
        },
    }
    return json.dumps(payload)


def test_validate_lemma_credential_uses_local_path(monkeypatch):
    firewall.LOCAL_PROOF_ENFORCEMENT = True

    def fail_remote(_lemma_credential):
        raise AssertionError("remote exchange-proof path should not be used")

    def fake_verify(_credential):
        return {"valid": True}

    fake_api = types.ModuleType("api")
    fake_trusted_issuers = types.ModuleType("api.trusted_issuers")
    fake_trusted_issuers.verify_credential_with_trust = fake_verify
    monkeypatch.setitem(sys.modules, "api", fake_api)
    monkeypatch.setitem(sys.modules, "api.trusted_issuers", fake_trusted_issuers)
    monkeypatch.setattr(firewall, "_validate_lemma_credential_remote", fail_remote)

    ok, payload = firewall._validate_lemma_credential(_sample_lemma_credential(["admin", "read"]))
    assert ok is True
    assert payload["scope"] == ["admin", "read"]
    assert payload["site_id"] == "lemma.id"


def test_runtime_authorize_cached(monkeypatch):
    firewall.RUNTIME_AUTHORIZE_CACHE_TTL_MS = 30000
    firewall._RUNTIME_AUTHZ_CACHE.clear()
    call_count = {"value": 0}

    def fake_runtime_authorize(_lemma_credential, _runtime_id, *, action="", resource="", risk=""):
        call_count["value"] += 1
        return True, {"authorized": True}

    monkeypatch.setattr(firewall, "_runtime_active_for_credential", fake_runtime_authorize)

    _kw = {"action": "api.call.read", "resource": "/test", "risk": "low"}
    first_ok, _ = firewall._runtime_active_for_credential_cached("cred", "runtime-a", **_kw)
    second_ok, _ = firewall._runtime_active_for_credential_cached("cred", "runtime-a", **_kw)
    assert first_ok is True
    assert second_ok is True
    assert call_count["value"] == 1


def test_runtime_authorize_cache_disabled(monkeypatch):
    firewall.RUNTIME_AUTHORIZE_CACHE_TTL_MS = 0
    firewall._RUNTIME_AUTHZ_CACHE.clear()
    call_count = {"value": 0}

    def fake_runtime_authorize(_lemma_credential, _runtime_id, *, action="", resource="", risk=""):
        call_count["value"] += 1
        return True, {"authorized": True}

    monkeypatch.setattr(firewall, "_runtime_active_for_credential", fake_runtime_authorize)

    _kw = {"action": "api.call.read", "resource": "/test", "risk": "low"}
    firewall._runtime_active_for_credential_cached("cred", "runtime-b", **_kw)
    firewall._runtime_active_for_credential_cached("cred", "runtime-b", **_kw)
    assert call_count["value"] == 2


class _UpstreamResponse:
    def __init__(self, status_code=200, content=b'{"ok":true}', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}


class _ReplayDecision:
    def __init__(self, valid=True, code=None, reason="ok"):
        self.valid = valid
        self.code = code
        self.reason = reason


class _ProofDecision:
    def __init__(self, allowed=True, reason_code="OK", proof_id="dpf_test_1", root_grant_id="rgr_test_1", policy_version="v2"):
        self.allowed = allowed
        self.reason_code = reason_code
        self.proof_id = proof_id
        self.root_grant_id = root_grant_id
        self.policy_version = policy_version


def test_firewall_skips_online_runtime_check_when_not_required(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = {"critical"}
    firewall.PROOF_REQUIRED_TIERS = set()
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall.ONLINE_CHECK_ON_STALE_NONCRITICAL = False
    firewall._SYNC_STATE["revoked_credential_ids"] = set()
    firewall._RUNTIME_STATE_CACHE.clear()

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(
        firewall,
        "_validate_lemma_credential",
        lambda _cred: (True, {"scope": ["write"], "credential_id": "cred_ok_1"}),
    )
    monkeypatch.setattr(firewall, "_runtime_active_for_credential_cached", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime check should be skipped")))
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: _UpstreamResponse())
    monkeypatch.setattr(firewall, "_log_external_activity", lambda *args, **kwargs: None)

    client = firewall.APP.test_client()
    response = client.get("/firewall/github/repos/demo/repo", headers={"X-Lemma-Credential": _sample_lemma_credential(["write"])})
    assert response.status_code == 200


def test_firewall_requires_online_runtime_check_for_critical(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = {"critical"}
    firewall.PROOF_REQUIRED_TIERS = set()
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall.ONLINE_CHECK_ON_STALE_NONCRITICAL = False
    firewall._SYNC_STATE["revoked_credential_ids"] = set()
    firewall._RUNTIME_STATE_CACHE.clear()
    calls = {"runtime": 0}

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(
        firewall,
        "_validate_lemma_credential",
        lambda _cred: (True, {"scope": ["admin"], "credential_id": "cred_ok_2"}),
    )

    def fake_runtime(*_args, **_kwargs):
        calls["runtime"] += 1
        return True, {"authorized": True}

    monkeypatch.setattr(firewall, "_runtime_active_for_credential_cached", fake_runtime)
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: _UpstreamResponse())
    monkeypatch.setattr(firewall, "_log_external_activity", lambda *args, **kwargs: None)

    client = firewall.APP.test_client()
    response = client.post("/firewall/stripe/v1/customers", headers={"X-Lemma-Credential": _sample_lemma_credential(["admin"])})
    assert response.status_code == 200
    assert calls["runtime"] == 1


def test_firewall_denies_locally_revoked_credential(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = {"critical"}
    firewall.PROOF_REQUIRED_TIERS = set()
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall.ONLINE_CHECK_ON_STALE_NONCRITICAL = False
    firewall._SYNC_STATE["revoked_credential_ids"] = {"cred_revoked_1"}
    firewall._RUNTIME_STATE_CACHE.clear()

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(
        firewall,
        "_validate_lemma_credential",
        lambda _cred: (True, {"scope": ["write"], "credential_id": "cred_revoked_1"}),
    )
    monkeypatch.setattr(firewall, "_runtime_active_for_credential_cached", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime check should not run")))
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("upstream should not run")))

    client = firewall.APP.test_client()
    response = client.get("/firewall/github/repos/demo/repo", headers={"X-Lemma-Credential": _sample_lemma_credential(["write"])})
    assert response.status_code == 401
    payload = response.get_json()
    assert payload["error"] == "revoked_credential_local"


def test_firewall_high_tier_stale_does_not_force_online_by_default(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = True
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = {"critical"}
    firewall.PROOF_REQUIRED_TIERS = set()
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall.ONLINE_CHECK_ON_STALE_NONCRITICAL = False
    firewall._SYNC_STATE["last_revocation_sync_ms"] = 0  # stale
    firewall._SYNC_STATE["revoked_credential_ids"] = set()
    firewall._RUNTIME_STATE_CACHE.clear()

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(
        firewall,
        "_validate_lemma_credential",
        lambda _cred: (True, {"scope": ["write"], "credential_id": "cred_ok_3", "ppid": "did:lemma:ppid_test"}),
    )
    monkeypatch.setattr(firewall, "_runtime_active_for_credential_cached", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime check should be skipped")))
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: _UpstreamResponse())
    monkeypatch.setattr(firewall, "_log_external_activity", lambda *args, **kwargs: None)

    client = firewall.APP.test_client()
    response = client.get("/firewall/github/repos/demo/repo", headers={"X-Lemma-Credential": _sample_lemma_credential(["write"])})
    assert response.status_code == 200


def test_firewall_uses_local_runtime_inactive_cache_for_high_tier(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = {"critical"}
    firewall.PROOF_REQUIRED_TIERS = set()
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall.ONLINE_CHECK_ON_STALE_NONCRITICAL = False
    firewall._SYNC_STATE["revoked_credential_ids"] = set()
    firewall._RUNTIME_STATE_CACHE.clear()

    auth_payload = {"scope": ["write"], "credential_id": "cred_ok_4", "ppid": "did:lemma:ppid_test"}
    firewall._runtime_state_update(runtime_id="lemma-firewall-default", auth_payload=auth_payload, active=False, source="test-cache")

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(firewall, "_validate_lemma_credential", lambda _cred: (True, auth_payload))
    monkeypatch.setattr(firewall, "_runtime_active_for_credential_cached", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime check should not run")))
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("upstream should not run")))

    client = firewall.APP.test_client()
    response = client.get("/firewall/github/repos/demo/repo", headers={"X-Lemma-Credential": _sample_lemma_credential(["write"])})
    assert response.status_code == 403
    payload = response.get_json()
    assert payload["error"] == "runtime_inactive_local"


def test_firewall_accepts_proof_native_request(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = set()
    firewall.PROOF_REQUIRED_TIERS = {"low", "high", "critical"}
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall._SYNC_STATE["revoked_proof_ids"] = set()
    firewall._SYNC_STATE["revoked_root_grant_ids"] = set()
    firewall._SYNC_STATE["min_revocation_epoch"] = 0
    firewall._RUNTIME_STATE_CACHE.clear()

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(firewall, "evaluate_proof_native", lambda **_kwargs: _ProofDecision())
    monkeypatch.setattr(firewall, "validate_pop_replay", lambda **_kwargs: _ReplayDecision(valid=True))
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: _UpstreamResponse())
    monkeypatch.setattr(firewall, "_log_external_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        firewall,
        "_scope_from_proof_payload",
        lambda _payload: ["write"],
    )

    proof_header = json.dumps(
        {
            "version": "authz_profile_v2",
            "proof_id": "dpf_test_1",
            "root_grant_id": "rgr_test_1",
            "root_proof": {"subject_ppid": "did:lemma:ppid_test"},
            "delegated_proof": {"acting_for_ppid": "did:lemma:ppid_test"},
        }
    )
    client = firewall.APP.test_client()
    response = client.get(
        "/firewall/github/repos/demo/repo",
        headers={"X-Lemma-Proof": proof_header, "X-Lemma-PoP": json.dumps({"nonce": "n1", "proof_id": "dpf_test_1"})},
    )
    assert response.status_code == 200


def test_firewall_denies_locally_revoked_proof_chain(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = set()
    firewall.PROOF_REQUIRED_TIERS = {"low", "high", "critical"}
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = False
    firewall._SYNC_STATE["revoked_proof_ids"] = {"dpf_revoked_1"}
    firewall._SYNC_STATE["revoked_root_grant_ids"] = set()
    firewall._SYNC_STATE["min_revocation_epoch"] = 0
    firewall._RUNTIME_STATE_CACHE.clear()

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(
        firewall,
        "evaluate_proof_native",
        lambda **_kwargs: _ProofDecision(proof_id="dpf_revoked_1", root_grant_id="rgr_test_1"),
    )
    monkeypatch.setattr(firewall, "validate_pop_replay", lambda **_kwargs: _ReplayDecision(valid=True))
    monkeypatch.setattr(firewall, "_scope_from_proof_payload", lambda _payload: ["write"])

    proof_header = json.dumps(
        {
            "version": "authz_profile_v2",
            "proof_id": "dpf_revoked_1",
            "root_grant_id": "rgr_test_1",
            "root_proof": {"subject_ppid": "did:lemma:ppid_test"},
            "delegated_proof": {"acting_for_ppid": "did:lemma:ppid_test"},
        }
    )
    client = firewall.APP.test_client()
    response = client.get(
        "/firewall/github/repos/demo/repo",
        headers={"X-Lemma-Proof": proof_header, "X-Lemma-PoP": json.dumps({"nonce": "n2", "proof_id": "dpf_revoked_1"})},
    )
    assert response.status_code == 401
    payload = response.get_json()
    assert payload["error"] == "revoked_proof_chain_local"


def test_firewall_requires_fresh_passkey_stepup_when_enabled(monkeypatch):
    firewall.CONTROL_PLANE_SYNC_ENABLED = False
    firewall.RUNTIME_AUTHORIZE_REQUIRED_TIERS = set()
    firewall.PROOF_REQUIRED_TIERS = {"low", "high", "critical"}
    firewall.REQUIRE_FRESH_PASSKEY_STEPUP = True
    firewall.STEPUP_REQUIRED_TIERS = {"low", "high", "critical"}
    firewall._SYNC_STATE["revoked_proof_ids"] = set()
    firewall._SYNC_STATE["revoked_root_grant_ids"] = set()
    firewall._SYNC_STATE["min_revocation_epoch"] = 0
    firewall._RUNTIME_STATE_CACHE.clear()

    monkeypatch.setattr(firewall, "_ensure_sync_thread_started", lambda: None)
    monkeypatch.setattr(firewall, "evaluate_proof_native", lambda **_kwargs: _ProofDecision())
    monkeypatch.setattr(firewall, "validate_pop_replay", lambda **_kwargs: _ReplayDecision(valid=True))
    monkeypatch.setattr(firewall, "_scope_from_proof_payload", lambda _payload: ["write"])
    monkeypatch.setattr(firewall.HTTP, "request", lambda **_kwargs: _UpstreamResponse())
    monkeypatch.setattr(firewall, "_log_external_activity", lambda *args, **kwargs: None)

    proof_header = json.dumps(
        {
            "version": "authz_profile_v2",
            "proof_id": "dpf_stepup_1",
            "root_grant_id": "rgr_stepup_1",
            "root_proof": {"subject_ppid": "did:lemma:ppid_test"},
            "delegated_proof": {"acting_for_ppid": "did:lemma:ppid_test"},
        }
    )
    api_id, upstream_path = _first_policy_route()
    client = firewall.APP.test_client()
    response = client.get(
        f"/firewall/{api_id}/{upstream_path}",
        headers={"X-Lemma-Proof": proof_header, "X-Lemma-PoP": json.dumps({"nonce": "n3", "proof_id": "dpf_stepup_1"})},
    )
    assert response.status_code == 403
    payload = response.get_json()
    assert payload["error"] == "AUTH_RISK_STEP_UP_REQUIRED"
