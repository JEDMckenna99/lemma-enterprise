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
    monkeypatch.delenv("LEMMA_PERSON_ROOT_SOURCE", raising=False)
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
