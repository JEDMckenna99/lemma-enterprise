import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.customer_accounts import customer_accounts_bp
import api.customer_accounts as customer_accounts

OWNER_PPID = "did:lemma:ppid_" + ("a" * 64)


@pytest.fixture(autouse=True)
def _clear_invite_env(monkeypatch):
    monkeypatch.setenv("LEMMA_AUTH_INVITE_ONLY", "0")


def _app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(customer_accounts_bp)
    return app


def test_register_wallet_developer_requires_person_root(monkeypatch):
    monkeypatch.setattr(
        "api.platform_owner.enforce_platform_login_wallet",
        lambda **kwargs: (
            None,
            (
                {
                    "success": False,
                    "error": "person_root_required",
                    "message": "Complete isHuman IDV on this wallet before platform login.",
                },
                403,
            ),
        ),
    )

    app = _app()
    with app.test_client() as client:
        response = client.post(
            "/api/customer/register-wallet-developer",
            json={
                "email": "dev@example.com",
                "name": "Dev User",
                "company": "Example Inc",
                "ppid": OWNER_PPID,
                "wallet_id": "wallet_unverified",
            },
        )
        assert response.status_code == 403
        assert response.get_json()["error"] == "person_root_required"


def test_register_wallet_developer_provisions_developer_access(monkeypatch):
    issued = []
    upserts = []

    monkeypatch.setattr(
        "api.platform_owner.enforce_platform_login_wallet",
        lambda **kwargs: (OWNER_PPID, None),
    )
    monkeypatch.setattr(
        "api.services.wallet_service._has_platform_membership",
        lambda ppid, site_id="lemma.id": False,
    )
    monkeypatch.setattr(
        "api.services.wallet_service._upsert_platform_membership",
        lambda *args, **kwargs: upserts.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "api.services.wallet_service.issue_permission_lemma",
        lambda **kwargs: issued.append(kwargs) or {"id": "cred_dev_1", "claims": kwargs.get("custom_claims", {})},
    )
    monkeypatch.setattr(
        customer_accounts.customer_manager,
        "get_customer_by_email",
        lambda email: None,
    )
    monkeypatch.setattr(
        customer_accounts.customer_manager,
        "create_customer",
        lambda **kwargs: {
            "success": True,
            "customer_id": "cus_test123",
            "customer_did": kwargs.get("customer_did"),
            "api_key": "lemma_test_api_key",
        },
    )

    app = _app()
    with app.test_client() as client:
        response = client.post(
            "/api/customer/register-wallet-developer",
            json={
                "email": "dev@example.com",
                "name": "Dev User",
                "company": "Example Inc",
                "ppid": OWNER_PPID,
                "wallet_id": "wallet_verified",
            },
        )
        assert response.status_code == 201
        body = response.get_json()
        assert body["success"] is True
        assert body["permission_level"] == "developer"
        assert body["permission_lemma"]["id"] == "cred_dev_1"
        assert body["api_key"] == "lemma_test_api_key"

    assert len(issued) == 1
    assert issued[0]["subject_ppid"] == OWNER_PPID
    assert issued[0]["permission_id"] == "developer_access"
    assert len(upserts) == 2


def test_register_wallet_developer_rejects_existing_membership(monkeypatch):
    monkeypatch.setattr(
        "api.platform_owner.enforce_platform_login_wallet",
        lambda **kwargs: (OWNER_PPID, None),
    )
    monkeypatch.setattr(
        "api.services.wallet_service._has_platform_membership",
        lambda ppid, site_id="lemma.id": True,
    )

    app = _app()
    with app.test_client() as client:
        response = client.post(
            "/api/customer/register-wallet-developer",
            json={
                "email": "dev@example.com",
                "name": "Dev User",
                "company": "Example Inc",
                "ppid": OWNER_PPID,
                "wallet_id": "wallet_verified",
            },
        )
        assert response.status_code == 409
        assert response.get_json()["error"] == "platform_membership_exists"
