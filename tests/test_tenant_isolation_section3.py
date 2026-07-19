"""Section 3 tenant isolation and site ownership enforcement tests."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
from flask import Flask, g, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("LEMMA_DOMAIN_OWNERSHIP_ENFORCE", "0")

from api.site_access import (  # noqa: E402
    authorize_site_access,
    resolve_site_from_api_key,
    verify_site_ownership,
)
import api.site_access as site_access  # noqa: E402

OWNER_PPID = "did:lemma:ppid_" + ("a" * 64)
OTHER_PPID = "did:lemma:ppid_" + ("b" * 64)
SITE_A = "site_aaaaaaaaaaaa"
SITE_B = "site_bbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def _disable_domain_enforcement(monkeypatch):
    monkeypatch.setenv("LEMMA_DOMAIN_OWNERSHIP_ENFORCE", "0")


def test_authorize_site_access_rejects_non_owner(monkeypatch):
    app = Flask(__name__)
    with app.test_request_context():
        g.ppid = OTHER_PPID
        monkeypatch.setattr(site_access, "verify_site_ownership", lambda sid, ppid: False)
        site, denied = authorize_site_access(SITE_A)
        assert site is None
        assert denied is not None
        resp, status = denied
        assert status == 403
        payload = resp.get_json()
        assert payload["code"] == "UNAUTHORIZED_SITE_ACCESS"


def test_authorize_site_access_api_key_mismatch(monkeypatch):
    app = Flask(__name__)

    class _Site:
        site_id = SITE_A

    with app.test_request_context(headers={"X-API-Key": "lm_test_key"}):
        monkeypatch.setattr(site_access, "resolve_site_from_api_key", lambda key=None: _Site())
        site, denied = authorize_site_access(SITE_B, allow_site_api_key=True)
        assert site is None
        assert denied is not None
        _, status = denied
        assert status == 403


def test_audit_logs_reject_cross_tenant_site(monkeypatch):
    from api.audit_api import query_audit_logs

    monkeypatch.setattr(
        "api.audit_api.authorize_site_access",
        lambda site_id, **kwargs: (None, (jsonify({"code": "UNAUTHORIZED_SITE_ACCESS"}), 403)),
    )

    handler = query_audit_logs
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__

    app = Flask(__name__)
    with app.test_request_context("/api/v1/audit/logs?site_id=site_other"):
        resp = handler()
        if isinstance(resp, tuple):
            assert resp[1] == 403
        else:
            assert resp.status_code == 403


def test_billing_checkout_rejects_unowned_explicit_site(monkeypatch):
    from api.stripe_usage_billing import _resolve_site_for_checkout

    db = SimpleNamespace()
    db.query = lambda *args, **kwargs: SimpleNamespace(
        filter_by=lambda **kw: SimpleNamespace(first=lambda: SimpleNamespace(site_id=SITE_B, site_domain="b.example.com", admin_email="b@example.com"))
    )
    monkeypatch.setattr(site_access, "verify_site_ownership", lambda sid, ppid: False)

    result = _resolve_site_for_checkout(db, SITE_B, customer=None, ppid=OWNER_PPID)
    assert result is None


def test_api_key_create_requires_site_ownership(monkeypatch):
    from api.customer_accounts import manage_api_keys

    monkeypatch.setattr(
        "api.customer_accounts._extract_customer_id_from_request",
        lambda: "cust_a",
    )
    monkeypatch.setattr(
        "api.site_access.authorize_site_access",
        lambda site_id, **kwargs: (None, (jsonify({"code": "UNAUTHORIZED_SITE_ACCESS"}), 403)),
    )

    handler = manage_api_keys
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__

    app = Flask(__name__)
    with app.test_request_context(
        "/api/customer/api-keys",
        method="POST",
        json={"site_id": SITE_B, "name": "Key"},
    ):
        resp = handler()
        assert resp[1] == 403


def test_register_site_conflict_without_transfer(monkeypatch):
    from api.customer_accounts import register_customer_site

    wallet_ppid = OWNER_PPID
    customer = SimpleNamespace(
        customer_id="cust_a",
        email="a@example.com",
        company="A",
        sites=[],
        customer_did=wallet_ppid,
    )

    monkeypatch.setattr(
        "api.customer_accounts.customer_manager.get_customer",
        lambda cid: customer,
    )
    monkeypatch.setattr(
        "api.customer_accounts._extract_customer_id_from_request",
        lambda: "cust_a",
    )
    monkeypatch.setattr(
        site_access,
        "site_has_existing_owner",
        lambda site_id, domain, ppid: True,
    )
    monkeypatch.setattr(
        "api.domain_transfers.pending_transfer_allows_registration",
        lambda db, site_id, customer_id: False,
    )
    monkeypatch.setattr(
        "auth.decorators.require_customer_or_admin",
        lambda f: f,
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/customer/register-site",
        method="POST",
        json={"site_domain": "taken.example.com", "verification_token": "tok"},
    ):
        g.ppid = wallet_ppid
        handler = getattr(register_customer_site, "__wrapped__", register_customer_site)
        resp = handler()
        assert resp[1] == 409
        body = resp[0].get_json()
        assert body["code"] == "SITE_DOMAIN_CONFLICT"


def test_domain_verification_required_when_enforced(monkeypatch):
    monkeypatch.setenv("LEMMA_DOMAIN_OWNERSHIP_ENFORCE", "1")
    from api.customer_accounts import register_customer_site

    wallet_ppid = OWNER_PPID
    customer = SimpleNamespace(
        customer_id="cust_a",
        email="a@example.com",
        company="A",
        sites=[],
        customer_did=wallet_ppid,
    )
    monkeypatch.setattr("api.customer_accounts.customer_manager.get_customer", lambda cid: customer)
    monkeypatch.setattr("api.customer_accounts._extract_customer_id_from_request", lambda: "cust_a")
    monkeypatch.setattr(site_access, "site_has_existing_owner", lambda *args: False)
    monkeypatch.setattr("auth.decorators.require_customer_or_admin", lambda f: f)

    app = Flask(__name__)
    with app.test_request_context(
        "/api/customer/register-site",
        method="POST",
        json={"site_domain": "new.example.com"},
    ):
        g.ppid = wallet_ppid
        handler = getattr(register_customer_site, "__wrapped__", register_customer_site)
        resp = handler()
        assert resp[1] == 400
        assert resp[0].get_json()["code"] == "DOMAIN_VERIFICATION_REQUIRED"


def test_resolve_site_from_api_key_delegates(monkeypatch):
    class _Site:
        site_id = SITE_A

    monkeypatch.setattr(site_access, "resolve_site_from_api_key", lambda key=None: _Site())
    from api.ishuman import _resolve_site_from_request_api_key

    app = Flask(__name__)
    with app.test_request_context(headers={"X-API-Key": "lm_x"}):
        site = _resolve_site_from_request_api_key()
        assert site.site_id == SITE_A


def test_apply_tenant_context_noop_on_sqlite():
    from api.database import SessionLocal, apply_tenant_context

    db = SessionLocal()
    try:
        apply_tenant_context(db, SITE_A)
    finally:
        db.close()
