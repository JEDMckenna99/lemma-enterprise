"""Phase 5.1, pinned cryptographic invariants.

These tests byte-pin the canonical formats and derivations the whole network
depends on. They are the FIRST tests that should break if anyone introduces a
canonicalization-changing refactor. Each pinned value was produced by running
the live code once with fixed, test-controlled inputs.

If one of these fails, do not "fix" the expected value blindly, a changed
canonical message breaks every already-issued credential and every third-party
verifier (Go/Rust/Python). Treat a diff here as a protocol-breaking change.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Test-controlled secrets so the pins are independent of deploy env values.
FIXED_PEPPER = b"invariant_test_pepper_0123456789"  # 32 bytes
FIXED_ROOT_PPID_KEY = b"invariant_root_ppid_key_01234567"  # 32 bytes


@pytest.mark.unit
def test_ppid_derivation_is_deterministic_and_byte_pinned():
    """Same (person_root, site) -> same PPID, byte-exact."""
    from api.ppid import derive_ppid_from_person_root, derive_ppid_from_person_root_hash

    person_root = bytes.fromhex("aa" * 32)
    site = "example.com"

    ppid_a = derive_ppid_from_person_root(person_root, site)
    ppid_b = derive_ppid_from_person_root(person_root, site)
    assert ppid_a == ppid_b  # deterministic

    expected = "did:lemma:ppid_9d361fce9d528a34ccc86f1f83882743068855fe517f7cbe0c995ecdbfeed20c"
    assert ppid_a == expected

    # The hex-hash entry point must agree with the bytes entry point.
    assert derive_ppid_from_person_root_hash("aa" * 32, site) == expected

    # Different site -> different PPID (pairwise unlinkability).
    assert derive_ppid_from_person_root(person_root, "other.example") != expected


@pytest.mark.unit
def test_document_root_canonicalization_is_stable(monkeypatch):
    """Same document fields -> same document_root_hash, byte-exact."""
    import api.identity_roots as ir
    from api.identity_roots import (
        StripeIdentityRootMaterial,
        build_document_root_claims,
        derive_document_root_hash,
    )

    monkeypatch.setattr(ir, "_get_identity_root_pepper", lambda *a, **k: FIXED_PEPPER)

    material = StripeIdentityRootMaterial(
        country="US",
        document_type="driving_license",
        document_number="D1234567",
        date_of_birth="1985-03-12",
        issuing_subdivision="CA",
    )
    claims = build_document_root_claims(material)

    # Canonical claim set must remain stable (key order is canonicalized later).
    assert claims == {
        "schema": "lemma.identity.document-root.v2",
        "provider": "stripe_identity",
        "country": "US",
        "document_type": "driving_license",
        "document_number": "D1234567",
        "date_of_birth": "1985-03-12",
        "issuing_subdivision": "CA",
    }

    digest = derive_document_root_hash(claims)
    assert digest == "f95534fe22f9972bda81fbcda454ae5b45013d52680428beafedc87a4d7ecbbc"
    # Determinism across calls.
    assert derive_document_root_hash(build_document_root_claims(material)) == digest


@pytest.mark.unit
def test_didit_document_root_canonicalization_is_stable(monkeypatch):
    """Didit decision -> document_root_hash, byte-exact (Phase 3.2 Option A).

    provider='didit' yields a DISTINCT document_root from the same physical
    document under Stripe, which is the intended provider-namespaced isolation.
    """
    import api.identity_roots as ir
    from api.identity_roots import (
        build_document_root_claims,
        derive_document_root_hash,
        extract_root_material_from_didit_decision,
    )

    monkeypatch.setattr(ir, "_get_identity_root_pepper", lambda *a, **k: FIXED_PEPPER)

    decision = {
        "id_verifications": [
            {
                "node_id": "id_verification_1",
                "status": "Approved",
                "document_type": "Identity Card",
                "document_number": "SAMPLE-DOC-12345",
                "first_name": "Jane",
                "last_name": "Doe",
                "date_of_birth": "1990-01-01",
                "issuing_state": "ESP",
            }
        ],
        "liveness_checks": [{"node_id": "liveness_1", "status": "Approved"}],
        "face_matches": [{"node_id": "face_match_1", "status": "Approved"}],
    }
    material = extract_root_material_from_didit_decision(decision)
    claims = build_document_root_claims(material, provider="didit")

    assert claims == {
        "schema": "lemma.identity.document-root.v2",
        "provider": "didit",
        "country": "ES",
        "document_type": "id_card",
        "document_number": "SAMPLEDOC12345",
        "date_of_birth": "1990-01-01",
    }

    digest = derive_document_root_hash(claims)
    assert digest == "300fead7cfa36c096d79154c88c5534cb9652cf23123bbea3da21c35d1956a5d"

    # provider isolation: same document under stripe -> different root.
    stripe_claims = build_document_root_claims(material, provider="stripe_identity")
    assert derive_document_root_hash(stripe_claims) != digest


@pytest.mark.unit
def test_browser_canonical_message_byte_pin():
    """Python _browser_canonical_message must match the JS canonicalMessage()."""
    from api.ishuman import _browser_canonical_message

    credential = {
        "issuer": "did:lemma:issuer:test",
        "subject": "did:lemma:ppid_abc",
        "claims": {"isHuman": True, "siteId": "example.com", "expiresAt": "4102444800"},
    }

    expected = (
        b'{"issuer":"did:lemma:issuer:test","subject":"did:lemma:ppid_abc",'
        b'"claims":{"expiresAt":"4102444800","isHuman":"true","siteId":"example.com"}}'
    )
    assert _browser_canonical_message(credential) == expected


@pytest.mark.unit
def test_session_presentation_payload_format():
    """The newline-joined session presentation payload must remain stable."""
    # Load the reference Python verifier package (its directory name has hyphens,
    # so it must be loaded by path; register in sys.modules so its @dataclass
    # decorators can resolve their own module).
    pkg_path = REPO_ROOT / "packages" / "ishuman-verify-py" / "lemma_ishuman_verify.py"
    spec = importlib.util.spec_from_file_location("lemma_ishuman_verify_pin", pkg_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lemma_ishuman_verify_pin"] = mod
    spec.loader.exec_module(mod)

    assertion = {
        "session_id": "sess_1",
        "site_id": "example.com",
        "credential_id": "ishuman_site_1",
        "subject": "did:lemma:ppid_abc",
        "session_nonce": "nonce_1",
        "bloom_sequence": 7,
        "issued_at_unix": 1700000000,
        "expires_at_unix": 1700086400,
    }

    expected = (
        b"lemma:site-session-presentation:v1\n"
        b"sess_1\nexample.com\nishuman_site_1\ndid:lemma:ppid_abc\n"
        b"nonce_1\n7\n1700000000\n1700086400"
    )
    assert mod._build_session_message(assertion) == expected
    assert mod.SESSION_PRESENTATION_PREFIX == "lemma:site-session-presentation:v1"


@pytest.mark.unit
def test_wallet_master_secret_derivation(monkeypatch):
    """HMAC(root_key, wallet_secret) yields a stable master secret."""
    import api.ppid as ppidmod

    monkeypatch.setattr(ppidmod, "_get_root_ppid_key", lambda *a, **k: FIXED_ROOT_PPID_KEY)

    master = ppidmod.derive_master_secret_from_wallet_secret("ab" * 32)
    assert master.hex() == "c060ff2951a71f8ba8094bdef0329e2bc83e9445ff5a0bcd9b486148c3fce24d"
    # Deterministic.
    assert ppidmod.derive_master_secret_from_wallet_secret("ab" * 32) == master
