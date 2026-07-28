"""Regression tests: cross-tenant credential issuance must be blocked.

These cover the fix for the finding that ``@require_site_admin`` only proves the
caller holds an admin-scoped lemma for *some* site, letting any site admin mint
signed permission lemmas (including admin/'*') for arbitrary other tenants via
``POST /api/v1/sites/<site_id>/...``. The mutating routes must now bind the
action to a site the caller actually administers.
"""

from __future__ import annotations

import os
import sys

import pytest
from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.authz_engine import AuthzPrincipal  # noqa: E402
import auth.decorators as decorators  # noqa: E402
import api.site_access as site_access  # noqa: E402
import api.permission_management_api as pma  # noqa: E402
import api.iam_permission_types as iam_types  # noqa: E402

ATTACKER_PPID = "did:lemma:ppid_" + ("b" * 64)
ATTACKER_SITE = "site_attacker0001"
VICTIM_SITE = "site_victim000001"
TARGET_DID = "did:lemma:ppid_" + ("c" * 64)


def _admin_principal(ppid: str, site_binding: str) -> AuthzPrincipal:
    """A perfectly valid admin credential — for the attacker's OWN site."""
    return AuthzPrincipal(
        principal_type="user_lemma",
        auth_method="lemma_header",
        ppid=ppid,
        credential_id="cred_attacker",
        permission_id="admin",
        scope=["admin", "write", "read"],
        site_binding=site_binding,
    )


@pytest.fixture
def as_attacker_admin(monkeypatch):
    """Authenticate every request as a valid admin of ATTACKER_SITE only."""
    monkeypatch.setattr(
        decorators,
        "extract_user_lemma_principal",
        lambda headers: (_admin_principal(ATTACKER_PPID, ATTACKER_SITE), None),
    )
    # The attacker administers ONLY their own site.
    monkeypatch.setattr(
        site_access,
        "verify_site_ownership",
        lambda sid, ppid: sid == ATTACKER_SITE and ppid == ATTACKER_PPID,
    )
    # Not the platform owner / operator.
    monkeypatch.setattr(
        "api.platform_owner.is_platform_owner_ppid", lambda ppid: False
    )


def _client(blueprint) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(blueprint)
    return app.test_client()


def test_grant_user_permission_blocks_cross_tenant(as_attacker_admin, monkeypatch):
    # The signing manager must never be reached for a site the caller doesn't own.
    def _boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("get_site_manager reached despite ownership denial")

    monkeypatch.setattr(pma, "get_site_manager", _boom)

    client = _client(pma.permission_api)
    resp = client.post(
        f"/api/v1/sites/{VICTIM_SITE}/users/{TARGET_DID}/permissions",
        json={"permission_id": "admin", "permission_scope": ["*"]},
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "UNAUTHORIZED_SITE_ACCESS"


def test_create_permission_blocks_cross_tenant(as_attacker_admin, monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("get_site_manager reached despite ownership denial")

    monkeypatch.setattr(pma, "get_site_manager", _boom)

    client = _client(pma.permission_api)
    resp = client.post(
        f"/api/v1/sites/{VICTIM_SITE}/permissions",
        json={
            "permission_id": "admin",
            "display_name": "Administrator",
            "scope": ["*"],
        },
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "UNAUTHORIZED_SITE_ACCESS"


def test_grant_user_permission_allows_owned_site(as_attacker_admin, monkeypatch):
    """When the ownership gate authorizes, issuance proceeds past it.

    The gate is stubbed to 'authorized' here so the test stays hermetic (no DB
    schema needed); the real gate wiring is exercised by the denial tests above.
    """
    sentinel = {"reached": False}

    monkeypatch.setattr(pma, "require_site_ownership", lambda *a, **k: None)

    def _fake_manager(site_id, site_domain=None):
        sentinel["reached"] = True
        return None  # handler returns 404 'Site not found' — gate already passed

    monkeypatch.setattr(pma, "get_site_manager", _fake_manager)

    client = _client(pma.permission_api)
    resp = client.post(
        f"/api/v1/sites/{ATTACKER_SITE}/users/{TARGET_DID}/permissions",
        json={"permission_id": "member"},
    )
    assert sentinel["reached"], "ownership gate should pass for the owned site"
    assert resp.status_code != 403


def test_iam_permission_types_grant_blocks_cross_tenant(as_attacker_admin):
    client = _client(iam_types.iam_types_bp)
    resp = client.post(
        f"/api/iam/sites/{VICTIM_SITE}/permissions/grant",
        json={"user_did": TARGET_DID, "permission_type": "admin"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "UNAUTHORIZED_SITE_ACCESS"


def test_iam_permission_types_list_blocks_cross_tenant(as_attacker_admin):
    client = _client(iam_types.iam_types_bp)
    resp = client.get(f"/api/iam/sites/{VICTIM_SITE}/permission-types")
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "UNAUTHORIZED_SITE_ACCESS"
