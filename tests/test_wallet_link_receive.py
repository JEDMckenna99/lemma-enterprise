"""Pull-based device link relay — POST /api/wallet/link-receive."""

from __future__ import annotations

import pytest

TRANSFER_ID = "linkrecv_" + "b" * 24
RECV_PUB = "bc" * 32
SEALED = "AQ_sealed_link_payload_placeholder"


@pytest.mark.integration
def test_link_receive_deposit_then_claim(
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
            "wallet_id": "wallet_pull_001",
            "transfer_id": TRANSFER_ID,
            "recv_pubkey": RECV_PUB,
            "bundle": {"sealed_link_payload": SEALED},
        },
        ["transfer_id", "recv_pubkey"],
    )
    deposit = ishuman_client.post("/api/wallet/link-receive", json=deposit_body)
    assert deposit.status_code == 200, deposit.get_json()
    assert deposit.get_json()["expires_in"] == 300

    claim = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "claim", "transfer_id": TRANSFER_ID},
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["wallet_id"] == "wallet_pull_001"
    assert payload["bundle"]["sealed_link_payload"] == SEALED

    again = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "claim", "transfer_id": TRANSFER_ID},
    )
    assert again.status_code == 404


@pytest.mark.integration
def test_link_receive_deposit_requires_wallet_assertion(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    resp = ishuman_client.post(
        "/api/wallet/link-receive",
        json={
            "action": "deposit",
            "wallet_id": "wallet_pull_002",
            "transfer_id": TRANSFER_ID,
            "recv_pubkey": RECV_PUB,
            "bundle": {"sealed_link_payload": SEALED},
        },
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_link_receive_claim_before_deposit_404(ishuman_client):
    resp = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "claim", "transfer_id": "linkrecv_" + "z" * 24},
    )
    assert resp.status_code == 404
