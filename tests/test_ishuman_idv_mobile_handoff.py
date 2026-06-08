"""Silent mobile wallet handoff during Didit IDV return."""

from __future__ import annotations

import pytest

HANDOFF_ID = "handoff_" + "b" * 24
SESSION_ID = "ishuman_sess_test_handoff_001"
ENCRYPTED_BLOB = "AQID_encrypted_opaque_blob"


@pytest.mark.integration
def test_deposit_then_claim_round_trips_handoff(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    deposit_body = attach_wallet_assertion(
        {
            "wallet_id": "wallet_handoff_001",
            "wallet_secret": "ab" * 32,
            "handoff_id": HANDOFF_ID,
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
        },
        ["handoff_id", "session_id"],
    )
    deposit = ishuman_client.post("/api/ishuman/idv-mobile-handoff/deposit", json=deposit_body)
    assert deposit.status_code == 200, deposit.get_json()
    assert deposit.get_json()["expires_in"] == 900

    claim = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"handoff_id": HANDOFF_ID},
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["wallet_id"] == "wallet_handoff_001"
    assert payload["session_id"] == SESSION_ID
    assert payload["encrypted_blob"] == ENCRYPTED_BLOB

    again = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"handoff_id": HANDOFF_ID},
    )
    assert again.status_code == 404
    assert again.get_json()["error"] == "handoff_not_found"


@pytest.mark.integration
def test_deposit_requires_wallet_assertion(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/deposit",
        json={
            "wallet_id": "wallet_handoff_002",
            "handoff_id": HANDOFF_ID,
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 403, payload
    assert payload["error"].startswith("wallet_assertion")


@pytest.mark.integration
def test_deposit_missing_fields_returns_400(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/deposit",
        json={"wallet_id": "wallet_handoff_003"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_handoff_fields"


@pytest.mark.integration
def test_claim_unknown_handoff_returns_404(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"handoff_id": "handoff_" + "z" * 24},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "handoff_not_found"


@pytest.mark.integration
def test_claim_by_session_id_when_handoff_id_unknown(ishuman_client):
    from auth.redis_store import store as redis_store

    redis_store(
        "ishuman:idv-handoff-session:ishuman_sess_test_handoff_002",
        {
            "handoff_id": HANDOFF_ID,
            "wallet_id": "wallet_handoff_session_001",
            "session_id": "ishuman_sess_test_handoff_002",
            "encrypted_blob": ENCRYPTED_BLOB,
        },
        ttl_seconds=900,
    )

    claim = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"session_id": "ishuman_sess_test_handoff_002"},
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["wallet_id"] == "wallet_handoff_session_001"
    assert payload["session_id"] == "ishuman_sess_test_handoff_002"


@pytest.mark.integration
def test_start_verification_stores_mobile_handoff(
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
            "session_id": "didit_sess_handoff",
            "url": "https://verification.didit.me/session/handoff",
        },
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_handoff_start",
    )

    return_url = "https://lemma.id/wallet/ishuman-idv?verification_return=true&handoff_id=" + HANDOFF_ID
    body = attach_wallet_assertion(
        {
            "wallet_id": "wallet_handoff_start_001",
            "wallet_secret": "ab" * 32,
            "return_url": return_url,
            "provider": "didit",
            "handoff_id": HANDOFF_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
        },
        ["return_url", "handoff_id"],
    )
    resp = ishuman_client.post("/api/ishuman/start-verification", json=body)
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["handoff_stored"] is True

    claim = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"handoff_id": HANDOFF_ID},
    )
    claim_payload = claim.get_json()
    assert claim.status_code == 200, claim_payload
    assert claim_payload["session_id"] == payload["session_id"]
    assert claim_payload["encrypted_blob"] == ENCRYPTED_BLOB

    rows = db.store.data[IsHumanVerification.__name__]
    assert len(rows) == 1
    assert rows[0].session_id == payload["session_id"]


@pytest.mark.integration
def test_deposit_weak_handoff_id_rejected(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    deposit_body = attach_wallet_assertion(
        {
            "wallet_id": "wallet_handoff_004",
            "wallet_secret": "ab" * 32,
            "handoff_id": "short",
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
        },
        ["handoff_id", "session_id"],
    )
    resp = ishuman_client.post("/api/ishuman/idv-mobile-handoff/deposit", json=deposit_body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "weak_handoff_id"
