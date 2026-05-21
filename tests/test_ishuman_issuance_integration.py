from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from tests.wallet_test_helpers import DERIVE_ASSERTION_FIELDS, START_ASSERTION_FIELDS


@pytest.mark.integration
def test_start_verification_persists_pending_session(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification

    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "billing.stripe_manager.StripeManager.create_identity_verification_session",
        lambda self, user_id, return_url: {
            "success": True,
            "session_id": "vs_integration_001",
            "client_secret": "cs_integration_001",
            "url": "https://verify.stripe.test/session",
        },
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_start_001",
    )

    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "return_url": "https://customer.example/return",
            },
            START_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["stripe_session_id"] == "vs_integration_001"

    rows = db.store.data[IsHumanVerification.__name__]
    assert len(rows) == 1
    assert rows[0].session_id == payload["session_id"]
    assert rows[0].wallet_id == "wallet_test_001"
    assert rows[0].ppid == "did:lemma:ppid_start_001"
    assert rows[0].status == "pending"
    assert rows[0].metadata_json["return_url"] == "https://customer.example/return"


@pytest.mark.integration
def test_webhook_verified_updates_master_record(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    from api.database import IsHumanVerification

    os.environ["STRIPE_IDENTITY_WEBHOOK_SECRET"] = "whsec_test_456"

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_integration_2",
            stripe_session_id="vs_integration_002",
            wallet_id="wallet_test_001",
            ppid=None,
            credential_id=None,
            status="pending",
            verified_at=None,
            issued_at=None,
            expires_at=None,
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "stripe.Webhook.construct_event",
        lambda payload, sig_header, secret: {
            "type": "identity.verification_session.verified",
            "data": {"object": {"id": "vs_integration_002", "metadata": {"user_id": "wallet_test_001"}}},
        },
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_webhook_001",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_master_integration_001",
            "issuerInfo": {"did": "did:lemma:issuer:test"},
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "subject": ppid,
        },
    )

    resp = ishuman_client.post(
        "/api/webhooks/stripe-identity",
        data=b"{}",
        headers={"Stripe-Signature": "t=1,v1=test"},
    )
    assert resp.status_code == 200

    row = db.store.data[IsHumanVerification.__name__][0]
    assert row.status == "verified"
    assert row.ppid == "did:lemma:ppid_webhook_001"
    assert row.credential_id == "ishuman_master_integration_001"
    assert row.verified_at is not None
    assert row.issued_at is not None
    assert row.expires_at is not None
    assert row.metadata_json["credential_issuer_did"] == "did:lemma:issuer:test"


@pytest.mark.integration
def test_verification_status_returns_stable_credential_id(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_status_001",
            credential_id="ishuman_master_stable_001",
            status="verified",
            ppid="did:lemma:ppid_status_001",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ephemeral_should_be_replaced",
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "subject": ppid,
        },
    )

    resp = ishuman_client.get("/api/ishuman/verification-status/ishuman_sess_status_001")
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["status"] == "verified"
    assert payload["credential_id"] == "ishuman_master_stable_001"
    assert payload["credential"]["id"] == "ishuman_master_stable_001"
    assert payload["credential"]["subject"] == "did:lemma:ppid_status_001"


@pytest.mark.integration
def test_derive_site_proof_error_paths(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    make_revocation_row,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    not_found = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "does_not_exist",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert not_found.status_code == 404
    assert not_found.get_json()["error"] == "master_credential_not_found"

    invalid_site = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_missing",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert invalid_site.status_code == 400
    assert "required" in invalid_site.get_json()["error"]

    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_expired_001",
            wallet_id="wallet_test_001",
            expires_at=datetime.utcnow() - timedelta(seconds=5),
            status="verified",
        )
    )
    expired = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_expired_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert expired.status_code == 403
    assert expired.get_json()["error"] == "master_credential_expired"

    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_revoked_001",
            wallet_id="wallet_test_001",
            status="verified",
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
    )
    db.store.data["RevocationList"].append(
        make_revocation_row(wallet_id="wallet_test_001", revocation_type="wallet")
    )
    revoked = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_revoked_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert revoked.status_code == 403
    assert revoked.get_json()["error"] == "wallet_revoked"


@pytest.mark.integration
def test_derive_site_proof_persists_derived_mapping(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import DerivedCredential

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_integration_derive_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_derive_001",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_site_integration_001",
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "subject": ppid,
            "issuer": "did:lemma:test",
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_integration_derive_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "customer.example",
                "site_signing_pubkey": "",
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["cached"] is False
    assert payload["credential"]["id"] == "ishuman_site_integration_001"
    assert len(db.store.data[DerivedCredential.__name__]) == 1
    assert db.store.data[DerivedCredential.__name__][0].target_site == "customer.example"
