"""Pull-based device link relay, POST /api/wallet/link-receive."""

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
    assert payload["enrollment_grant"].startswith("weg_")

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


@pytest.mark.integration
def test_link_push_early_claim_does_not_expire_offer(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    """Regression: receiver claim polling must not delete a push offer."""
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    offer_id = "linkpush_" + "e" * 24
    offer_body = attach_wallet_assertion(
        {
            "action": "offer",
            "wallet_id": "wallet_push_early",
            "transfer_id": offer_id,
            "confirm_code": "135790",
        },
        ["transfer_id", "confirm_code"],
    )
    assert ishuman_client.post("/api/wallet/link-receive", json=offer_body).status_code == 200
    assert ishuman_client.post(
        "/api/wallet/link-receive",
        json={
            "action": "register",
            "transfer_id": offer_id,
            "recv_pubkey": RECV_PUB,
        },
    ).status_code == 200

    for _ in range(3):
        early = ishuman_client.post(
            "/api/wallet/link-receive",
            json={"action": "claim", "transfer_id": offer_id},
        )
        assert early.status_code == 404

    status = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "status", "transfer_id": offer_id},
    )
    body = status.get_json()
    assert status.status_code == 200, body
    assert body["status"] == "registered"
    assert body["recv_pubkey"] == RECV_PUB
    assert body["confirm_code"] == "135790"
    assert body["has_bundle"] is False


PUSH_ID = "linkpush_" + "c" * 24
CONFIRM = "482913"


@pytest.mark.integration
def test_link_push_offer_register_deposit_claim(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    offer_body = attach_wallet_assertion(
        {
            "action": "offer",
            "wallet_id": "wallet_push_001",
            "transfer_id": PUSH_ID,
            "confirm_code": CONFIRM,
        },
        ["transfer_id", "confirm_code"],
    )
    offer = ishuman_client.post("/api/wallet/link-receive", json=offer_body)
    assert offer.status_code == 200, offer.get_json()

    status = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "status", "transfer_id": PUSH_ID},
    )
    assert status.status_code == 200
    assert status.get_json()["status"] == "waiting"
    assert status.get_json()["confirm_code"] == CONFIRM

    reg = ishuman_client.post(
        "/api/wallet/link-receive",
        json={
            "action": "register",
            "transfer_id": PUSH_ID,
            "recv_pubkey": RECV_PUB,
        },
    )
    assert reg.status_code == 200, reg.get_json()
    assert reg.get_json()["confirm_code"] == CONFIRM

    race = ishuman_client.post(
        "/api/wallet/link-receive",
        json={
            "action": "register",
            "transfer_id": PUSH_ID,
            "recv_pubkey": "dd" * 32,
        },
    )
    assert race.status_code == 409

    early_claim = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "claim", "transfer_id": PUSH_ID},
    )
    assert early_claim.status_code == 404

    # Early claim polls must not destroy the registered offer (sender status
    # would otherwise 404 and the UI would report "expired" mid-transfer).
    status_after_early = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "status", "transfer_id": PUSH_ID},
    )
    assert status_after_early.status_code == 200, status_after_early.get_json()
    assert status_after_early.get_json()["status"] == "registered"
    assert status_after_early.get_json()["recv_pubkey"] == RECV_PUB
    assert status_after_early.get_json()["confirm_code"] == CONFIRM

    deposit_body = attach_wallet_assertion(
        {
            "action": "deposit",
            "wallet_id": "wallet_push_001",
            "transfer_id": PUSH_ID,
            "recv_pubkey": RECV_PUB,
            "bundle": {
                "sealed_wallet_seed": "c2VlZA==",
                "sealed_person_root_proxy": "cHJveHk=",
            },
        },
        ["transfer_id", "recv_pubkey"],
    )
    deposit = ishuman_client.post("/api/wallet/link-receive", json=deposit_body)
    assert deposit.status_code == 200, deposit.get_json()

    claim = ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "claim", "transfer_id": PUSH_ID},
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["wallet_id"] == "wallet_push_001"
    assert payload["bundle"]["sealed_wallet_seed"] == "c2VlZA=="
    assert payload["enrollment_grant"].startswith("weg_")


@pytest.mark.integration
def test_link_push_deposit_rejects_pubkey_mismatch(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    push_id = "linkpush_" + "d" * 24

    offer_body = attach_wallet_assertion(
        {
            "action": "offer",
            "wallet_id": "wallet_push_002",
            "transfer_id": push_id,
            "confirm_code": "100001",
        },
        ["transfer_id", "confirm_code"],
    )
    assert ishuman_client.post("/api/wallet/link-receive", json=offer_body).status_code == 200
    assert ishuman_client.post(
        "/api/wallet/link-receive",
        json={"action": "register", "transfer_id": push_id, "recv_pubkey": RECV_PUB},
    ).status_code == 200

    deposit_body = attach_wallet_assertion(
        {
            "action": "deposit",
            "wallet_id": "wallet_push_002",
            "transfer_id": push_id,
            "recv_pubkey": "ee" * 32,
            "bundle": {
                "sealed_wallet_seed": "c2VlZA==",
                "sealed_person_root_proxy": "cHJveHk=",
            },
        },
        ["transfer_id", "recv_pubkey"],
    )
    deposit = ishuman_client.post("/api/wallet/link-receive", json=deposit_body)
    assert deposit.status_code == 409
    assert deposit.get_json()["error"] == "pubkey_mismatch"
