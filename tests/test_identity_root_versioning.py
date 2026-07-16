"""Phase 3.1, versioned pepper/salt rotation.

Rotation is additive: V1 resolution is byte-stable (legacy), the active version
is selectable via ``LEMMA_ACTIVE_ROOT_VERSION``, distinct versions derive
distinct roots, and a missing pepper/salt for the active version fails closed.
"""

from __future__ import annotations

import pytest

from api.identity_roots import (
    IdentityRootError,
    active_root_version,
    derive_document_root_hash,
    derive_person_root_hash,
)

CLAIMS = {
    "schema": "lemma.identity.document-root.v1",
    "provider": "stripe_identity",
    "country": "US",
    "document_type": "driving_license",
    "document_number": "D1234567",
    "date_of_birth": "1985-03-12",
}

PEPPER_A = "A" * 40
PEPPER_B = "B" * 40
SALT_A = "C" * 40
SALT_B = "D" * 40


@pytest.mark.unit
def test_active_root_version_defaults_to_v1(monkeypatch):
    monkeypatch.delenv("LEMMA_ACTIVE_ROOT_VERSION", raising=False)
    assert active_root_version() == "v1"


@pytest.mark.unit
def test_active_root_version_reads_env(monkeypatch):
    monkeypatch.setenv("LEMMA_ACTIVE_ROOT_VERSION", "V2")
    assert active_root_version() == "V2"


@pytest.mark.unit
def test_v1_resolution_is_stable_across_aliases(monkeypatch):
    # All three spellings hit the legacy V1 path -> identical bytes.
    monkeypatch.delenv("LEMMA_ACTIVE_ROOT_VERSION", raising=False)
    default = derive_document_root_hash(CLAIMS)
    explicit_lower = derive_document_root_hash(CLAIMS, "v1")
    explicit_upper = derive_document_root_hash(CLAIMS, "V1")
    assert default == explicit_lower == explicit_upper


@pytest.mark.unit
def test_distinct_versions_yield_distinct_roots(monkeypatch):
    monkeypatch.setenv("LEMMA_IDENTITY_ROOT_PEPPER_V9A", PEPPER_A)
    monkeypatch.setenv("LEMMA_IDENTITY_ROOT_PEPPER_V9B", PEPPER_B)
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SALT_V9A", SALT_A)
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SALT_V9B", SALT_B)

    doc_a = derive_document_root_hash(CLAIMS, "V9A")
    doc_b = derive_document_root_hash(CLAIMS, "V9B")
    assert doc_a != doc_b

    # Even on the same document root, distinct salts diverge the person root.
    person_a = derive_person_root_hash(doc_a, "V9A")
    person_b = derive_person_root_hash(doc_a, "V9B")
    assert person_a != person_b


@pytest.mark.unit
def test_active_version_is_used_by_default(monkeypatch):
    monkeypatch.setenv("LEMMA_IDENTITY_ROOT_PEPPER_V9A", PEPPER_A)
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SALT_V9A", SALT_A)
    monkeypatch.setenv("LEMMA_ACTIVE_ROOT_VERSION", "V9A")

    assert derive_document_root_hash(CLAIMS) == derive_document_root_hash(CLAIMS, "V9A")


@pytest.mark.unit
def test_missing_pepper_for_active_version_fails_closed(monkeypatch):
    monkeypatch.delenv("LEMMA_IDENTITY_ROOT_PEPPER_VZZ", raising=False)
    with pytest.raises(IdentityRootError):
        derive_document_root_hash(CLAIMS, "VZZ")


@pytest.mark.unit
def test_missing_salt_for_active_version_fails_closed(monkeypatch):
    monkeypatch.setenv("LEMMA_IDENTITY_ROOT_PEPPER_VYY", PEPPER_A)
    monkeypatch.delenv("LEMMA_PERSON_ROOT_SALT_VYY", raising=False)
    doc = derive_document_root_hash(CLAIMS, "VYY")
    with pytest.raises(IdentityRootError):
        derive_person_root_hash(doc, "VYY")
