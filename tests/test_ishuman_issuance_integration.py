from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from tests.wallet_test_helpers import (
    DERIVE_ASSERTION_FIELDS,
    SITE_SIGNING_PUBKEY_B64,
    START_ASSERTION_FIELDS,
    STATUS_CLAIM_ASSERTION_FIELDS,
)


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
    # Didit is the default IDV rail (it replaced Stripe Identity), so a start
    # request with no explicit provider must route to didit.
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.create_identity_verification_session",
        lambda self, user_id, return_url, callback_url=None: {
            "success": True,
            "session_id": "didit_integration_001",
            "url": "https://verify.didit.test/session",
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "ppid": "did:lemma:ppid_" + ("a" * 64),
                "return_url": "https://customer.example/return",
            },
            START_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["provider"] == "didit"
    assert payload["provider_session_id"] == "didit_integration_001"
    # Didit is a hosted redirect; no Stripe client_secret/session shape.
    assert "client_secret" not in payload
    assert "stripe_session_id" not in payload

    rows = db.store.data[IsHumanVerification.__name__]
    assert len(rows) == 1
    assert rows[0].session_id == payload["session_id"]
    assert rows[0].wallet_id == "wallet_test_001"
    assert rows[0].issuer_id == "didit"
    assert rows[0].provider_session_id == "didit_integration_001"
    assert rows[0].stripe_session_id is None
    assert rows[0].ppid == "did:lemma:ppid_" + ("a" * 64)
    assert rows[0].status == "pending"
    assert rows[0].metadata_json["return_url"] == "https://customer.example/return"


@pytest.mark.integration
def test_webhook_verified_updates_master_record(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    """Didit webhook issuance is covered by test_ishuman_didit_issuance.py."""
    pytest.skip("Stripe Identity webhook removed; see test_didit_webhook_verified_issues_master")


@pytest.mark.integration
def test_verification_status_poll_hides_credential_until_claim(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_status_001",
            credential_id="ishuman_master_stable_001",
            status="verified",
            ppid="did:lemma:ppid_status_001",
            wallet_id="wallet_test_001",
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

    poll = ishuman_client.get("/api/ishuman/verification-status/ishuman_sess_status_001")
    poll_payload = poll.get_json()

    assert poll.status_code == 200
    assert poll_payload["success"] is True
    assert poll_payload["status"] == "verified"
    assert poll_payload["credential_ready"] is True
    assert "credential" not in poll_payload
    assert "ppid" not in poll_payload

    claim = ishuman_client.post(
        "/api/ishuman/verification-status/ishuman_sess_status_001/claim",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "session_id": "ishuman_sess_status_001",
            },
            STATUS_CLAIM_ASSERTION_FIELDS,
        ),
    )
    claim_payload = claim.get_json()

    assert claim.status_code == 200
    assert claim_payload["success"] is True
    assert claim_payload["status"] == "verified"
    assert claim_payload["credential_id"] == "ishuman_master_stable_001"
    assert claim_payload["credential"]["id"] == "ishuman_master_stable_001"
    assert claim_payload["credential"]["subject"] == "did:lemma:ppid_status_001"


@pytest.mark.integration
def test_verification_status_claim_rejects_wallet_mismatch(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_status_002",
            credential_id="ishuman_master_stable_002",
            status="verified",
            ppid="did:lemma:ppid_status_002",
            wallet_id="wallet_owner",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    resp = ishuman_client.post(
        "/api/ishuman/verification-status/ishuman_sess_status_002/claim",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_other",
                "session_id": "ishuman_sess_status_002",
            },
            STATUS_CLAIM_ASSERTION_FIELDS,
            wallet_id="wallet_other",
        ),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "wallet_session_mismatch"


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

    # Phase 1.2: an unknown master hint with NO verified record for the wallet
    # now falls back and fails closed as wallet_not_verified (the old
    # master_credential_not_found 404 path was removed).
    not_verified = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "does_not_exist",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert not_verified.status_code == 403
    assert not_verified.get_json()["error"] == "wallet_not_verified"

    invalid_site = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_missing",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
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
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
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
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
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
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["cached"] is False
    assert payload["credential"]["id"] == "ishuman_site_integration_001"
    assert db.store.data["DerivedCredential"] == []
