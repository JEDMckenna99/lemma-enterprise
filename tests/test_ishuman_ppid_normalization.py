from __future__ import annotations

import pytest

from api.identity_person import material_from_test_fixture
from api.identity_roots import document_root_hash_from_material, derive_ppid_from_document_root_hash
from api.ppid import canonicalize_rp_id, derive_ppid_from_wallet_secret
from api.site_hostname import canonicalize_site_hostname, SiteHostnameError, try_canonicalize_site_hostname


# Shared vectors with static/js/lemma-keys.js canonicalizeSiteDomain
SITE_HOSTNAME_VECTORS = [
    ("EXAMPLE.COM", "example.com"),
    ("https://WWW.Example.com/login?source=test", "example.com"),
    ("example.com/path/to/route", "example.com"),
    ("example.com:8443", "example.com"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_rp_id", "expected"),
    [
        ("EXAMPLE.COM", "example.com"),
        ("https://WWW.Example.com/login?source=test", "example.com"),
        ("example.com/path/to/route", "example.com"),
        ("example.com:8443", "example.com"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_canonicalize_rp_id_cases(raw_rp_id, expected):
    assert canonicalize_rp_id(raw_rp_id) == expected


@pytest.mark.unit
@pytest.mark.parametrize(("raw_host", "expected"), SITE_HOSTNAME_VECTORS)
def test_canonicalize_site_hostname_matches_client_vectors(raw_host, expected):
    assert canonicalize_site_hostname(raw_host) == expected


@pytest.mark.unit
def test_canonicalize_site_hostname_rejects_internal_site_id():
    with pytest.raises(SiteHostnameError, match="internal_site_id_not_allowed"):
        canonicalize_site_hostname("site_abc123def456")


@pytest.mark.unit
def test_try_canonicalize_site_hostname_empty():
    canonical, err = try_canonicalize_site_hostname("")
    assert canonical is None
    assert err == "hostname_required"


@pytest.mark.unit
def test_ppid_derivation_stable_for_same_site_variants():
    wallet_secret = "ab" * 32
    site_variants = [
        "EXAMPLE.com",
        "example.com",
        "example.com/path",
        "https://example.com/login",
    ]
    ppid_values = {derive_ppid_from_wallet_secret(wallet_secret, value) for value in site_variants}
    assert len(ppid_values) == 1


@pytest.mark.unit
def test_ppid_derivation_differs_for_different_sites():
    wallet_secret = "ab" * 32
    ppid_a = derive_ppid_from_wallet_secret(wallet_secret, "example.com")
    ppid_b = derive_ppid_from_wallet_secret(wallet_secret, "another-example.com")
    assert ppid_a != ppid_b


@pytest.mark.unit
def test_person_root_ppid_stable_for_site_variants():
    material = material_from_test_fixture(document_number="SITE_VARIANT_1")
    doc_hash = document_root_hash_from_material(material)
    variants = [
        "EXAMPLE.com",
        "example.com",
        "https://www.example.com/path",
    ]
    ppids = {derive_ppid_from_document_root_hash(doc_hash, value) for value in variants}
    assert len(ppids) == 1
