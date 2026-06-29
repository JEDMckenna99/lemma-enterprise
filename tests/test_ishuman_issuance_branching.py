from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.test_didit_root_material import PROOF_OF_HUMANITY_WORKFLOW_ID, _approved_poh_decision
from tests.wallet_test_helpers import (
    DERIVE_ASSERTION_FIELDS,
    SITE_SIGNING_PUBKEY_B64,
    START_ASSERTION_FIELDS,
)


@pytest.mark.unit
def test_derive_site_proof_cache_miss_creates_new_mapping(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification

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
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
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
    assert db.store.data["DerivedCredential"] == []


@pytest.mark.unit
def test_derive_site_proof_ignores_legacy_mapping_and_rotates_credential_id(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    make_derived_credential,
    monkeypatch,
    attach_wallet_assertion,
):
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
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["cached"] is False
    assert payload["credential"]["id"] == "ephemeral_should_be_replaced"
    assert len(db.store.data["DerivedCredential"]) == 1


@pytest.mark.unit
def test_no_master_then_master_issued_then_site_derived(
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
        lambda self, user_id, return_url, callback_url=None: {
            "success": True,
            "session_id": "didit_branch_123",
            "url": "https://verify.didit.test/session",
        },
    )
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.verify_webhook",
        lambda self, raw, **kw: {
            "webhook_type": "status.updated",
            "status": "Approved",
            "session_id": "didit_branch_123",
            "workflow_id": PROOF_OF_HUMANITY_WORKFLOW_ID,
            "decision": _approved_poh_decision(),
        },
    )

    def _issue(_ppid, _wallet_id=None, site_id=None, **kwargs):
        if site_id:
            return {"id": "ishuman_site_created_123", "claims": {"isHuman": True, "siteId": site_id}}
        return {"id": "ishuman_master_created_123", "claims": {"isHuman": True, "siteId": "lemma.id"}}

    def _fake_complete(db, record, *, wallet_id, decision, workflow_id=None):
        from api.identity_person import material_from_test_fixture, resolve_or_create_person_from_material
        from api.ppid import derive_ppid_from_person_root_hash

        material = material_from_test_fixture(stripe_session_id="didit_branch_123")
        resolved = resolve_or_create_person_from_material(db, material=material, wallet_id=wallet_id)
        ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "lemma.id")
        record.lemma_person_id = resolved.person_id
        record.document_root_hash = resolved.document_root_hash
        record.ppid = ppid
        return _issue(ppid, wallet_id, ppid_derivation="person_root_v1")

    monkeypatch.setattr("api.ishuman._complete_verified_ishuman_from_didit", _fake_complete)
    monkeypatch.setattr(
        "api.site_ppid_revocation.clear_amnesty_eligible_wallet_revocations",
        lambda *args, **kwargs: {"cleared_revocation_entries": 0, "cleared_site_blocks": 0, "reactivated_derived_credentials": 0},
    )
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.purge_verification_data",
        lambda self, session_id, **kw: {"success": True, "status_code": 204},
    )

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
        "/api/webhooks/didit-identity",
        data=b"{}",
        headers={"X-Signature-V2": "sig", "X-Timestamp": "1"},
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
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    assert derive.status_code == 200
    derive_payload = derive.get_json()
    assert derive_payload["success"] is True
    assert derive_payload["cached"] is False
    assert derive_payload["credential"]["id"] == "ishuman_site_created_123"
    assert db.store.data["DerivedCredential"] == []
