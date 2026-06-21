"""Stripe usage billing: webhooks, access gate, and checkout."""

from __future__ import annotations

from datetime import datetime

import pytest

from billing.billing_access import check_site_billing_allows_issuance
from billing.stripe_webhook_handlers import (
    dispatch_stripe_billing_event,
    handle_invoice_payment_failed,
    handle_invoice_paid,
    map_stripe_subscription_status,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "stripe_status,expected",
    [
        ("active", "active"),
        ("trialing", "active"),
        ("past_due", "past_due"),
        ("unpaid", "past_due"),
        ("canceled", "canceled"),
        ("incomplete", "none"),
    ],
)
def test_map_stripe_subscription_status(stripe_status, expected):
    assert map_stripe_subscription_status(stripe_status) == expected


@pytest.mark.unit
def test_invoice_paid_activates_customer(fake_ishuman_db_session_factory):
    from api.database import Customer

    store = fake_ishuman_db_session_factory.store
    store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_lemma_001",
            email="dev@example.com",
            stripe_customer_id="cus_stripe_001",
            subscription_status="past_due",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    assert handle_invoice_paid(
        db,
        {"customer": "cus_stripe_001", "subscription": "sub_123"},
    )

    customer = store.data[Customer.__name__][0]
    assert customer.subscription_status == "active"
    assert customer.monthly_usage["stripe_subscription_id"] == "sub_123"


@pytest.mark.unit
def test_invoice_payment_failed_marks_past_due(fake_ishuman_db_session_factory):
    from api.database import Customer

    store = fake_ishuman_db_session_factory.store
    store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_lemma_002",
            email="billing@example.com",
            stripe_customer_id="cus_stripe_002",
            subscription_status="active",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    assert handle_invoice_payment_failed(db, {"customer": "cus_stripe_002"})

    customer = store.data[Customer.__name__][0]
    assert customer.subscription_status == "past_due"


@pytest.mark.unit
def test_dispatch_checkout_session_completed(fake_ishuman_db_session_factory):
    from api.database import Customer

    store = fake_ishuman_db_session_factory.store
    store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_lemma_003",
            email="owner@example.com",
            subscription_status="none",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_stripe_003",
                "customer_email": "owner@example.com",
                "subscription": "sub_new",
                "metadata": {
                    "lemma_site_id": "site_abc",
                    "lemma_customer_id": "cus_lemma_003",
                },
            }
        },
    }
    assert dispatch_stripe_billing_event(db, event)

    customer = store.data[Customer.__name__][0]
    assert customer.stripe_customer_id == "cus_stripe_003"
    assert customer.subscription_status == "active"


@pytest.mark.unit
def test_billing_gate_blocks_past_due(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import Customer, Site

    monkeypatch.setenv("LEMMA_BILLING_ENFORCEMENT", "1")

    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="site_blocked",
            site_domain="blocked.example",
            company_name="Blocked Co",
            admin_email="billing@example.com",
            api_key="key_test",
            oauth_client_id="oauth_test",
            oauth_client_secret="secret_test",
        )
    )
    store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_lemma_004",
            email="billing@example.com",
            stripe_customer_id="cus_stripe_004",
            subscription_status="past_due",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    assert check_site_billing_allows_issuance(db, "blocked.example") == "billing_past_due"


@pytest.mark.unit
def test_billing_gate_blocks_unprovisioned_customer(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import Site

    monkeypatch.setenv("LEMMA_BILLING_ENFORCEMENT", "1")

    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="site_new",
            site_domain="new.example",
            company_name="New Co",
            admin_email="newdev@example.com",
            api_key="key_test",
            oauth_client_id="oauth_test",
            oauth_client_secret="secret_test",
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    assert check_site_billing_allows_issuance(db, "new.example") == "billing_setup_required"


@pytest.mark.unit
def test_billing_gate_allows_demo_sites(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import Site

    monkeypatch.setenv("LEMMA_BILLING_ENFORCEMENT", "1")

    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="site_demo_tickets",
            site_domain="tickets-demo.lemma.id",
            company_name="Ticketing Demo",
            admin_email="demo+tickets@lemma.id",
            api_key="key_test",
            oauth_client_id="oauth_test",
            oauth_client_secret="secret_test",
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    assert check_site_billing_allows_issuance(db, "tickets-demo.lemma.id") is None


@pytest.mark.unit
def test_billing_gate_allows_unregistered_host(monkeypatch, fake_ishuman_db_session_factory):
    monkeypatch.setenv("LEMMA_BILLING_ENFORCEMENT", "1")
    db = fake_ishuman_db_session_factory.session_local()
    assert check_site_billing_allows_issuance(db, "unregistered.example") is None


@pytest.mark.unit
def test_billing_gate_allows_active(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import Customer, Site

    monkeypatch.setenv("LEMMA_BILLING_ENFORCEMENT", "1")

    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="site_ok",
            site_domain="ok.example",
            company_name="OK Co",
            admin_email="active@example.com",
            api_key="key_test",
            oauth_client_id="oauth_test",
            oauth_client_secret="secret_test",
        )
    )
    store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_lemma_005",
            email="active@example.com",
            stripe_customer_id="cus_stripe_005",
            subscription_status="active",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    assert check_site_billing_allows_issuance(db, "ok.example") is None


@pytest.mark.unit
def test_resolve_site_for_checkout_uses_ppid_owned_sites(monkeypatch, fake_ishuman_db_session_factory):
    from datetime import datetime

    from api.database import Site
    from api.stripe_usage_billing import _resolve_site_for_checkout

    ppid = "did:lemma:ppid_" + ("a" * 64)
    store = fake_ishuman_db_session_factory.store
    store.data[Site.__name__].append(
        Site(
            site_id="lemma.id",
            site_domain="lemma.id",
            company_name="Lemma Platform",
            admin_email="platform@lemma.id",
            api_key="key_test",
            oauth_client_id="oauth_test",
            oauth_client_secret="secret_test",
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()

    class FakeCustomer:
        email = "owner@example.com"
        billing_email = "owner@example.com"
        sites = []

    monkeypatch.setattr(
        "api.developer_api._get_owned_site_ids",
        lambda _db, owner_ppid: ["lemma.id"] if owner_ppid == ppid else [],
    )

    resolved = _resolve_site_for_checkout(db, "", FakeCustomer(), ppid=ppid)
    assert resolved == {
        "site_id": "lemma.id",
        "site_domain": "lemma.id",
        "admin_email": "platform@lemma.id",
    }


@pytest.mark.unit
def test_derive_site_proof_blocked_when_billing_past_due(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import Customer, Site
    from tests.wallet_test_helpers import SITE_SIGNING_PUBKEY_B64

    monkeypatch.setenv("LEMMA_BILLING_ENFORCEMENT", "1")

    factory = fake_ishuman_db_session_factory
    factory.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_verified_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    factory.store.data[Site.__name__].append(
        Site(
            site_id="site_gate",
            site_domain="gate.example",
            company_name="Gate Co",
            admin_email="pastdue@example.com",
            api_key="key_test",
            oauth_client_id="oauth_test",
            oauth_client_secret="secret_test",
        )
    )
    factory.store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_gate",
            email="pastdue@example.com",
            stripe_customer_id="cus_stripe_gate",
            subscription_status="past_due",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", factory.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_gate",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_site_gate_001",
            "subject": ppid,
            "claims": {"isHuman": True},
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "gate.example",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            ["target_site", "site_signing_pubkey"],
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 402, payload
    assert payload["error"] == "billing_past_due"
