"""Tests for assigned_v1 person roots and document attach continuity."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.identity_person import material_from_test_fixture, resolve_or_create_person_from_material
from api.identity_roots import (
    PERSON_ROOT_SOURCE_ASSIGNED,
    PERSON_ROOT_SOURCE_DOCUMENT_DERIVED,
    derive_person_root_hash,
    document_root_hash_from_material,
)


@pytest.mark.unit
def test_assigned_mode_mints_random_person_root(fake_ishuman_db_session_factory, monkeypatch):
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SOURCE", "assigned_v1")
    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="ASSIGNED_001")
    doc_hash = document_root_hash_from_material(material)
    derived = derive_person_root_hash(doc_hash)

    resolved = resolve_or_create_person_from_material(db, material=material, wallet_id="wallet_new")
    assert resolved.created_person is True
    assert resolved.person_root_source == PERSON_ROOT_SOURCE_ASSIGNED
    assert resolved.person_root_hash != derived
    assert len(resolved.person_root_hash) == 64


@pytest.mark.unit
def test_legacy_mode_still_derives_from_document(fake_ishuman_db_session_factory, monkeypatch):
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SOURCE", "document_derived_v1")
    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: False)

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="LEGACY_001")
    doc_hash = document_root_hash_from_material(material)
    expected = derive_person_root_hash(doc_hash)

    resolved = resolve_or_create_person_from_material(db, material=material, wallet_id="wallet_legacy")
    assert resolved.person_root_source == PERSON_ROOT_SOURCE_DOCUMENT_DERIVED
    assert resolved.person_root_hash == expected


@pytest.mark.unit
def test_re_idv_keeps_ppid_with_document_attach(fake_ishuman_db_session_factory, monkeypatch):
    from api.database import LemmaDocumentRoot, LemmaPerson
    from api.ppid import derive_ppid_from_person_root_hash

    monkeypatch.setenv("LEMMA_PERSON_ROOT_SOURCE", "assigned_v1")
    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)

    db = fake_ishuman_db_session_factory.session_local()
    first_material = material_from_test_fixture(document_number="PASSPORT_V1")
    first = resolve_or_create_person_from_material(db, material=first_material, wallet_id="wallet_refresh")
    ppid_before = derive_ppid_from_person_root_hash(first.person_root_hash, "example.com")

    second_material = material_from_test_fixture(document_number="PASSPORT_V2_RENEWAL")
    second = resolve_or_create_person_from_material(
        db,
        material=second_material,
        wallet_id="wallet_refresh",
    )

    ppid_after = derive_ppid_from_person_root_hash(second.person_root_hash, "example.com")
    assert second.person_id == first.person_id
    assert second.person_root_hash == first.person_root_hash
    assert ppid_before == ppid_after
    assert second.document_attached is True
    assert len(db._store.data[LemmaPerson.__name__]) == 1
    assert len(db._store.data[LemmaDocumentRoot.__name__]) == 2


@pytest.mark.unit
def test_new_wallet_recovers_assigned_person_across_document_schema_change(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaDocumentRoot, LemmaPerson, LemmaWalletBinding
    from api.ppid import derive_ppid_from_person_root_hash

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v1")

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="SCHEMA-RECOVERY-001")
    first = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_schema_old",
        provider="didit",
    )
    old_ppid = derive_ppid_from_person_root_hash(first.person_root_hash, "lemma.id")

    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    recovered = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_schema_recovery",
        provider="didit",
    )

    assert recovered.person_id == first.person_id
    assert recovered.person_root_hash == first.person_root_hash
    assert recovered.created_person is False
    assert recovered.matched_legacy_document_root is True
    assert recovered.document_attached is True
    assert derive_ppid_from_person_root_hash(recovered.person_root_hash, "lemma.id") == old_ppid
    assert len(db._store.data[LemmaPerson.__name__]) == 1
    assert len(db._store.data[LemmaDocumentRoot.__name__]) == 2
    assert {
        row.wallet_id: row.lemma_person_id
        for row in db._store.data[LemmaWalletBinding.__name__]
    } == {
        "wallet_schema_old": first.person_id,
        "wallet_schema_recovery": first.person_id,
    }


@pytest.mark.unit
def test_provisional_wallet_rebinds_to_known_document_person(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaPerson, LemmaWalletBinding
    from api.identity_person import PERSON_STATUS_PROVISIONAL, ensure_provisional_person_for_wallet

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="RECOVERY-PROVISIONAL-001")
    first = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_already_anchored",
        provider="didit",
    )

    provisional_id = ensure_provisional_person_for_wallet(
        db,
        wallet_id="wallet_new_provisional",
    )
    provisional = db.query(LemmaPerson).filter_by(person_id=provisional_id).first()
    assert provisional.status == PERSON_STATUS_PROVISIONAL

    recovered = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_new_provisional",
        provider="didit",
    )

    assert recovered.person_id == first.person_id
    assert recovered.person_root_hash == first.person_root_hash
    assert recovered.created_person is False
    binding = db.query(LemmaWalletBinding).filter_by(wallet_id="wallet_new_provisional").first()
    assert binding.lemma_person_id == first.person_id


@pytest.mark.unit
def test_new_wallet_recovers_assigned_person_across_pepper_and_provider_change(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaPerson, PlatformUser
    from api.platform_owner import resolve_platform_login_ppid
    from api.ppid import derive_ppid_from_person_root_hash

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v1")
    monkeypatch.setenv("LEMMA_ACTIVE_ROOT_VERSION", "v1")

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="IAM-RECOVERY-001")
    first = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_iam_old",
        provider="stripe_identity",
    )
    platform_ppid = derive_ppid_from_person_root_hash(first.person_root_hash, "lemma.id")
    db.add(
        PlatformUser(
            user_did=platform_ppid,
            wallet_id="wallet_iam_old",
            account_type="owner",
            status="active",
        )
    )

    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    monkeypatch.setenv("LEMMA_ACTIVE_ROOT_VERSION", "V2")
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_READ_VERSIONS", "v1")
    monkeypatch.setenv("LEMMA_IDENTITY_ROOT_PEPPER_V2", "v" * 40)
    recovered = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_iam_recovery",
        provider="didit",
    )

    assert recovered.person_id == first.person_id
    assert recovered.person_root_hash == first.person_root_hash
    assert recovered.created_person is False
    assert recovered.matched_legacy_document_root is True
    assert len(db._store.data[LemmaPerson.__name__]) == 1

    login_ppid = resolve_platform_login_ppid(
        client_ppid=platform_ppid,
        wallet_id="wallet_iam_recovery",
        db=db,
    )
    assert login_ppid == platform_ppid
    account = db.query(PlatformUser).filter_by(user_did=login_ppid).first()
    assert account is not None

    from api.platform_account import upsert_platform_account

    upsert_platform_account(
        login_ppid,
        wallet_id="wallet_iam_recovery",
        replace_wallet_id=True,
        db=db,
    )
    assert account.wallet_id == "wallet_iam_recovery"


@pytest.mark.unit
def test_legacy_document_can_recover_when_v2_requires_missing_subdivision(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaDocumentRoot, LemmaPerson

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v1")
    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(
        country="US",
        document_type="driving_license",
        document_number="DL-LEGACY-001",
        issuing_subdivision=None,
    )
    first = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_dl_old",
        provider="didit",
    )

    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    recovered = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_dl_recovery",
        provider="didit",
    )

    assert recovered.person_id == first.person_id
    assert recovered.created_person is False
    assert len(db._store.data[LemmaPerson.__name__]) == 1
    assert len(db._store.data[LemmaDocumentRoot.__name__]) == 1


@pytest.mark.integration
def test_didit_issuance_reuses_existing_assigned_person_on_recovery_wallet(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.identity_roots import extract_root_material_from_didit_decision
    from api.ishuman import _complete_verified_ishuman_from_didit
    from api.ppid import derive_ppid_from_person_root_hash
    from tests.test_didit_root_material import (
        PROOF_OF_HUMANITY_WORKFLOW_ID,
        _approved_poh_decision,
    )

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v1")
    monkeypatch.setenv("LEMMA_ACTIVE_ROOT_VERSION", "v1")

    db = fake_ishuman_db_session_factory.session_local()
    decision = _approved_poh_decision()
    material = extract_root_material_from_didit_decision(decision)
    first = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_issuance_old",
        provider="stripe_identity",
    )
    expected_ppid = derive_ppid_from_person_root_hash(first.person_root_hash, "lemma.id")

    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    monkeypatch.setattr("api.ishuman._maybe_store_seed_envelopes", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id, **_kwargs: {
            "id": "ishuman_master_recovered",
            "subject": ppid,
            "wallet_id": wallet_id,
        },
    )
    record = SimpleNamespace(
        metadata_json={},
        provider_session_id="didit_recovery_session",
        lemma_person_id=None,
        document_root_hash=None,
        root_version=None,
        confidence_level=None,
        ppid=None,
        expires_at=None,
        wallet_seed_envelope=None,
        person_root_proxy_envelope=None,
        seed_version=None,
        status="pending",
    )

    credential = _complete_verified_ishuman_from_didit(
        db,
        record,
        wallet_id="wallet_issuance_recovery",
        decision=decision,
        workflow_id=PROOF_OF_HUMANITY_WORKFLOW_ID,
    )

    assert credential is not None
    assert credential["id"] == "ishuman_master_recovered"
    assert record.lemma_person_id == first.person_id
    assert record.ppid == expected_ppid
    assert credential["subject"] == expected_ppid
    assert record.root_version == "v1"
