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
    assert "verifyForBackend" in body
    assert "stampAction" not in body
    assert "presentation" in body
    assert "tickets-demo.lemma.id" in body


def test_relying_site_index_exposes_server_receipt_and_hub_return(relying_site_client):
    client, _mod = relying_site_client
    resp = client.get("/")
    body = resp.get_data(as_text=True)

    assert 'id="server-receipt"' in body
    assert 'id="server-receipt-fields"' in body
    assert 'id="presentation-json"' in body
    assert "Server verification receipt" in body
    assert "formatDenyReason" in body
    assert "renderServerReceipt" in body
    assert "isBlockedLocally" in body
    assert "/api/demo/policy/check" in body
    assert "site_blocked" in body
    assert "assurance_insufficient" in body
    assert "Verified (passkey)" in body
    assert "Human (ishuman)" in body
    assert "?from=demo" in body
    assert "demo hub" in body.lower()


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
