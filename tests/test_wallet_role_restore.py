import os
import sys

from flask import Flask


# Keep imports working when running tests from repository root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.services.wallet_service import _role_to_permission_profile, wallet_service_bp
import api.services.wallet_service as wallet_service


def _app_with_wallet_service():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(wallet_service_bp)
    return app


def test_role_profile_maps_admin_developer_and_user():
    admin = _role_to_permission_profile("admin")
    assert admin["role"] == "admin"
    assert admin["permission_id"] == "admin_access"
    assert "admin" in admin["scope"]

    developer = _role_to_permission_profile("developer")
    assert developer["role"] == "developer"
    assert developer["permission_id"] == "developer_access"
    assert "developer" in developer["scope"]

    user = _role_to_permission_profile("something-unknown")
    assert user["role"] == "user"
    assert user["permission_id"] == "customer_access"
    assert user["scope"] == ["read"]


def test_restore_site_access_requires_identity_material():
    app = _app_with_wallet_service()
    with app.test_client() as client:
        response = client.post("/api/wallet-auth/restore-site-access", json={"site_id": "lemma.id"})
        assert response.status_code == 403
        body = response.get_json()
        assert body["success"] is False
        assert body["error"] == "wallet_id_required"


def test_restore_site_access_rejects_wallet_secret():
    app = _app_with_wallet_service()
    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/restore-site-access",
            json={"wallet_secret": "secret_123", "site_id": "lemma.id"},
        )
        assert response.status_code == 410
        assert response.get_json()["error"] == "wallet_secret_not_accepted"


def test_restore_site_access_issues_role_backed_lemma(monkeypatch):
    app = _app_with_wallet_service()
    issued_calls = []

    monkeypatch.setattr(
        wallet_service,
        "derive_user_ppid",
        lambda site_id, wallet_secret=None, passkey_credential_id=None: "did:lemma:ppid_" + ("a" * 64),
    )
    monkeypatch.setattr(
        wallet_service,
        "_resolve_platform_role_for_ppid",
        lambda ppid, site_id="lemma.id": {
            "role": "admin",
            "permission_id": "admin_access",
            "permissions": ["admin", "write", "read", "access", "developer"],
            "scope": ["admin", "write", "read", "developer"],
            "source": "site_admins",
        },
    )

    def _fake_issue_permission_lemma(**kwargs):
        issued_calls.append(kwargs)
        return {"id": "cred_restore_1", "claims": {"permissionId": kwargs.get("permission_id")}}

    monkeypatch.setattr(wallet_service, "issue_permission_lemma", _fake_issue_permission_lemma)
    monkeypatch.setattr(
        "api.platform_owner.enforce_platform_login_wallet",
        lambda **kwargs: ("did:lemma:ppid_" + ("a" * 64), None),
    )
    monkeypatch.setattr(
        wallet_service,
        "_has_platform_membership",
        lambda ppid, site_id="lemma.id": True,
    )
    monkeypatch.setattr(wallet_service, "_upsert_platform_membership", lambda *args, **kwargs: None)

    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/restore-site-access",
            json={
                "ppid": "did:lemma:ppid_" + ("a" * 64),
                "wallet_id": "wallet_verified",
                "site_id": "lemma.id",
            },
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["restored_role"] == "admin"
        assert body["restored_from"] == "site_admins"
        assert body["permission_lemma"]["id"] == "cred_restore_1"

    assert len(issued_calls) == 1
    assert issued_calls[0]["site_id"] == "lemma.id"
    assert issued_calls[0]["permission_id"] == "admin_access"
    assert issued_calls[0]["account_type"] == "admin"
