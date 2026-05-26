from __future__ import annotations

import json

import pytest

from api.identity_person import material_from_test_fixture, resolve_or_create_person_from_material
from api.identity_roots import (
    IdentityRootMaterialError,
    build_document_root_claims,
    canonical_json_bytes,
    derive_document_root_hash,
    derive_ppid_from_document_root_hash,
    document_root_hash_from_material,
    format_dob_from_stripe,
)


@pytest.mark.unit
def test_canonical_json_is_deterministic():
    payload = {"schema": "lemma.identity.document-root.v1", "country": "US", "document_type": "passport"}
    a = canonical_json_bytes(payload)
    b = canonical_json_bytes({"document_type": "passport", "country": "US", "schema": "lemma.identity.document-root.v1"})
    assert a == b


@pytest.mark.unit
def test_same_material_same_document_root():
    material = material_from_test_fixture(document_number="ABC123456")
    h1 = document_root_hash_from_material(material)
    h2 = document_root_hash_from_material(material)
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.unit
def test_name_like_fields_not_in_document_root_claims():
    material = material_from_test_fixture()
    claims = build_document_root_claims(material)
    assert "first_name" not in claims
    assert "last_name" not in claims
    assert "email" not in claims


@pytest.mark.unit
def test_missing_document_number_fails_closed():
    material = material_from_test_fixture(document_number="")
    with pytest.raises(IdentityRootMaterialError):
        build_document_root_claims(material)


@pytest.mark.unit
def test_dob_format_from_stripe_dict():
    assert format_dob_from_stripe({"year": 1991, "month": 2, "day": 3}) == "1991-02-03"


@pytest.mark.unit
def test_person_root_site_ppid_stable_and_site_scoped():
    material = material_from_test_fixture(document_number="PERSONROOT001")
    doc_hash = document_root_hash_from_material(material)
    ppid_a = derive_ppid_from_document_root_hash(doc_hash, "example.com")
    ppid_b = derive_ppid_from_document_root_hash(doc_hash, "example.com")
    ppid_other = derive_ppid_from_document_root_hash(doc_hash, "other.example")
    assert ppid_a == ppid_b
    assert ppid_a != ppid_other
    assert ppid_a.startswith("did:lemma:ppid_")


@pytest.mark.unit
def test_resolve_person_creates_and_reuses(fake_ishuman_db_session_factory):
    from api.database import LemmaDocumentRoot, LemmaPerson

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="REUSE123")
    first = resolve_or_create_person_from_material(db, material=material, wallet_id="wallet_a")
    second = resolve_or_create_person_from_material(db, material=material, wallet_id="wallet_b")

    assert first.created_person is True
    assert second.created_person is False
    assert first.person_id == second.person_id
    assert len(db._store.data[LemmaPerson.__name__]) == 1
    assert len(db._store.data[LemmaDocumentRoot.__name__]) == 1


@pytest.mark.unit
def test_claims_json_roundtrip_stable_hash():
    material = material_from_test_fixture()
    claims = build_document_root_claims(material)
    h1 = derive_document_root_hash(claims)
    claims2 = json.loads(canonical_json_bytes(claims).decode("utf-8"))
    h2 = derive_document_root_hash(claims2)
    assert h1 == h2
