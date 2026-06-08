import os
import sys

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.services.wallet_service import wallet_service_bp
import api.services.wallet_service as wallet_service
from api.wallet_session_sync import wallet_session_sync_bp


def _wallet_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(wallet_service_bp)
    app.register_blueprint(wallet_session_sync_bp)
    return app


def test_wallet_auth_issue_rejects_wallet_secret():
    app = _wallet_app()
    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/issue",
            json={"site_id": "lemma.id", "wallet_secret": "ab" * 32},
        )
        assert response.status_code == 410
        body = response.get_json()
        assert body["error"] == "wallet_secret_not_accepted"


def test_restore_site_access_accepts_ppid_only(monkeypatch):
    app = _wallet_app()
    ppid = "did:lemma:ppid_" + ("a" * 64)

    monkeypatch.setattr(
        wallet_service,
        "_resolve_platform_role_for_ppid",
        lambda _ppid, site_id="lemma.id": {
            "role": "user",
            "permission_id": "customer_access",
            "permissions": ["read"],
            "scope": ["read"],
            "source": "default",
        },
    )
    monkeypatch.setattr(
        wallet_service,
        "_upsert_platform_membership",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        wallet_service,
        "issue_permission_lemma",
        lambda **kwargs: {"id": "cred_restore_ppid", "claims": {}},
    )

    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/restore-site-access",
            json={"ppid": ppid, "site_id": "lemma.id"},
        )
        assert response.status_code == 200
        assert response.get_json()["success"] is True


def test_redirect_token_endpoints_return_gone(monkeypatch):
    app = _wallet_app()
    monkeypatch.setattr(
        "api.wallet_session_sync._origin_allowed",
        lambda origin: origin == "https://customer.example",
    )
    with app.test_client() as client:
        create = client.post(
            "/api/wallet/create-redirect-token",
            json={"wallet_id": "wallet_test", "wallet_secret": "ab" * 32},
            headers={"Origin": "https://lemma.id"},
        )
        assert create.status_code == 410
        assert create.get_json()["error"] == "redirect_token_removed"

        exchange = client.post(
            "/api/wallet/exchange-redirect-token",
            json={"token": "legacy-token"},
            headers={"Origin": "https://customer.example"},
        )
        assert exchange.status_code == 410
        assert exchange.get_json()["error"] == "redirect_token_removed"
