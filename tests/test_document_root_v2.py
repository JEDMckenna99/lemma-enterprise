"""Tests for issuing subdivision normalization and document-root v2."""

from __future__ import annotations

import pytest

from api.identity_person import (
    load_latest_person_idv_attributes,
    material_from_test_fixture,
    resolve_or_create_person_from_material,
)
from api.identity_roots import (
    DOCUMENT_ROOT_SCHEMA_V2,
    build_document_root_claims,
    derive_document_root_hash,
    document_root_hash_from_material,
)
from api.issuing_subdivision import (
    extract_didit_issuing_subdivision,
    normalize_issuing_subdivision,
    subdivision_from_document_subtype,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("California", "US-CA"),
        ("CA", "US-CA"),
        ("US-CA", "US-CA"),
        ("CALIFORNIA_DRIVER_LICENSE", "US-CA"),
        ("Ontario", "CA-ON"),
        ("QUEENSLAND", "AU-QLD"),
    ],
)
def test_normalize_issuing_subdivision(raw, expected):
    country = expected.split("-", 1)[0]
    assert normalize_issuing_subdivision(country, raw) == expected


@pytest.mark.unit
def test_subdivision_from_document_subtype():
    assert subdivision_from_document_subtype("US", "CALIFORNIA_DRIVER_LICENSE_GENERIC") == "US-CA"
    assert subdivision_from_document_subtype("US", "NEW_YORK_DRIVER_LICENSE") == "US-NY"


@pytest.mark.unit
def test_v2_claims_include_subdivision_for_us_dl(monkeypatch):
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    material = material_from_test_fixture(
        country="US",
        document_type="driving_license",
        document_number="D1234567",
        issuing_subdivision="US-CA",
    )
    claims = build_document_root_claims(material, "didit")
    assert claims["schema"] == DOCUMENT_ROOT_SCHEMA_V2
    assert claims["issuing_subdivision"] == "US-CA"


@pytest.mark.unit
def test_v2_us_dl_without_subdivision_fails_closed(monkeypatch):
    from api.identity_roots import IdentityRootMaterialError

    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    material = material_from_test_fixture(
        country="US",
        document_type="driving_license",
        document_number="D1234567",
    )
    with pytest.raises(IdentityRootMaterialError, match="issuing_subdivision required"):
        build_document_root_claims(material, "didit")


@pytest.mark.unit
def test_same_doc_number_different_states_yield_distinct_roots(monkeypatch):
    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    base = dict(country="US", document_type="driving_license", date_of_birth="1990-01-01", document_number="123456")
    ca = material_from_test_fixture(**base, issuing_subdivision="US-CA")
    ny = material_from_test_fixture(**base, issuing_subdivision="US-NY")
    assert document_root_hash_from_material(ca, provider="didit") != document_root_hash_from_material(
        ny, provider="didit"
    )


@pytest.mark.unit
def test_extract_didit_subdivision_from_subtype():
    idv = {
        "document_subtype": "TEXAS_DRIVER_LICENSE_GENERIC",
        "parsed_address": {"region": "Texas", "country": "US"},
    }
    assert extract_didit_issuing_subdivision(idv, "US") == "US-TX"


@pytest.mark.unit
def test_document_root_row_persists_policy_fields(fake_ishuman_db_session_factory, monkeypatch):
    from api.column_crypto import is_encrypted, reset_key_cache

    monkeypatch.setenv("LEMMA_DOCUMENT_ROOT_SCHEMA", "v2")
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SALT_V1", "x" * 40)
    reset_key_cache()

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(
        country="US",
        document_type="passport",
        document_number="PERSIST001",
        document_expiration_date="2032-01-15",
        issuing_subdivision=None,
    )
    resolved = resolve_or_create_person_from_material(db, material=material, wallet_id="wallet_policy")
    attrs = load_latest_person_idv_attributes(db, resolved.person_id)
    assert attrs is not None
    assert attrs["document_expiration_date"] == "2032-01-15"
    assert attrs["issuing_subdivision"] is None

    from api.database import LemmaDocumentRoot

    stored = db._store.data[LemmaDocumentRoot.__name__][-1]
    assert is_encrypted(stored.date_of_birth)
    assert is_encrypted(stored.document_expiration_date)
    assert stored.issuing_subdivision is None
    assert attrs["date_of_birth"] == "1990-01-15"
    assert attrs["age_years"] is not None
    assert attrs["document_root_schema"] == DOCUMENT_ROOT_SCHEMA_V2
