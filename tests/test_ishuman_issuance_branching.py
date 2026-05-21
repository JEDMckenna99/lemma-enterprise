from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from tests.wallet_test_helpers import DERIVE_ASSERTION_FIELDS, START_ASSERTION_FIELDS


@pytest.mark.unit
def test_derive_site_proof_cache_miss_creates_new_mapping(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import DerivedCredential, IsHumanVerification

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_existing_1",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_001",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_site_new_001",
            "subject": ppid,
            "wallet_id": wallet_id,
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "issuer": "did:lemma:test",
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_existing_1",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "Example.com",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["cached"] is False
    assert payload["credential"]["id"] == "ishuman_site_new_001"
    assert len(db.store.data[IsHumanVerification.__name__]) == 1
    assert len(db.store.data[DerivedCredential.__name__]) == 1
    assert db.store.data[DerivedCredential.__name__][0].target_site == "example.com"


@pytest.mark.unit
def test_derive_site_proof_cached_reuses_existing_credential_id(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    make_derived_credential,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import DerivedCredential

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_existing_2",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    db.store.data["DerivedCredential"].append(
        make_derived_credential(
            master_credential_id="ishuman_master_existing_2",
            derived_credential_id="ishuman_site_cached_001",
            wallet_id="wallet_test_001",
            target_site="example.com",
            derived_ppid="did:lemma:ppid_site_cached",
        )
    )

    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_cached",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ephemeral_should_be_replaced",
            "subject": ppid,
            "wallet_id": wallet_id,
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "issuer": "did:lemma:test",
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_existing_2",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["cached"] is True
    assert payload["credential"]["id"] == "ishuman_site_cached_001"
    assert len(db.store.data[DerivedCredential.__name__]) == 1


@pytest.mark.unit
def test_no_master_then_master_issued_then_site_derived(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification, DerivedCredential

    os.environ["STRIPE_IDENTITY_WEBHOOK_SECRET"] = "whsec_test_123"
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "billing.stripe_manager.StripeManager.create_identity_verification_session",
        lambda self, user_id, return_url: {
            "success": True,
            "session_id": "vs_branch_123",
            "client_secret": "cs_branch_123",
            "url": "https://verify.stripe.test/session",
        },
    )
    monkeypatch.setattr(
        "stripe.Webhook.construct_event",
        lambda payload, sig_header, secret: {
            "type": "identity.verification_session.verified",
            "data": {"object": {"id": "vs_branch_123", "metadata": {"user_id": "wallet_test_001"}}},
        },
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **kwargs: f"did:lemma:ppid::{kwargs['rp_id']}::{kwargs.get('wallet_id')}",
    )

    def _issue(_ppid, _wallet_id=None, site_id=None, **kwargs):
        if site_id:
            return {"id": "ishuman_site_created_123", "claims": {"isHuman": True, "siteId": site_id}}
        return {"id": "ishuman_master_created_123", "claims": {"isHuman": True, "siteId": "lemma.id"}}

    monkeypatch.setattr("api.ishuman._issue_ishuman_credential", _issue)

    start = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "return_url": "https://lemma.id/app",
            },
            START_ASSERTION_FIELDS,
        ),
    )
    assert start.status_code == 200
    session_id = start.get_json()["session_id"]

    webhook = ishuman_client.post(
        "/api/webhooks/stripe-identity",
        data=b"{}",
        headers={"Stripe-Signature": "t=1,v1=abc"},
    )
    assert webhook.status_code == 200

    master_rows = db.store.data[IsHumanVerification.__name__]
    assert len(master_rows) == 1
    assert master_rows[0].status == "verified"
    assert master_rows[0].credential_id == "ishuman_master_created_123"
    assert master_rows[0].session_id == session_id
    assert master_rows[0].expires_at > datetime.utcnow() + timedelta(days=300)

    derive = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_created_123",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "customer-a.example",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert derive.status_code == 200
    derive_payload = derive.get_json()
    assert derive_payload["success"] is True
    assert derive_payload["cached"] is False
    assert derive_payload["credential"]["id"] == "ishuman_site_created_123"
    assert len(db.store.data[DerivedCredential.__name__]) == 1
