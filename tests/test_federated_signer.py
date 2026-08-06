"""Federated signer remote/local behavior."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_get_federated_issuer_blocks_seed_on_web_when_remote(monkeypatch):
    monkeypatch.setenv("LEMMA_SIGNING_SERVICE_URL", "https://signing.example")
    monkeypatch.setenv("LEMMA_SIGNING_SERVICE_TOKEN", "test-token")
    monkeypatch.delenv("LEMMA_SIGNING_SERVICE", raising=False)

    from api.federated_signer import reset_federated_signer_cache
    from api.issuer_management import get_issuer_manager

    reset_federated_signer_cache()

    with pytest.raises(RuntimeError, match="LEMMA_SIGNING_SERVICE_URL"):
        get_issuer_manager().get_federated_issuer()


@pytest.mark.unit
def test_remote_signer_issue_credential(monkeypatch):
    monkeypatch.setenv("LEMMA_SIGNING_SERVICE_URL", "https://signing.example")
    monkeypatch.setenv("LEMMA_SIGNING_SERVICE_TOKEN", "test-token")
    monkeypatch.delenv("LEMMA_SIGNING_SERVICE", raising=False)

    from api.federated_signer import RemoteFederatedSigner, reset_federated_signer_cache

    reset_federated_signer_cache()
    signer = RemoteFederatedSigner()

    responses = [
        {"success": True, "issuer_did": "did:lemma:abc", "pubkey_hex": "a" * 64},
        {
            "success": True,
            "credential": {
                "issuer": "did:lemma:abc",
                "subject": "did:lemma:ppid_deadbeef",
                "claims": {"assurance": "passkey"},
                "proof": {"signatureValueWeb": "ff" * 32},
            },
        },
    ]

    def fake_request(path, payload):
        if path == "/internal/issuer-info":
            return responses[0]
        assert path == "/internal/issue-credential"
        return responses[1]

    with patch.object(signer, "_request", side_effect=fake_request):
        assert signer.get_did() == "did:lemma:abc"
        cred = signer.issue_credential("did:lemma:ppid_deadbeef", {"assurance": "passkey"})
        assert cred["subject"] == "did:lemma:ppid_deadbeef"
