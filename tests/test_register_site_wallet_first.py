"""Tests for wallet-first register-site flow."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask, g


class _FakeManager:
    permissions = {}

    def __init__(self, site_id, site_domain):
        self.site_id = site_id
        self.site_domain = site_domain

    class issuer:
        @staticmethod
        def get_did():
            return "did:lemma:test_site_issuer"

    def add_permission(self, info):
        self.permissions[info["permission_id"]] = info

    def issue_permission_lemma(self, user_did, permission_id, expiry_days=90, custom_claims=None):
        return {
            "id": "cred_register_test",
            "subject": user_did,
            "issuer": self.issuer.get_did(),
            "claims": custom_claims or {},
        }


@pytest.fixture(name="register_env")
def fixture_register_env(fake_ishuman_db_session_factory, monkeypatch):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setattr("api.real_iam_manager.RealIAMSubnetManager", _FakeManager)
    monkeypatch.setattr("api.storage_helpers.upsert_site_to_postgres", lambda *args, **kwargs: True)

    wallet_ppid = "did:lemma:ppid_" + ("e" * 64)
    customer = SimpleNamespace(
        customer_id="cust_register_test",
        email="dev@example.com",
        company="Example Co",
        sites=[],
        customer_did=None,
    )

    monkeypatch.setattr(
        "api.customer_accounts.customer_manager.get_customer",
        lambda cid: customer if cid == "cust_register_test" else None,
    )
    monkeypatch.setattr(
        "api.customer_accounts._extract_customer_id_from_request",
        lambda: "cust_register_test",
    )
    monkeypatch.setattr(
        "api.customer_accounts.customer_manager.generate_additional_api_key",
        lambda cid, name, site_id=None: {
            "success": True,
            "api_key": "lm_register_test_key",
            "key_data": {"site_id": site_id},
        },
    )
    monkeypatch.setattr("api.customer_accounts.customer_manager.db_available", False)
    monkeypatch.setattr(
        "api.customer_accounts.customer_manager.cache_customer",
        lambda cust: None,
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    return app, fake_ishuman_db_session_factory, wallet_ppid


@pytest.mark.unit
def test_register_site_requires_wallet_ppid(register_env):
    from api.customer_accounts import register_customer_site

    handler = getattr(register_customer_site, "__wrapped__", register_customer_site)
    app, _factory, _wallet_ppid = register_env
    with app.test_request_context(
        "/api/customer/register-site",
        method="POST",
        json={"site_domain": "app.example.com"},
    ):
        resp = handler()
        if isinstance(resp, tuple):
            status = resp[1]
            body = resp[0].get_json()
        else:
            status = resp.status_code
            body = resp.get_json()
    assert status == 400
    assert body["error"] == "wallet_ppid_required"


@pytest.mark.unit
def test_register_site_issues_admin_to_wallet_and_creates_site_row(register_env):
    from api.customer_accounts import register_customer_site
    from api.database import Site, SiteAdmin

    handler = getattr(register_customer_site, "__wrapped__", register_customer_site)
    app, factory, wallet_ppid = register_env
    with app.test_request_context(
        "/api/customer/register-site",
        method="POST",
        json={"site_domain": "https://WWW.App.Example.com/login"},
    ):
        g.ppid = wallet_ppid
        resp = handler()
        if isinstance(resp, tuple):
            status = resp[1]
            body = resp[0].get_json()
        else:
            status = resp.status_code
            body = resp.get_json()

    assert status == 200
    assert body["success"] is True
    assert body["site_domain"] == "app.example.com"
    assert body["admin_credential"]["subject"] == wallet_ppid
    assert body["admin_credential"]["claims"]["siteId"] == "app.example.com"

    sites = factory.store.data[Site.__name__]
    assert len(sites) == 1
    assert sites[0].site_domain == "app.example.com"
    assert sites[0].api_key == "lm_register_test_key"

    admins = factory.store.data[SiteAdmin.__name__]
    assert len(admins) == 1
    assert admins[0].admin_did == wallet_ppid
    assert admins[0].is_active is True
