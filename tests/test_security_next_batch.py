import os
import sys
from flask import Flask


# Keep imports working when running tests from repository root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app_with_sdk_auth():
    os.environ.setdefault("LEMMA_ACCESS_TOKEN_SECRET", "test-access-token-secret")

    from api.sdk_auth import sdk_auth_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(sdk_auth_bp)
    return app


def _app_with_sdk_api(monkeypatch):
    # Enable demo API key path for validate_api_key decorator.
    monkeypatch.setenv("LEMMA_SDK_ALLOW_DEMO", "1")

    from api.sdk_api import sdk_api_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(sdk_api_bp)
    return app


def _app_with_wallet_session_sync(monkeypatch):
    # session_manager requires SESSION_SECRET in production-like envs.
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from api.wallet_session_sync import wallet_session_sync_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(wallet_session_sync_bp)
    return app


def _stub_valid_credential(site_id="site-a.example.com"):
    return {
        "id": "cred_replay_001",
        "issuer": "did:lemma:testissuer",
        "subject": "did:lemma:ppid_abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "claims": {
            "siteId": site_id,
            "permissionId": "admin_access",
            "scope": ["read", "write", "admin"],
        },
    }


def test_exchange_proof_replay_succeeds_across_clients(monkeypatch):
    """
    Risk check #1: copied credential replay from a different browser/profile.
    Current behavior should demonstrate bearer-token style exchange.
    """
    app = _app_with_sdk_auth()

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {
            "valid": True,
            "issuer_trusted": True,
            "signature_valid": True,
        },
    )

    payload = {
        "credential": _stub_valid_credential(),
        "site_id": "site-a.example.com",
    }

    with app.test_client() as client_a:
        first = client_a.post("/api/auth/exchange-proof", json=payload)
        assert first.status_code == 200
        assert first.get_json()["success"] is True

    # Simulate exfiltration to a different browser/profile (new client).
    with app.test_client() as client_b:
        replay = client_b.post("/api/auth/exchange-proof", json=payload)
        assert replay.status_code == 200
        assert replay.get_json()["success"] is True


def test_exchange_proof_replay_succeeds_after_signout(monkeypatch):
    """
    Risk check #1: replay remains possible after signout because signout is
    compatibility-only and does not invalidate proof artifacts.
    """
    app = _app_with_sdk_auth()

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {
            "valid": True,
            "issuer_trusted": True,
            "signature_valid": True,
        },
    )

    payload = {
        "credential": _stub_valid_credential(),
        "site_id": "site-a.example.com",
    }

    with app.test_client() as client:
        first = client.post("/api/auth/exchange-proof", json=payload)
        assert first.status_code == 200

        signout = client.post("/api/auth/signout", json={})
        assert signout.status_code == 200

        replay = client.post("/api/auth/exchange-proof", json=payload)
        assert replay.status_code == 200
        assert replay.get_json()["success"] is True


def test_exchange_proof_rejects_site_mismatch(monkeypatch):
    """
    Risk check #2 (positive control): site mismatch between claimed site and
    requested site should fail closed.
    """
    app = _app_with_sdk_auth()

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {
            "valid": True,
            "issuer_trusted": True,
            "signature_valid": True,
        },
    )

    payload = {
        "credential": _stub_valid_credential(site_id="site-a.example.com"),
        "site_id": "site-b.example.com",
    }

    with app.test_client() as client:
        resp = client.post("/api/auth/exchange-proof", json=payload)
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "site_mismatch"


def test_complete_identity_verification_rejects_untracked_session_id(monkeypatch):
    """
    Completion must reject client-supplied session IDs that were not started
    and bound to the initiating API key.
    """
    app = _app_with_sdk_api(monkeypatch)

    monkeypatch.setattr(
        "api.sdk_api.create_enhanced_identity_credential",
        lambda user_id, session_id, stripe_result: {
            "id": "cred_demo_completion",
            "issuer": "did:lemma:testissuer",
            "subject": user_id,
            "claims": {"siteId": "lemma.id", "isHuman": "true"},
        },
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/sdk/complete-identity-verification",
            headers={"Authorization": "Bearer demo-test-key"},
            json={
                "session_id": "vs_demo_attackerchosen_123456",
                "enable_rust_engine": False,
            },
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "untracked_verification_session"


def test_signal_unlock_origin_substring_bypass(monkeypatch):
    """
    Risk check #2/#4 (positive control): origin checks must use exact host
    matching, not substring. An attacker-controlled origin that merely contains
    'lemma.id' (e.g. 'lemma.id.attacker.example') must be rejected.
    """
    app = _app_with_wallet_session_sync(monkeypatch)

    monkeypatch.setattr("api.wallet_session_sync._store_global_session", lambda **kwargs: True)

    with app.test_client() as client:
        resp = client.post(
            "/api/wallet/signal-unlock",
            headers={"Origin": "https://lemma.id.attacker.example"},
            json={"wallet_id": "wallet_attack_test"},
        )
        assert resp.status_code == 403
        assert resp.get_json().get("success") is not True

