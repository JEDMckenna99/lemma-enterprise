"""
Header-to-authz contract tests.

Covers the full server path:
X-Lemma-Credential header -> authz_engine extraction -> trusted verifier outcome.
"""

import base64
import json
import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _encode_header(credential: dict) -> str:
    raw = json.dumps(credential).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


@pytest.fixture
def golden_header_credential():
    return {
        "id": "cred_header_1",
        "issuer": "did:lemma:testissuer",
        "subject": "did:lemma:ppid_" + ("b" * 64),
        "type": ["VerifiableCredential", "PermissionLemma"],
        "issuanceDate": 1770322459,
        "claims": {
            "permissionId": "admin_access",
            "scope": ["admin", "read", "write"],
            "siteId": "lemma.id",
            "issuedAt": 1770322459,
            "expiresAt": 1833394459,
        },
        "proof": {"type": "Ed25519Signature2020", "signatureValue": "abc123"},
    }


def test_extract_user_lemma_principal_accepts_golden_header(monkeypatch, golden_header_credential):
    from api import authz_engine

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    headers = {"X-Lemma-Credential": _encode_header(golden_header_credential)}
    principal, error = authz_engine.extract_user_lemma_principal(headers)

    assert error is None
    assert principal is not None
    assert principal.ppid.startswith("did:lemma:ppid_")
    assert principal.permission_id == "admin_access"
    assert principal.auth_method == "lemma_header"


def test_extract_user_lemma_principal_returns_diagnostic_for_untrusted_issuer(monkeypatch, golden_header_credential):
    from api import authz_engine

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {
            "valid": False,
            "reason": "untrusted_issuer",
            "issuer": "did:lemma:legacyissuer",
        },
    )

    headers = {"X-Lemma-Credential": _encode_header(golden_header_credential)}
    principal, error = authz_engine.extract_user_lemma_principal(headers)

    assert principal is None
    assert error == "invalid_lemma:untrusted_issuer:did:lemma:legacyissuer"


def test_extract_user_lemma_principal_rejects_invalid_header_payload(monkeypatch):
    from api import authz_engine

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    headers = {"X-Lemma-Credential": "not-base64-json"}
    principal, error = authz_engine.extract_user_lemma_principal(headers)

    assert principal is None
    assert error == "invalid_lemma_header"

