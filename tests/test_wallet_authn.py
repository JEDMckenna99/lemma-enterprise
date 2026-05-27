from __future__ import annotations

import pytest

from api.wallet_authn import (
    issue_wallet_challenge,
    register_wallet_signing_key,
    verify_assertion_from_body,
)
from api.wallet_keys import (
    build_wallet_assertion,
    derive_wallet_signing_keypair,
    derive_wallet_signing_seed,
    pubkey_to_b64url,
    register_self_signature,
)
from tests.wallet_test_helpers import DERIVE_ASSERTION_FIELDS, SITE_SIGNING_PUBKEY_B64


@pytest.fixture
def wallet_fixture():
    return {
        "wallet_id": "wallet_authn_test",
        "wallet_secret": "cd" * 32,
    }


def _register(wallet_fixture):
    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
    )
    assert result.ok
    return pubkey_b64


def test_wallet_signing_seed_is_stable(wallet_fixture):
    a = derive_wallet_signing_seed(wallet_fixture["wallet_secret"])
    b = derive_wallet_signing_seed(wallet_fixture["wallet_secret"])
    assert a == b
    assert len(a) == 32


def test_register_then_assert_then_replay_fails(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    _register(wallet_fixture)

    challenge = issue_wallet_challenge(wallet_id=wallet_fixture["wallet_id"])
    body = {
        "wallet_id": wallet_fixture["wallet_id"],
        "master_credential_id": "ishuman_master_x",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
    }
    assertion = build_wallet_assertion(
        wallet_id=wallet_fixture["wallet_id"],
        wallet_secret=wallet_fixture["wallet_secret"],
        field_names=DERIVE_ASSERTION_FIELDS,
        field_values=body,
        nonce_b64=challenge["nonce"],
    )
    body["wallet_assertion"] = {
        "nonce": assertion.nonce,
        "signature": assertion.signature,
    }

    ok_result, _fields = verify_assertion_from_body(
        body,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert ok_result.ok

    replay_result, _ = verify_assertion_from_body(
        body,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert not replay_result.ok
    assert replay_result.code in {
        "wallet_assertion_nonce_replay",
        "wallet_assertion_nonce_unknown",
    }


def test_assert_with_unregistered_wallet_fails(wallet_fixture, fake_ishuman_db_session_factory, monkeypatch):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    challenge = issue_wallet_challenge(wallet_id=wallet_fixture["wallet_id"])
    body = {
        "wallet_id": wallet_fixture["wallet_id"],
        "master_credential_id": "x",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
        "wallet_assertion": {
            "nonce": challenge["nonce"],
            "signature": "AAAA",
        },
    }
    result, _ = verify_assertion_from_body(
        body,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert not result.ok
    assert result.code == "wallet_not_registered"


def test_assert_with_bad_signature_fails(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    _register(wallet_fixture)
    challenge = issue_wallet_challenge(wallet_id=wallet_fixture["wallet_id"])
    body = {
        "wallet_id": wallet_fixture["wallet_id"],
        "master_credential_id": "x",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
        "wallet_assertion": {"nonce": challenge["nonce"], "signature": "AAAA"},
    }
    result, _ = verify_assertion_from_body(
        body,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert not result.ok
    assert result.code in {"wallet_assertion_malformed", "wallet_assertion_invalid_signature"}


def test_assert_with_field_tampering_fails(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    _register(wallet_fixture)
    challenge = issue_wallet_challenge(wallet_id=wallet_fixture["wallet_id"])
    signed_body = {
        "wallet_id": wallet_fixture["wallet_id"],
        "master_credential_id": "ishuman_master_x",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
    }
    assertion = build_wallet_assertion(
        wallet_id=wallet_fixture["wallet_id"],
        wallet_secret=wallet_fixture["wallet_secret"],
        field_names=DERIVE_ASSERTION_FIELDS,
        field_values=signed_body,
        nonce_b64=challenge["nonce"],
    )
    tampered = dict(signed_body)
    tampered["target_site"] = "evil.example"
    tampered["wallet_assertion"] = {
        "nonce": assertion.nonce,
        "signature": assertion.signature,
    }
    result, _ = verify_assertion_from_body(
        tampered,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert not result.ok
    assert result.code == "wallet_assertion_invalid_signature"


def test_register_idempotent_for_same_pubkey(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    first = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
    )
    second = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
    )
    assert first.ok and second.ok


def test_register_replace_pubkey_blocked_in_phase1(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    _register(wallet_fixture)

    _priv, pub = derive_wallet_signing_keypair("ef" * 32)
    other_pubkey = pubkey_to_b64url(pub)
    from api.wallet_keys import build_register_payload, sign_message

    payload = build_register_payload(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=other_pubkey,
    )
    sig = sign_message(_priv, payload)
    from api.wallet_keys import b64url_encode

    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=other_pubkey,
        signature_b64=b64url_encode(sig),
    )
    assert not result.ok
    assert result.code == "wallet_pubkey_mismatch"

