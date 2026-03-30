import os
import sys

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import api.services.wallet_service as wallet_service


def _wallet_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(wallet_service.wallet_service_bp)
    return app


def test_runtime_authorize_denies_invalid_operation_descriptor(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "_extract_ppid_from_lemma_header", lambda: "did:lemma:ppid_" + ("1" * 64))
    monkeypatch.setattr(wallet_service, "_extract_lemma_trust_claims", lambda: {"credential_id": "prf_1", "scope": ["read"]})
    monkeypatch.setattr(wallet_service, "_runtime_record_for_ppid", lambda **kwargs: {"active": True, "trust_state": "clean_internal", "taint_epoch": 0})
    with app.test_client() as client:
        resp = client.post("/api/wallet/runtimes/lemma-firewall-default/authorize", json={"risk": "low"})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "deny_operation_descriptor_invalid"


def test_runtime_authorize_denies_missing_resource_for_fs_write(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "_extract_ppid_from_lemma_header", lambda: "did:lemma:ppid_" + ("2" * 64))
    monkeypatch.setattr(wallet_service, "_extract_lemma_trust_claims", lambda: {"credential_id": "prf_2", "scope": ["write"]})
    monkeypatch.setattr(wallet_service, "_runtime_record_for_ppid", lambda **kwargs: {"active": True, "trust_state": "clean_internal", "taint_epoch": 0})
    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/lemma-firewall-default/authorize",
            json={"action": "fs.write", "risk": "high"},
        )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "deny_operation_descriptor_invalid"


def test_runtime_authorize_returns_normalized_descriptor(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(wallet_service, "_extract_ppid_from_lemma_header", lambda: "did:lemma:ppid_" + ("3" * 64))
    monkeypatch.setattr(
        wallet_service,
        "_extract_lemma_trust_claims",
        lambda: {"credential_id": "prf_3", "scope": ["write"], "step_up_required": False, "taint_epoch": 0},
    )
    monkeypatch.setattr(
        wallet_service,
        "_runtime_record_for_ppid",
        lambda **kwargs: {"active": True, "trust_state": "clean_internal", "taint_epoch": 0, "policy_profile": "lemma_firewall_default_v1", "risk_defaults": {}},
    )
    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/runtimes/lemma-firewall-default/authorize",
            json={"action": "api.call.write", "resource": "/api/developer/sites"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["action"] == "api.call.write"
    assert body["risk"] == "high"
    assert body["resource"] == "/api/developer/sites"
