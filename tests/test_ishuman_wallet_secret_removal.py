from __future__ import annotations

import pytest

from tests.wallet_test_helpers import SITE_SIGNING_PUBKEY_B64


@pytest.mark.unit
def test_derive_site_proof_rejects_wallet_secret(ishuman_client, attach_wallet_assertion):
    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json={
            "wallet_id": "wallet_test_001",
            "wallet_secret": "ab" * 32,
            "target_site": "example.com",
            "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
        },
    )
    assert resp.status_code == 410
    assert resp.get_json()["error"] == "wallet_secret_not_accepted"


@pytest.mark.unit
def test_start_verification_rejects_wallet_secret(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json={
            "wallet_id": "wallet_test_001",
            "wallet_secret": "ab" * 32,
            "return_url": "https://lemma.id/app",
        },
    )
    assert resp.status_code == 410
    assert resp.get_json()["error"] == "wallet_secret_not_accepted"


@pytest.mark.unit
def test_start_verification_accepts_client_ppid(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.create_identity_verification_session",
        lambda self, **kwargs: {
            "success": True,
            "session_id": "didit_sess_test_001",
            "url": "https://verify.didit.me/session/test",
        },
    )

    ppid = "did:lemma:ppid_" + ("c" * 64)
    resp = ishuman_client.post(
        "/api/ishuman/start-verification",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "return_url": "https://lemma.id/app",
                "ppid": ppid,
            },
            ["return_url"],
        ),
    )
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["session_id"]
