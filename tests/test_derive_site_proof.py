"""Phase 1.2 — master_credential_id is an optional hint in derive-site-proof.

The server must:
  * succeed without master_credential_id when the wallet has a verified IDV,
  * still honor a valid master_credential_id hint,
  * fall back to the latest verified record when the hint is stale,
  * reject an unverified wallet with wallet_not_verified.
"""

from __future__ import annotations

import pytest

from tests.wallet_test_helpers import (
    DERIVE_ASSERTION_FIELDS,
    SITE_SIGNING_PUBKEY_B64,
)

NO_MASTER_ASSERTION_FIELDS = ["target_site", "site_signing_pubkey"]


def _patch_issuance(monkeypatch):
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_phase12",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_site_phase12_001",
            "subject": ppid,
            "wallet_id": wallet_id,
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "issuer": "did:lemma:test",
        },
    )


@pytest.mark.unit
def test_derive_without_master_id_succeeds_for_verified_wallet(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import DerivedCredential

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_verified_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            NO_MASTER_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert payload["credential"]["id"] == "ishuman_site_phase12_001"
    # The derived mapping is recorded against the RESOLVED master id.
    derived = db.store.data[DerivedCredential.__name__][0]
    assert derived.master_credential_id == "ishuman_master_verified_001"


@pytest.mark.unit
def test_derive_with_valid_master_hint_still_works(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_hint_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_hint_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert payload["credential"]["id"] == "ishuman_site_phase12_001"


@pytest.mark.unit
def test_derive_with_stale_master_hint_falls_back_to_latest_verified(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import DerivedCredential

    db = fake_ishuman_db_session_factory
    # Only a fresh verified record exists; the hint references an old id.
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_current_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_STALE_999",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    derived = db.store.data[DerivedCredential.__name__][0]
    assert derived.master_credential_id == "ishuman_master_current_001"


@pytest.mark.unit
def test_derive_for_unverified_wallet_returns_wallet_not_verified(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory  # no verified rows seeded
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            NO_MASTER_ASSERTION_FIELDS,
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 403, payload
    assert payload["error"] == "wallet_not_verified"
