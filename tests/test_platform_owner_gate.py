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
