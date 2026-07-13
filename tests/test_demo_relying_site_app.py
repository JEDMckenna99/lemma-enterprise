"""Contract tests for the tiny relying-site demo Flask apps."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO_SITES = ROOT / "demo-sites"
PY_PKG = ROOT / "packages" / "ishuman-verify-py"


@pytest.fixture(name="relying_site_client")
def fixture_relying_site_client(monkeypatch):
    monkeypatch.setenv("LEMMA_DEMO_SITE_ID", "tickets-demo.lemma.id")
    monkeypatch.setenv("LEMMA_DEMO_SITE_NAME", "Lemma Ticketing Demo")
    monkeypatch.setenv("LEMMA_DEMO_SITE_KIND", "ticketing")
    monkeypatch.setenv("LEMMA_DEMO_REQUIRED_ASSURANCE", "passkey")
    monkeypatch.setenv("LEMMA_ORIGIN", "https://lemma.id")

    for path in (str(PY_PKG), str(DEMO_SITES)):
        if path not in sys.path:
            sys.path.insert(0, path)

    module_name = "relying_site_app_test"
    if module_name in sys.modules:
        mod = sys.modules[module_name]
    else:
        spec = importlib.util.spec_from_file_location(module_name, DEMO_SITES / "relying_site_app.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

    mod.app.config["TESTING"] = True
    with mod.app.test_client() as client:
        yield client, mod


def test_relying_site_health(relying_site_client):
    client, mod = relying_site_client
    resp = client.get("/health")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["site_id"] == "tickets-demo.lemma.id"
    assert payload["required_assurance"] == "passkey"
    assert payload["presale_mode"] is True
    assert payload["presale_drop_id"]
    assert payload["presale_claim_assurance"] == "passkey"
    assert payload["presale_escalated_assurance"] == "ishuman"


def test_relying_site_config(relying_site_client):
    client, _mod = relying_site_client
    resp = client.get("/api/demo/config")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["site_id"] == "tickets-demo.lemma.id"
    assert payload["lemma_origin"] == "https://lemma.id"
    assert payload["required_assurance"] == "passkey"


def test_relying_site_action_denies_missing_presentation(relying_site_client):
    client, _mod = relying_site_client
    resp = client.post("/api/demo/action", json={})
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "presentation_missing"


def test_relying_site_action_verifies_presentation(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._VERIFY_CTX = None

    class _FakeResult:
        ok = True
        ppid = "ppid_demo_123"
        assurance = "passkey"
        reason = "session_valid"
        credential_id = "cred-1"
        issuer_did = "did:lemma:test"
        bound_site_id = "tickets-demo.lemma.id"

    def _fake_verify(self, _presentation):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify", _fake_verify)

    resp = client.post(
        "/api/demo/action",
        json={
            "action": "reserve_tickets",
            "email": "fan@example.com",
            "presentation": {"credential": {"id": "cred-1"}},
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["ppid"] == "ppid_demo_123"
    assert payload["assurance"] == "passkey"
    assert payload["reason"] == "session_valid"
    assert payload["action_log"][0]["action"] == "reserve_tickets"


def test_relying_site_action_log_empty(relying_site_client):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    resp = client.get("/api/demo/action-log")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["entries"] == []


def test_relying_site_lemma_clear_page(relying_site_client):
    client, _mod = relying_site_client
    resp = client.get("/lemma-clear")

    assert resp.status_code == 200
    assert b"LEMMA_CLEAR_DONE" in resp.data


def test_relying_site_index_loads_verifier_script(relying_site_client):
    client, _mod = relying_site_client
    resp = client.get("/")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "IsHumanVerifier" in body
    assert "stampAction" in body
    assert "claim_presale_code" in body
    assert "register_presale" in body
    assert "unique code" in body.lower()
    assert "Step 1" in body
    assert "verifyFreshForBackend" in body
    assert "/api/presale/register" in body
    assert "Simulate site risk flag" in body
    assert "tickets-demo.lemma.id" in body
    assert "Unique presale code distributor" in body
    assert "requireFreshPasskey: true" in body
    assert "Laylo" not in body
    assert "RealFan" not in body


def test_relying_site_index_exposes_presale_defense_and_tour_ui(relying_site_client):
    client, _mod = relying_site_client
    resp = client.get("/?tour=presale")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'id="defense-strip"' in body
    assert "Fresh passkey" in body
    assert "1 code / fan" in body
    assert 'id="tour-banner"' in body
    assert 'id="tour-checklist"' in body
    assert "TOUR_MODE" in body
    assert "Phone-first presale" in body
    assert "compare-table" in body
    assert "fresh_passkey_missing" in body
    assert "rate_limited" in body
    assert "Nonce consumed" in body
    assert "Gate reason" in body
    assert 'id="backend-gates-toggle"' in body
    assert 'id="crypto-envelope-details"' in body
    assert 'id="fresh-attestation-json"' in body
    assert 'id="attack-lab"' in body
    assert "Replay last stamp" in body
    assert "Skip Step 1" in body
    assert "renderGateChips" in body
    assert "redactFreshPasskeyAttestation" in body


def test_relying_site_index_exposes_server_receipt_and_hub_return(relying_site_client):
    client, _mod = relying_site_client
    resp = client.get("/")
    body = resp.get_data(as_text=True)

    assert 'id="server-receipt"' in body
    assert 'id="server-receipt-fields"' in body
    assert 'id="stamp-json"' in body
    assert "Server verification receipt" in body
    assert "Fan-visible flow" in body
    assert "Cryptographic envelope" in body
    assert "formatDenyReason" in body
    assert "renderReceipt" in body
    assert "isBlockedLocally" in body
    assert "/api/demo/policy/check" in body
    assert "registration_required" in body
    assert "doubt_required" in body
    assert "Try again with same wallet" in body
    assert "/api/presale/claim-code" in body


def test_relying_site_action_denies_invalid_presentation(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._VERIFY_CTX = None

    class _FakeResult:
        ok = False
        ppid = None
        assurance = None
        reason = "invalid_signature"

    def _fake_verify(self, _presentation):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify", _fake_verify)

    resp = client.post(
        "/api/demo/action",
        json={
            "action": "reserve_tickets",
            "presentation": {"credential": {"id": "bad"}},
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "invalid_signature"


def test_presale_claim_denies_missing_stamp(relying_site_client):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_LEDGER.reset()
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    resp = client.post("/api/presale/claim-code", json={"drop_id": "drop-a"})
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "action_stamp_missing"


def test_presale_register_denies_missing_presentation(relying_site_client):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_REGISTRATIONS.reset()

    resp = client.post("/api/presale/register", json={"drop_id": "drop-a"})
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "action_stamp_missing"


def test_presale_register_stores_signup(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_REGISTRATIONS.reset()
    mod._VERIFY_CTX = None
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    class _FakeResult:
        ok = True
        ppid = "did:lemma:ppid_demo_123"
        legacy_ppid = None
        assurance = "passkey"
        reason = "session_valid"

    def _fake_verify_action_stamp(self, *_args, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify_action_stamp", _fake_verify_action_stamp)

    resp = client.post(
        "/api/presale/register",
        json={
            "drop_id": mod.PRESALE_DROP_ID,
            "email": "fan@example.com",
            "phone": "+15550101234",
            "lemma": {"action_assertion": {}, "action_signature": "abc", "credential": {"id": "cred-1"}},
            "server_nonce": "nonce-register-1",
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["ppid"] == "did:lemma:ppid_demo_123"
    assert "gates_passed" in payload
    assert "registration_stored" in payload["gates_passed"]
    assert mod._PRESALE_REGISTRATIONS.is_registered(
        mod.PRESALE_DROP_ID,
        "did:lemma:ppid_demo_123",
    )


def test_presale_claim_requires_registration(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_LEDGER.reset()
    mod._PRESALE_REGISTRATIONS.reset()
    mod._CLAIM_VERIFY_CTX = None
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    class _FakeResult:
        ok = True
        ppid = "did:lemma:ppid_demo_123"
        legacy_ppid = None
        assurance = "passkey"
        reason = "valid"

    def _fake_verify_action_stamp(self, *_args, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify_action_stamp", _fake_verify_action_stamp)

    resp = client.post(
        "/api/presale/claim-code",
        json={
            "drop_id": mod.PRESALE_DROP_ID,
            "lemma": {"verified": True},
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "registration_required"


def test_presale_claim_issues_code_once(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_LEDGER.reset()
    mod._PRESALE_REGISTRATIONS.reset()
    mod._CLAIM_VERIFY_CTX = None
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    ppid = "did:lemma:ppid_demo_123"
    mod._PRESALE_REGISTRATIONS.register(mod.PRESALE_DROP_ID, ppid)

    class _FakeResult:
        ok = True
        ppid = "did:lemma:ppid_demo_123"
        legacy_ppid = None
        assurance = "passkey"
        reason = "valid"
        credential_id = "cred-1"
        issuer_did = "did:lemma:test"
        bound_site_id = "tickets-demo.lemma.id"

    def _fake_verify_action_stamp(self, *_args, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify_action_stamp", _fake_verify_action_stamp)

    body = {
        "drop_id": mod.PRESALE_DROP_ID,
        "email": "fan@example.com",
        "phone": "+15550101234",
        "lemma": {"verified": True},
    }
    first = client.post("/api/presale/claim-code", json=body)
    second = client.post("/api/presale/claim-code", json=body)
    first_payload = first.get_json()
    second_payload = second.get_json()

    assert first.status_code == 200
    assert first_payload["success"] is True
    assert len(first_payload["code"]) == 8
    assert "ledger_claim" in first_payload.get("gates_passed", [])

    assert second.status_code == 403
    assert second_payload["success"] is False
    assert second_payload["reason"] == "allocation_already_claimed"
    assert second_payload["existing_code"] == first_payload["code"]


def test_presale_claim_doubt_requires_escalated_assurance(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_LEDGER.reset()
    mod._PRESALE_REGISTRATIONS.reset()
    mod._POLICY_STORE.doubted.clear()
    mod._CLAIM_VERIFY_CTX = None
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    ppid = "did:lemma:ppid_flagged"
    mod._PRESALE_REGISTRATIONS.register(mod.PRESALE_DROP_ID, ppid)
    mod._POLICY_STORE.doubted.add(ppid)

    class _FakeResult:
        ok = True
        ppid = "did:lemma:ppid_flagged"
        legacy_ppid = None
        assurance = "passkey"
        reason = "valid"

    def _fake_verify_action_stamp(self, *_args, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify_action_stamp", _fake_verify_action_stamp)

    resp = client.post(
        "/api/presale/claim-code",
        json={"drop_id": mod.PRESALE_DROP_ID, "lemma": {"verified": True}},
    )
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "doubt_required"
    assert payload["required_assurance"] == "ishuman"
    assert payload["escalation"] == "fresh_idv"


def test_presale_claim_clears_doubt_after_ishuman(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_LEDGER.reset()
    mod._PRESALE_REGISTRATIONS.reset()
    mod._POLICY_STORE.doubted.clear()
    mod._CLAIM_VERIFY_CTX = None
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    ppid = "did:lemma:ppid_escalated"
    mod._PRESALE_REGISTRATIONS.register(mod.PRESALE_DROP_ID, ppid)
    mod._POLICY_STORE.doubted.add(ppid)

    class _FakeResult:
        ok = True
        ppid = "did:lemma:ppid_escalated"
        legacy_ppid = None
        assurance = "ishuman"
        reason = "valid"

    def _fake_verify_action_stamp(self, *_args, **kwargs):
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify_action_stamp", _fake_verify_action_stamp)

    resp = client.post(
        "/api/presale/claim-code",
        json={
            "drop_id": mod.PRESALE_DROP_ID,
            "required_assurance": "ishuman",
            "lemma": {"verified": True},
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert ppid not in mod._POLICY_STORE.doubted


def test_presale_claim_denies_missing_fresh_passkey(relying_site_client, monkeypatch):
    client, mod = relying_site_client
    mod.ACTION_LOG.clear()
    mod._PRESALE_LEDGER.reset()
    mod._PRESALE_REGISTRATIONS.reset()
    mod._CLAIM_VERIFY_CTX = None
    mod._NONCE_STORE = mod.InMemoryNonceStore()

    ppid = "did:lemma:ppid_demo_123"
    mod._PRESALE_REGISTRATIONS.register(mod.PRESALE_DROP_ID, ppid)

    class _FakeResult:
        ok = False
        ppid = "did:lemma:ppid_demo_123"
        legacy_ppid = None
        assurance = "passkey"
        reason = "fresh_passkey_missing"

    def _fake_verify_action_stamp(self, *_args, **kwargs):
        assert kwargs.get("require_fresh_passkey") is True
        return _FakeResult()

    monkeypatch.setattr(mod.VerificationContext, "verify_action_stamp", _fake_verify_action_stamp)

    resp = client.post(
        "/api/presale/claim-code",
        json={
            "drop_id": mod.PRESALE_DROP_ID,
            "server_nonce": "nonce-claim-missing-fp",
            "lemma": {"verified": True},
        },
    )
    payload = resp.get_json()

    assert resp.status_code == 403
    assert payload["success"] is False
    assert payload["reason"] == "fresh_passkey_missing"
    assert payload.get("gate_failed") == "fresh_passkey_missing"
    assert "assurance" in payload.get("gates_passed", [])
    assert "fresh_passkey_attestation" not in payload.get("gates_passed", [])
