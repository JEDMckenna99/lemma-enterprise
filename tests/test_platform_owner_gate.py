import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.platform_owner import (
    cap_platform_role_profile,
    enforce_platform_admin_ppid,
    is_platform_owner_ppid,
    platform_owner_ppid,
    resolve_platform_login_ppid,
)
from api.services.wallet_service import wallet_service_bp
import api.services.wallet_service as wallet_service


OWNER_PPID = "did:lemma:ppid_" + ("a" * 64)
OTHER_PPID = "did:lemma:ppid_" + ("b" * 64)


@pytest.fixture(autouse=True)
def _clear_owner_env(monkeypatch):
    monkeypatch.delenv("LEMMA_PLATFORM_OWNER_PPID", raising=False)


def test_enforcement_disabled_by_default():
    assert platform_owner_ppid() is None
    assert enforce_platform_admin_ppid(OTHER_PPID, "lemma.id") is None


def test_enforcement_blocks_non_owner(monkeypatch):
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
    denied = enforce_platform_admin_ppid(OTHER_PPID, "lemma.id")
    assert denied is not None
    body, status = denied
    assert status == 403
    assert body["error"] == "platform_owner_required"


def test_cap_platform_role_downgrades_non_owner(monkeypatch):
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
    admin_profile = {
        "role": "admin",
        "permission_id": "admin_access",
        "permissions": ["admin", "read"],
        "scope": ["admin", "read"],
        "source": "site_admins",
    }
    capped = cap_platform_role_profile(OTHER_PPID, "lemma.id", admin_profile)
    assert capped["role"] == "user"
    assert capped["permission_id"] == "customer_access"

    unchanged = cap_platform_role_profile(OWNER_PPID, "lemma.id", admin_profile)
    assert unchanged["role"] == "admin"


def test_is_platform_owner_ppid(monkeypatch):
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
    assert is_platform_owner_ppid(OWNER_PPID) is True
    assert is_platform_owner_ppid(OTHER_PPID) is False


def test_restore_site_access_caps_non_owner_admin(monkeypatch):
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(wallet_service_bp)

    def _resolve_with_cap(ppid, site_id="lemma.id"):
        from api.platform_owner import cap_platform_role_profile

        return cap_platform_role_profile(
            ppid,
            site_id,
            {
                "role": "admin",
                "permission_id": "admin_access",
                "permissions": ["admin", "read"],
                "scope": ["admin", "read"],
                "source": "site_admins",
            },
        )

    monkeypatch.setattr(wallet_service, "_resolve_platform_role_for_ppid", _resolve_with_cap)
    monkeypatch.setattr(wallet_service, "_upsert_platform_membership", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "api.platform_owner.enforce_platform_login_wallet",
        lambda **kwargs: (kwargs.get("client_ppid") or OTHER_PPID, None),
    )
    monkeypatch.setattr(
        wallet_service,
        "issue_permission_lemma",
        lambda **kwargs: {"id": "cred", "subject": kwargs["subject_ppid"]},
    )

    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/restore-site-access",
            json={"ppid": OTHER_PPID, "site_id": "lemma.id"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["restored_role"] == "user"


def test_platform_login_denies_unbound_wallet_when_enforcement_on(monkeypatch):
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
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

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(wallet_service_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/platform-login",
            json={
                "ppid": OTHER_PPID,
                "wallet_id": "wallet_probe_nonexistent",
            },
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == "person_root_required"


def test_enforce_platform_login_wallet_requires_person_root(monkeypatch):
    from api.platform_owner import enforce_platform_login_wallet

    monkeypatch.setattr(
        "api.ishuman._resolve_person_id_for_wallet",
        lambda db, wallet_id: None,
    )

    ppid, denied = enforce_platform_login_wallet(
        client_ppid=OTHER_PPID,
        wallet_id="wallet_unverified",
        db=object(),
    )
    assert ppid is None
    assert denied is not None
    assert denied[1] == 403
    assert denied[0]["error"] == "person_root_required"


def test_enforce_platform_login_wallet_requires_wallet_id():
    from api.platform_owner import enforce_platform_login_wallet

    ppid, denied = enforce_platform_login_wallet(
        client_ppid=OTHER_PPID,
        wallet_id=None,
    )
    assert ppid is None
    assert denied is not None
    assert denied[0]["error"] == "wallet_id_required"


def test_enforce_platform_login_wallet_rejects_ppid_mismatch(monkeypatch):
    from api.platform_owner import enforce_platform_login_wallet

    monkeypatch.setattr(
        "api.ishuman._resolve_person_id_for_wallet",
        lambda db, wallet_id: "person_1",
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **kwargs: OWNER_PPID,
    )

    ppid, denied = enforce_platform_login_wallet(
        client_ppid=OTHER_PPID,
        wallet_id="wallet_verified",
        db=object(),
    )
    assert ppid is None
    assert denied is not None
    assert denied[0]["error"] == "ppid_mismatch"


def test_platform_login_denies_without_platform_membership(monkeypatch):
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
    monkeypatch.setattr(
        "api.platform_owner.enforce_platform_login_wallet",
        lambda **kwargs: (OWNER_PPID, None),
    )
    monkeypatch.setattr(
        wallet_service,
        "_has_platform_membership",
        lambda ppid, site_id="lemma.id": False,
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(wallet_service_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/wallet-auth/platform-login",
            json={"ppid": OWNER_PPID, "wallet_id": "wallet_verified"},
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == "platform_membership_required"


def test_resolve_platform_login_ppid_prefers_binding(monkeypatch):
    monkeypatch.setattr(
        "api.ishuman._resolve_person_id_for_wallet",
        lambda db, wallet_id: "person_1" if wallet_id == "wallet_verified" else None,
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **kwargs: OWNER_PPID,
    )

    ppid = resolve_platform_login_ppid(
        client_ppid=OTHER_PPID,
        wallet_id="wallet_verified",
        db=object(),
    )
    assert ppid == OWNER_PPID


def test_evaluate_platform_owner_bootstrap_owner_match(monkeypatch):
    from api.platform_owner import evaluate_platform_owner_bootstrap

    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
    monkeypatch.setattr(
        "api.ishuman._resolve_person_id_for_wallet",
        lambda db, wallet_id: "person_1",
    )
    monkeypatch.setattr(
        "api.platform_owner.resolve_platform_login_ppid",
        lambda **kwargs: OWNER_PPID,
    )

    status = evaluate_platform_owner_bootstrap(
        client_ppid=OWNER_PPID,
        wallet_id="wallet_verified",
        db=object(),
    )
    assert status["owner_configured"] is True
    assert status["person_root_verified"] is True
    assert status["is_platform_owner"] is True
    assert status["can_auto_issue"] is True
    assert status["ppid"] == OWNER_PPID


def test_platform_bootstrap_status_endpoint(monkeypatch):
    from api.admin_self_issue import admin_self_issue_bp

    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", OWNER_PPID)
    monkeypatch.setattr(
        "api.platform_owner.evaluate_platform_owner_bootstrap",
        lambda **kwargs: {
            "owner_configured": True,
            "person_root_verified": True,
            "is_platform_owner": True,
            "ppid_consistent": True,
            "can_auto_issue": True,
            "ppid": OWNER_PPID,
            "site_id": "lemma.id",
            "site_domain": "lemma.id",
            "admin_email": "admin@lemma.id",
        },
    )

    class _FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class _FakeSession:
        def query(self, model):
            return _FakeQuery()

        def close(self):
            pass

    monkeypatch.setattr("api.database.SessionLocal", lambda: _FakeSession())

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_self_issue_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/v1/iam/admin/platform-bootstrap/status",
            json={"ppid": OWNER_PPID, "wallet_id": "wallet_verified"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["should_auto_issue"] is True
        assert body["has_site_admin"] is False


def test_platform_bootstrap_auto_issue_endpoint(monkeypatch):
    from api.admin_self_issue import admin_self_issue_bp

    monkeypatch.setattr(
        "api.platform_owner.verify_platform_owner_wallet",
        lambda **kwargs: (OWNER_PPID, None),
    )
    monkeypatch.setattr(
        "api.platform_owner.platform_owner_admin_email",
        lambda: "admin@lemma.id",
    )
    monkeypatch.setattr(
        "api.admin_self_issue._issue_admin_credential_core",
        lambda **kwargs: {
            "success": True,
            "credential": {"id": "cred-1", "claims": {"siteId": "lemma.id"}},
            "site_id": "lemma.id",
            "site_domain": "lemma.id",
            "permission_level": "super_admin",
            "issue_time_us": 12.5,
        },
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_self_issue_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/v1/iam/admin/platform-bootstrap/auto-issue",
            json={"ppid": OWNER_PPID, "wallet_id": "wallet_verified"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["credential"]["id"] == "cred-1"


def test_platform_bootstrap_auto_issue_denies_non_owner(monkeypatch):
    from api.admin_self_issue import admin_self_issue_bp

    monkeypatch.setattr(
        "api.platform_owner.verify_platform_owner_wallet",
        lambda **kwargs: (
            None,
            (
                {
                    "success": False,
                    "error": "platform_owner_required",
                    "message": "This wallet is not the configured lemma.id platform owner.",
                },
                403,
            ),
        ),
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_self_issue_bp)

    with app.test_client() as client:
        response = client.post(
            "/api/v1/iam/admin/platform-bootstrap/auto-issue",
            json={"ppid": OTHER_PPID, "wallet_id": "wallet_other"},
        )
        assert response.status_code == 403
        body = response.get_json()
        assert body["error"] == "platform_owner_required"
