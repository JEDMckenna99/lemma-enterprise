from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _patch_signing_material(monkeypatch):
    from api.wallet_keys import derive_wallet_signing_keypair

    private_key, public_key = derive_wallet_signing_keypair("ef" * 32)

    def _material():
        return private_key, public_key, "did:lemma:" + ("b" * 64)

    monkeypatch.setattr("api.bloom_snapshot._issuer_signing_material", _material)
    monkeypatch.setenv("LEMMA_ALLOW_UNPINNED_TRUST_ROOT", "1")


@pytest.mark.unit
def test_build_signed_trust_list_contains_entries():
    from api.issuer_trust_list import build_signed_trust_list

    payload = build_signed_trust_list()
    assert payload["signature"]
    assert payload["signer_pubkey"]
    assert isinstance(payload["issuers"], list)
    assert payload["issuers"]


@pytest.mark.unit
def test_verify_signed_trust_list_round_trip():
    from api.issuer_trust_list import build_signed_trust_list, verify_signed_trust_list

    payload = build_signed_trust_list()
    ok, reason = verify_signed_trust_list(payload)
    assert ok, reason


@pytest.mark.unit
def test_verify_signed_trust_list_rejects_tamper():
    from api.issuer_trust_list import build_signed_trust_list, verify_signed_trust_list

    payload = build_signed_trust_list()
    payload["issuers"][0]["pubkey"] = "0" * 64
    ok, reason = verify_signed_trust_list(payload)
    assert not ok
    assert reason == "trust_list_content_hash_mismatch"


@pytest.mark.unit
def test_verify_signed_trust_list_rejects_unpinned_self_signed(monkeypatch):
    from api.issuer_trust_list import build_signed_trust_list, verify_signed_trust_list

    monkeypatch.delenv("LEMMA_ALLOW_UNPINNED_TRUST_ROOT", raising=False)
    monkeypatch.setenv("LEMMA_NETWORK_ROOT_PUBKEYS", "cc" * 32)

    payload = build_signed_trust_list()
    payload["signer_pubkey"] = "aa" * 32
    payload["signature"] = "AAAA"

    ok, reason = verify_signed_trust_list(payload)
    assert not ok
    assert reason == "trust_list_signer_not_pinned"
