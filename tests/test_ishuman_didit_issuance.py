"""Integration tests for the didit IDV rail (Phase 3.2).

Mirrors test_ishuman_issuance_integration.py for the didit provider:
  * start-verification routes to didit and persists issuer_id/provider_session_id
  * the didit webhook issues a Lemma-signed master credential on Approved
  * an ongoing didit risk event (BLOCKED) triggers a network revocation

All didit network/crypto boundaries are monkeypatched; these tests exercise the
Lemma-side routing, persistence, and dispatch logic.
"""

from __future__ import annotations

import pytest

from tests.conftest import START_ASSERTION_FIELDS
from tests.test_didit_root_material import PROOF_OF_HUMANITY_WORKFLOW_ID, _approved_poh_decision


@pytest.mark.integration
def test_start_verification_routes_to_didit(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification

    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.create_identity_verification_session",
        lambda self, user_id, return_url: {
            "success": True,
            "session_id": "didit_sess_abc",
            "url": "https://verification.didit.me/session/abc",
        },
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_didit_start",
    )

    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "return_url": "https://customer.example/return",
                "provider": "didit",
            },
            START_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert payload["provider"] == "didit"
    assert payload["provider_session_id"] == "didit_sess_abc"
    assert payload["url"] == "https://verification.didit.me/session/abc"
    # didit has no Stripe client_secret in the response.
    assert "client_secret" not in payload

    rows = db.store.data[IsHumanVerification.__name__]
    assert len(rows) == 1
    assert rows[0].issuer_id == "didit"
    assert rows[0].provider_session_id == "didit_sess_abc"
    assert rows[0].provider_session_id_hash is None
    assert rows[0].stripe_session_id is None
    assert rows[0].status == "pending"


@pytest.mark.integration
def test_start_verification_rejects_stripe_identity_provider(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)

    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "return_url": "https://customer.example/return",
                "provider": "stripe_identity",
            },
            START_ASSERTION_FIELDS,
        ),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unsupported_provider"


@pytest.mark.integration
def test_start_verification_didit_disabled_fails_closed(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: False)

    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "return_url": "https://customer.example/return",
                "provider": "didit",
            },
            START_ASSERTION_FIELDS,
        ),
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "didit_not_enabled"


@pytest.mark.integration
def test_didit_webhook_verified_issues_master(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    from api.database import IsHumanVerification
    from api.privacy_hashes import reset_provider_hash_key_cache

    db = fake_ishuman_db_session_factory
    monkeypatch.setenv("LEMMA_PROVIDER_ID_HASH_KEY", "p" * 40)
    reset_provider_hash_key_cache()
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_didit_2",
            stripe_session_id=None,
            provider_session_id="didit_sess_002",
            issuer_id="didit",
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
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "api.config.get_didit_workflow_id",
        lambda: PROOF_OF_HUMANITY_WORKFLOW_ID,
    )
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.verify_webhook",
        lambda self, raw, **kw: {
            "webhook_type": "status.updated",
            "status": "Approved",
            "session_id": "didit_sess_002",
            "workflow_id": PROOF_OF_HUMANITY_WORKFLOW_ID,
            "decision": _approved_poh_decision(),
        },
    )

    def _fake_complete(db, record, *, wallet_id, decision, workflow_id=None):
        record.lemma_person_id = "person_didit_1"
        record.document_root_hash = "d" * 64
        record.ppid = "did:lemma:ppid_didit_master"
        return {
            "id": "ishuman_master_didit_001",
            "issuerInfo": {"did": "did:lemma:issuer:test"},
            "claims": {"isHuman": True, "siteId": "lemma.id"},
            "subject": record.ppid,
        }

    monkeypatch.setattr("api.ishuman._complete_verified_ishuman_from_didit", _fake_complete)

    purged = {}

    def _fake_purge(self, session_id, *, vendor_data=None):
        purged["session_id"] = session_id
        purged["vendor_data"] = vendor_data
        return {"success": True, "status_code": 204}

    monkeypatch.setattr("billing.didit_manager.DiditManager.purge_verification_data", _fake_purge)

    resp = ishuman_client.post(
        "/api/webhooks/didit-identity",
        data=b"{}",
        headers={"X-Signature-V2": "sig", "X-Timestamp": "1"},
    )
    assert resp.status_code == 200

    row = db.store.data[IsHumanVerification.__name__][0]
    assert row.status == "verified"
    assert row.credential_id == "ishuman_master_didit_001"
    assert row.lemma_person_id == "person_didit_1"
    assert row.ppid == "did:lemma:ppid_didit_master"
    assert row.verified_at is not None
    assert row.metadata_json["credential_issuer_did"] == "did:lemma:issuer:test"
    # process-and-purge: the upstream didit session is deleted after issuance.
    assert purged["session_id"] == "didit_sess_002"
    assert row.provider_session_id is None
    assert row.provider_session_id_hash
    assert row.provider_session_id_hash.startswith("ph1:")
    assert row.metadata_json["didit_purged_at"]
    assert "decision" not in row.metadata_json
    assert "document_number" not in row.metadata_json


@pytest.mark.integration
def test_didit_webhook_terminal_failure_purges_session(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    from api.database import IsHumanVerification
    from api.privacy_hashes import reset_provider_hash_key_cache

    db = fake_ishuman_db_session_factory
    monkeypatch.setenv("LEMMA_PROVIDER_ID_HASH_KEY", "p" * 40)
    reset_provider_hash_key_cache()
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_didit_fail",
            stripe_session_id=None,
            provider_session_id="didit_sess_fail",
            issuer_id="didit",
            wallet_id="wallet_test_001",
            status="pending",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.verify_webhook",
        lambda self, raw, **kw: {
            "webhook_type": "status.updated",
            "status": "Abandoned",
            "session_id": "didit_sess_fail",
        },
    )

    purged = {}

    def _fake_purge(self, session_id, *, vendor_data=None):
        purged["session_id"] = session_id
        purged["vendor_data"] = vendor_data
        return {"success": True, "status_code": 204}

    monkeypatch.setattr("billing.didit_manager.DiditManager.purge_verification_data", _fake_purge)

    resp = ishuman_client.post(
        "/api/webhooks/didit-identity",
        data=b"{}",
        headers={"X-Signature-V2": "sig", "X-Timestamp": "1"},
    )
    assert resp.status_code == 200

    row = db.store.data[IsHumanVerification.__name__][0]
    assert row.status == "abandoned"
    assert purged["session_id"] == "didit_sess_fail"
    assert row.provider_session_id is None
    assert row.provider_session_id_hash
    assert row.provider_session_id_hash.startswith("ph1:")
    assert row.metadata_json["didit_purged_at"]


@pytest.mark.integration
def test_didit_webhook_invalid_signature_rejected(
    ishuman_client, monkeypatch,
):
    from billing.didit_manager import DiditWebhookError

    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)

    def _raise(self, raw, **kw):
        raise DiditWebhookError("signature mismatch")

    monkeypatch.setattr("billing.didit_manager.DiditManager.verify_webhook", _raise)

    resp = ishuman_client.post(
        "/api/webhooks/didit-identity",
        data=b"{}",
        headers={"X-Signature-V2": "bad", "X-Timestamp": "1"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_signature"


@pytest.mark.integration
def test_didit_webhook_disabled_returns_404(ishuman_client, monkeypatch):
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: False)
    resp = ishuman_client.post(
        "/api/webhooks/didit-identity",
        data=b"{}",
        headers={"X-Signature-V2": "sig", "X-Timestamp": "1"},
    )
    assert resp.status_code == 404


@pytest.mark.integration
def test_didit_risk_event_blocked_triggers_revocation(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            session_id="ishuman_sess_didit_risk",
            provider_session_id="didit_sess_risk",
            issuer_id="didit",
            wallet_id="wallet_blocked_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.verify_webhook",
        lambda self, raw, **kw: {
            "webhook_type": "user.status.updated",
            "status": "BLOCKED",
            "session_id": "didit_sess_risk",
            "vendor_data": "wallet_blocked_001",
        },
    )

    captured = {}

    def _fake_revoke(db, *, wallet_id=None, master_credential_id=None, reason="", revoked_by="admin"):
        captured["wallet_id"] = wallet_id
        captured["reason"] = reason
        captured["revoked_by"] = revoked_by
        return {"wallet_id": wallet_id, "revoked_credential_ids": ["c1"], "master_count": 1, "derived_count": 0}

    monkeypatch.setattr("api.ishuman.revoke_wallet_network_wide", _fake_revoke)

    resp = ishuman_client.post(
        "/api/webhooks/didit-identity",
        data=b"{}",
        headers={"X-Signature-V2": "sig", "X-Timestamp": "1"},
    )
    assert resp.status_code == 200
    assert captured["wallet_id"] == "wallet_blocked_001"
    assert captured["revoked_by"] == "didit_risk_feed"
    assert "didit_risk" in captured["reason"]
