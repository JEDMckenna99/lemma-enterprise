"""Same-tab mobile redirect return for site proof issuance."""

from __future__ import annotations

import pytest

REQUEST_NONCE = "nonce_test_redirect_001"
SITE_ID = "tickets-demo.lemma.id"
CREDENTIAL = {
    "id": "ishuman_site_test_001",
    "subject": "did:lemma:ppid_" + ("a" * 64),
    "issuer": "did:lemma:issuer_test",
}
SESSION_ASSERTION = {
    "session_id": "sess_test_001",
    "site_id": SITE_ID,
    "credential_id": CREDENTIAL["id"],
    "subject": CREDENTIAL["subject"],
    "session_nonce": "nonce_session_001",
    "bloom_sequence": 1,
    "issued_at_unix": 1_700_000_000,
    "expires_at_unix": 1_700_086_400,
}
SESSION_SIGNATURE = "sig_test_redirect_001"


@pytest.mark.integration
def test_site_proof_redirect_deposit_then_claim(ishuman_client):
    deposit = ishuman_client.post(
        "/api/ishuman/site-proof-redirect/deposit",
        json={
            "request_nonce": REQUEST_NONCE,
            "site_id": SITE_ID,
            "credential": CREDENTIAL,
            "session_assertion": SESSION_ASSERTION,
            "session_signature": SESSION_SIGNATURE,
            "session_nonce": "nonce_session_001",
        },
    )
    assert deposit.status_code == 200, deposit.get_json()
    assert deposit.get_json()["expires_in"] == 900

    claim = ishuman_client.post(
        "/api/ishuman/site-proof-redirect/claim",
        json={"request_nonce": REQUEST_NONCE},
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["site_id"] == SITE_ID
    assert payload["credential"]["id"] == CREDENTIAL["id"]
    assert payload["session_signature"] == SESSION_SIGNATURE

    again = ishuman_client.post(
        "/api/ishuman/site-proof-redirect/claim",
        json={"request_nonce": REQUEST_NONCE},
    )
    assert again.status_code == 404
    assert again.get_json()["error"] == "redirect_proof_not_found"
