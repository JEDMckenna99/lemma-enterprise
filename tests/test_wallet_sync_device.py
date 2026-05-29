"""Phase 4.2 — POST /api/wallet/sync-device QR transfer relay.

The server is a short-lived, one-time relay for an opaque bundle the old device
reseals to the new device's transient key. The server never sees plaintext
seeds. Deposits require a wallet_assertion bound to ``transfer_id`` +
``new_device_enc_pubkey``; claims are single-use.
"""

from __future__ import annotations

import pytest


TRANSFER_ID = "transfer_" + "a" * 24
NEW_DEVICE_PUB = "bc" * 32  # base64url-ish placeholder; server treats it opaquely
BUNDLE = {
    "sealed_wallet_seed": "AQ_resealed_seed",
    "sealed_person_root_proxy": "AQ_resealed_proxy",
    "master_credential_id": "ishuman_master_xfer_001",
}


@pytest.mark.integration
def test_deposit_then_claim_round_trips_bundle(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    deposit_body = attach_wallet_assertion(
        {
            "action": "deposit",
            "wallet_id": "wallet_xfer_001",
            "wallet_secret": "ab" * 32,
            "transfer_id": TRANSFER_ID,
            "new_device_enc_pubkey": NEW_DEVICE_PUB,
            "bundle": BUNDLE,
        },
        ["transfer_id", "new_device_enc_pubkey"],
    )
    deposit = ishuman_client.post("/api/wallet/sync-device", json=deposit_body)
    assert deposit.status_code == 200, deposit.get_json()
    assert deposit.get_json()["expires_in"] == 60

    claim = ishuman_client.post(
        "/api/wallet/sync-device", json={"action": "claim", "transfer_id": TRANSFER_ID}
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["wallet_id"] == "wallet_xfer_001"
    assert payload["bundle"] == BUNDLE

    # One-time: a second claim must fail.
    again = ishuman_client.post(
        "/api/wallet/sync-device", json={"action": "claim", "transfer_id": TRANSFER_ID}
    )
    assert again.status_code == 404
    assert again.get_json()["error"] == "transfer_not_found"


@pytest.mark.integration
def test_deposit_requires_wallet_assertion(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    resp = ishuman_client.post(
        "/api/wallet/sync-device",
        json={
            "action": "deposit",
            "wallet_id": "wallet_xfer_002",
            "transfer_id": TRANSFER_ID,
            "new_device_enc_pubkey": NEW_DEVICE_PUB,
            "bundle": BUNDLE,
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 403, payload
    assert payload["error"].startswith("wallet_assertion")


@pytest.mark.integration
def test_deposit_assertion_must_bind_new_device_key(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    """A signature over the original key must not authorize a swapped key."""
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    body = attach_wallet_assertion(
        {
            "action": "deposit",
            "wallet_id": "wallet_xfer_003",
            "wallet_secret": "ab" * 32,
            "transfer_id": TRANSFER_ID,
            "new_device_enc_pubkey": NEW_DEVICE_PUB,
            "bundle": BUNDLE,
        },
        ["transfer_id", "new_device_enc_pubkey"],
    )
    # Attacker swaps the target key after the wallet signed.
    body["new_device_enc_pubkey"] = "ff" * 32
    resp = ishuman_client.post("/api/wallet/sync-device", json=body)
    payload = resp.get_json()
    assert resp.status_code == 403, payload
    # Signature was computed over the original key, so it no longer verifies.
    assert "signature" in payload["error"].lower()


@pytest.mark.integration
def test_claim_unknown_transfer_returns_404(ishuman_client):
    resp = ishuman_client.post(
        "/api/wallet/sync-device", json={"action": "claim", "transfer_id": "nope_" + "z" * 20}
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "transfer_not_found"


@pytest.mark.integration
def test_deposit_missing_fields_returns_400(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    resp = ishuman_client.post(
        "/api/wallet/sync-device", json={"action": "deposit", "wallet_id": "w"}
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_transfer_fields"


@pytest.mark.integration
def test_unknown_action_returns_400(ishuman_client):
    resp = ishuman_client.post("/api/wallet/sync-device", json={"action": "frobnicate"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unknown_action"
