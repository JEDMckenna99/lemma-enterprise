"""One-PPID assurance model: provisional roots, passkey credentials, stable PPIDs."""

from __future__ import annotations

import pytest

from tests.wallet_test_helpers import SITE_SIGNING_PUBKEY_B64

NO_MASTER_ASSERTION_FIELDS = ["target_site", "site_signing_pubkey", "issue_mode"]


@pytest.mark.unit
def test_ensure_provisional_person_is_idempotent(fake_ishuman_db_session_factory, monkeypatch):
    from api.database import LemmaPerson, LemmaWalletBinding
    from api.identity_person import (
        PERSON_STATUS_PROVISIONAL,
        ensure_provisional_person_for_wallet,
    )

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)
    db = fake_ishuman_db_session_factory.session_local()

    first = ensure_provisional_person_for_wallet(db, wallet_id="wallet_prov_1")
    second = ensure_provisional_person_for_wallet(db, wallet_id="wallet_prov_1")

    assert first == second
    assert len(db._store.data[LemmaPerson.__name__]) == 1
    assert db._store.data[LemmaPerson.__name__][0].status == PERSON_STATUS_PROVISIONAL
    assert len(db._store.data[LemmaWalletBinding.__name__]) == 1


@pytest.mark.unit
def test_first_idv_promotes_provisional_without_ppid_change(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaPerson
    from api.identity_person import (
        PERSON_STATUS_ACTIVE,
        ensure_provisional_person_for_wallet,
        material_from_test_fixture,
        resolve_or_create_person_from_material,
    )
    from api.ppid import derive_ppid_from_person_root_hash

    from api.person_root_crypto import decrypt_person_root

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)
    db = fake_ishuman_db_session_factory.session_local()
    person_id = ensure_provisional_person_for_wallet(db, wallet_id="wallet_step_up")
    person = db.query(LemmaPerson).filter_by(person_id=person_id).first()
    ppid_before = derive_ppid_from_person_root_hash(
        decrypt_person_root(person.person_id, person.person_root_hash),
        "example.com",
    )

    material = material_from_test_fixture(document_number="STEPUP-001")
    resolved = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_step_up",
    )
    ppid_after = derive_ppid_from_person_root_hash(resolved.person_root_hash, "example.com")

    assert resolved.person_id == person_id
    assert ppid_before == ppid_after
    assert db.query(LemmaPerson).filter_by(person_id=person_id).first().status == PERSON_STATUS_ACTIVE


@pytest.mark.unit
def test_passkey_derive_site_proof_when_flags_enabled(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import LemmaPerson
    from api.identity_person import ensure_provisional_person_for_wallet
    from api.ppid import derive_ppid_from_person_root_hash

    monkeypatch.setenv("LEMMA_ONE_PPID_ASSURANCE_MODEL", "1")
    monkeypatch.setenv("LEMMA_PASSKEY_ASSURANCE_ENABLED", "1")
    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)

    db = fake_ishuman_db_session_factory
    session = db.session_local()
    person_id = ensure_provisional_person_for_wallet(session, wallet_id="wallet_passkey_1")
    person = session.query(LemmaPerson).filter_by(person_id=person_id).first()
    from api.person_root_crypto import decrypt_person_root

    expected_ppid = derive_ppid_from_person_root_hash(
        decrypt_person_root(person.person_id, person.person_root_hash),
        "example.com",
    )
    session.commit()
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    issued = []

    def _issue(ppid, wallet_id=None, site_id=None, **kwargs):
        issued.append((ppid, kwargs.get("assurance"), kwargs.get("ppid_derivation")))
        return {
            "id": "ishuman_site_passkey_001",
            "subject": ppid,
            "claims": {
                "assurance": kwargs.get("assurance"),
                "isHuman": kwargs.get("assurance") == "ishuman",
                "siteId": site_id,
                "ppidDerivation": kwargs.get("ppid_derivation"),
            },
        }

    monkeypatch.setattr("api.ishuman._issue_ishuman_credential", _issue)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_passkey_1",
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
                "issue_mode": "site_proof",
            },
            NO_MASTER_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert issued[0][0] == expected_ppid
    assert issued[0][1] == "passkey"
    assert issued[0][2] == "person_root_v1"


@pytest.mark.unit
def test_unverified_wallet_still_wallet_not_verified_when_passkey_disabled(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setenv("LEMMA_ONE_PPID_ASSURANCE_MODEL", "0")
    monkeypatch.setenv("LEMMA_PASSKEY_ASSURANCE_ENABLED", "0")

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            NO_MASTER_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "wallet_not_verified"
