"""Wave 1 security containment regression tests (proof-first)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask, g

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "containment-test-session-secret")
os.environ.setdefault("LEMMA_ACCESS_TOKEN_SECRET", "containment-access-token-secret")


def _stub_valid_credential(site_id="site-a.example.com", permission_id="admin_access"):
    return {
        "id": "cred_containment_001",
        "issuer": "did:lemma:testissuer",
        "subject": "did:lemma:ppid_abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        "claims": {
            "siteId": site_id,
            "permissionId": permission_id,
            "scope": ["read", "write", "admin"],
        },
    }


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("ENVIRONMENT", "development")

    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


def test_require_api_key_accepts_valid_header(monkeypatch):
    from auth.decorators import require_api_key

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/m2m", methods=["GET"])
    @require_api_key(allow_credential_fallback=False)
    def _m2m():
        from flask import jsonify

        return jsonify({"api_key": g.api_key}), 200

    monkeypatch.setattr(
        "api.site_access.validate_site_api_key",
        lambda _key: {"valid": True, "type": "customer", "site_id": "site_abc"},
    )

    with app.test_client() as client:
        resp = client.get("/m2m", headers={"X-API-Key": "lm_site_test_key"})
        assert resp.status_code == 200
        assert resp.get_json()["api_key"] == "lm_site_test_key"


def test_require_api_key_rejects_invalid_key(monkeypatch):
    from auth.decorators import require_api_key

    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/m2m", methods=["GET"])
    @require_api_key(allow_credential_fallback=False)
    def _m2m():
        return {"ok": True}, 200

    monkeypatch.setattr(
        "api.site_access.validate_site_api_key",
        lambda _key: {"valid": False, "error": "Invalid API key"},
    )

    with app.test_client() as client:
        resp = client.get("/m2m", headers={"X-API-Key": "bad-key"})
        assert resp.status_code == 401


def test_verify_session_freshness_fail_closed(app):
    with app.test_client() as client:
        resp = client.post(
            "/api/verify-session-freshness",
            json={"walletId": "wallet_test", "authTimestamp": 1_700_000_000_000},
        )
        assert resp.status_code == 410
        body = resp.get_json()
        assert body["fresh"] is False
        assert body["valid"] is False


def test_wallet_auth_issue_rejects_bare_ppid(app, monkeypatch):
    monkeypatch.setattr(
        "api.services.wallet_service._validate_issuance_request",
        lambda _site_id: (True, None),
    )
    with app.test_client() as client:
        resp = client.post(
            "/api/wallet-auth/issue",
            json={
                "site_id": "customer.example.com",
                "ppid": "did:lemma:ppid_" + ("a" * 64),
            },
        )
        assert resp.status_code == 410
        assert resp.get_json()["error"] == "client_ppid_deprecated"


def test_wallet_auth_issue_rejects_bare_passkey_id(app, monkeypatch):
    monkeypatch.setattr(
        "api.services.wallet_service._validate_issuance_request",
        lambda _site_id: (True, None),
    )
    with app.test_client() as client:
        resp = client.post(
            "/api/wallet-auth/issue",
            json={
                "site_id": "customer.example.com",
                "passkey_credential_id": "pk-test-credential",
            },
        )
        assert resp.status_code == 410
        assert resp.get_json()["error"] == "presentation_required"


def test_complete_identity_verification_rejects_untracked_session(monkeypatch):
    monkeypatch.setenv("LEMMA_SDK_ALLOW_DEMO", "1")

    from api.sdk_api import sdk_api_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "containment-test-secret"
    app.register_blueprint(sdk_api_bp)

    monkeypatch.setattr(
        "api.sdk_api._consume_sdk_idv_session",
        lambda session_id, api_key: None,
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/sdk/complete-identity-verification",
            headers={"Authorization": "Bearer demo-test-key"},
            json={"session_id": "vs_demo_attackerchosen_123456", "enable_rust_engine": False},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "untracked_verification_session"


def test_fresh_passkey_begin_rejects_unregistered_passkey(app, monkeypatch):
    monkeypatch.setattr(
        "api.fresh_passkey_attestation.validate_fresh_passkey_identity_binding",
        lambda **kwargs: (False, "passkey_not_registered_on_server"),
    )
    with app.test_client() as client:
        resp = client.post(
            "/api/ishuman/fresh-passkey/begin",
            json={
                "site_id": "customer.example.com",
                "action_commitment": "a" * 64,
                "credential_id": "cred_victim",
                "subject": "did:lemma:ppid_" + ("b" * 64),
                "passkey_credential_id": "pk-attacker",
                "wallet_id": "wallet_attacker",
            },
        )
        assert resp.status_code == 403


def test_recovery_complete_requires_webauthn():
    import api.account_recovery as mod
    from api.account_recovery import account_recovery_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "containment-recovery-secret"
    app.register_blueprint(account_recovery_bp)

    token = "recovery-token-webauthn"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    mod.store_recovery_token(
        token_hash,
        {
            "site_id": "example.com",
            "admin_email": "admin@example.com",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "used": False,
        },
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/recovery/complete",
            json={
                "token": token,
                "ppid": "did:lemma:ppid_" + ("c" * 64),
                "passkey_credential_id": "pk-recovery-1",
            },
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "replacement_webauthn_required"


def test_platform_issue_site_permission_requires_platform_admin(app, monkeypatch):
    monkeypatch.setattr(
        "auth.decorators.extract_user_lemma_principal",
        lambda _headers: (None, "missing"),
    )
    with app.test_client() as client:
        resp = client.post(
            "/api/platform/issue-site-permission",
            headers={"X-Lemma-Credential": json.dumps(_stub_valid_credential())},
            json={"site_id": "victim.example.com", "user_email": "user@example.com"},
        )
        assert resp.status_code in (401, 403)


def test_issuer_revoke_requires_platform_admin(app, monkeypatch):
    monkeypatch.setattr(
        "auth.decorators.extract_user_lemma_principal",
        lambda _headers: (None, "missing"),
    )
    with app.test_client() as client:
        resp = client.post(
            "/api/issuers/did:web:example.com/revoke",
            headers={"X-Lemma-Credential": json.dumps(_stub_valid_credential())},
            json={"reason": "test"},
        )
        assert resp.status_code in (401, 403)
