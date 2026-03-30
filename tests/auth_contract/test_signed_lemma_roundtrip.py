"""
Signed lemma contract tests.

These tests protect against code drift between issuance/header-serialization and
server verification expectations by enforcing a golden signed payload shape.
"""

import json
import os
import sys
import time
import types

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(name="golden_credential_data")
def fixture_golden_credential():
    now = int(time.time())
    return {
        "id": "cred_contract_1",
        "issuer": "did:lemma:testissuer",
        "subject": "did:lemma:ppid_" + ("a" * 64),
        "type": ["VerifiableCredential", "PermissionLemma"],
        "issuanceDate": now,
        "claims": {
            "permissionId": "admin_access",
            "scope": ["admin", "read", "write"],
            "siteId": "lemma.id",
            "issuedAt": now,
            "expiresAt": now + 3600,
        },
        "proof": {
            "type": "Ed25519Signature2020",
            "signatureValue": "deadbeefcafebabe",
        },
    }


def _install_fake_verifier(monkeypatch):
    class _FakeVerifier:
        def verify_credential_json(self, credential_json):
            payload = json.loads(credential_json)

            # Contract expectations:
            # - no synthetic legacy top-level "signature" field
            # - numeric issuanceDate
            # - proof.signatureValue present
            if "signature" in payload:
                return False
            if not isinstance(payload.get("issuanceDate"), int):
                return False

            proof = payload.get("proof") or {}
            if not isinstance(proof.get("signatureValue"), str) or not proof.get("signatureValue"):
                return False

            return True

    fake_mod = types.SimpleNamespace(PyOptimizedVerifier=_FakeVerifier)
    monkeypatch.setitem(sys.modules, "lemma_crypto", fake_mod)


def test_golden_credential_shape_verifies(monkeypatch, golden_credential_data):
    from api import trusted_issuers

    _install_fake_verifier(monkeypatch)
    monkeypatch.setattr(trusted_issuers, "is_trusted_issuer", lambda _did: True)

    result = trusted_issuers.verify_credential_with_trust(golden_credential_data)
    assert result["valid"] is True
    assert result["signature_valid"] is True
    assert result["reason"] is None


def test_top_level_legacy_signature_field_breaks_verification(monkeypatch, golden_credential_data):
    from api import trusted_issuers

    _install_fake_verifier(monkeypatch)
    monkeypatch.setattr(trusted_issuers, "is_trusted_issuer", lambda _did: True)

    mutated = dict(golden_credential_data)
    mutated["signature"] = "legacy"

    result = trusted_issuers.verify_credential_with_trust(mutated)
    assert result["valid"] is False
    assert result["reason"] == "invalid_signature"


def test_string_issuance_date_breaks_verification(monkeypatch, golden_credential_data):
    from api import trusted_issuers

    _install_fake_verifier(monkeypatch)
    monkeypatch.setattr(trusted_issuers, "is_trusted_issuer", lambda _did: True)

    mutated = dict(golden_credential_data)
    mutated["issuanceDate"] = "2026-02-05T20:14:19.000Z"

    result = trusted_issuers.verify_credential_with_trust(mutated)
    assert result["valid"] is False
    assert result["reason"] == "invalid_signature"

