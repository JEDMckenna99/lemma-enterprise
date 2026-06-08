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
