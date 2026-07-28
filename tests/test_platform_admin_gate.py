"""Regression tests: platform-operator endpoints require a platform admin.

Covers the fix for the finding that ``@require_site_admin`` / ``@require_admin``
granted the entire ``/api/admin/*`` platform surface to any holder of an
admin-scoped lemma for their own relying site (the platform-owner check only
fired when the *caller's own* credential was bound to a platform site).

``require_platform_admin`` must additionally require the verified principal to
be the env-pinned platform owner or an active lemma.id / lemma_platform
SiteAdmin — using server-side authoritative checks only (never the forgeable
unsigned admin-lemma context).
"""

from __future__ import annotations

import os
import sys

import pytest
from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.authz_engine import AuthzPrincipal  # noqa: E402
import auth.decorators as decorators  # noqa: E402

CUSTOMER_ADMIN_PPID = "did:lemma:ppid_" + ("d" * 64)
CUSTOMER_SITE = "tickets.example.com"


def _admin_principal(ppid: str, site_binding: str) -> AuthzPrincipal:
    return AuthzPrincipal(
        principal_type="user_lemma",
        auth_method="lemma_header",
        ppid=ppid,
        credential_id="cred_x",
        permission_id="admin",
        scope=["admin", "write", "read"],
        site_binding=site_binding,
    )


def _client() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/api/admin/thing", methods=["GET"])
    @decorators.require_platform_admin
    def _thing():
        return jsonify({"ok": True})

    return app.test_client()


@pytest.fixture
def authed_as_customer_admin(monkeypatch):
    """require_credential sees a valid admin lemma bound to a customer site."""
    monkeypatch.setattr(
        decorators,
        "extract_user_lemma_principal",
        lambda headers: (_admin_principal(CUSTOMER_ADMIN_PPID, CUSTOMER_SITE), None),
    )


def test_customer_site_admin_denied_platform_route(authed_as_customer_admin, monkeypatch):
    monkeypatch.setattr("api.platform_owner.is_platform_owner_ppid", lambda ppid: False)
    monkeypatch.setattr("api.site_access.verify_site_ownership", lambda sid, ppid: False)

    resp = _client().get("/api/admin/thing")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "platform_admin_required"


def test_platform_owner_allowed(authed_as_customer_admin, monkeypatch):
    monkeypatch.setattr("api.platform_owner.is_platform_owner_ppid", lambda ppid: True)

    resp = _client().get("/api/admin/thing")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_lemma_platform_site_admin_allowed(authed_as_customer_admin, monkeypatch):
    monkeypatch.setattr("api.platform_owner.is_platform_owner_ppid", lambda ppid: False)
    monkeypatch.setattr(
        "api.site_access.verify_site_ownership",
        lambda sid, ppid: sid in ("lemma.id", "lemma_platform"),
    )

    resp = _client().get("/api/admin/thing")
    assert resp.status_code == 200


def test_unsigned_admin_lemma_context_cannot_forge_platform_admin(
    authed_as_customer_admin, monkeypatch
):
    """The gate must not consult the client-forgeable operator fallback.

    If require_platform_admin ever routed through is_platform_operator_ppid
    (whose _is_lemma_platform_operator fallback trusts an UNVERIFIED admin-lemma
    context), a customer admin could forge platform access. Here that fallback
    would return True, yet the DB/env checks are False, so access must be denied.
    """
    monkeypatch.setattr("api.platform_owner.is_platform_owner_ppid", lambda ppid: False)
    monkeypatch.setattr("api.site_access.verify_site_ownership", lambda sid, ppid: False)
    monkeypatch.setattr(
        "api.site_access.is_platform_operator_ppid", lambda ppid=None: True
    )

    resp = _client().get("/api/admin/thing")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "platform_admin_required"


def test_non_admin_principal_denied_before_platform_check(monkeypatch):
    """A non-admin credential is rejected by the underlying admin-scope gate."""
    monkeypatch.setattr(
        decorators,
        "extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid=CUSTOMER_ADMIN_PPID,
                credential_id="cred_r",
                permission_id="read",
                scope=["read"],
                site_binding=CUSTOMER_SITE,
            ),
            None,
        ),
    )
    resp = _client().get("/api/admin/thing")
    assert resp.status_code == 403
