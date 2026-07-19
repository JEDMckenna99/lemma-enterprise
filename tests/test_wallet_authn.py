from __future__ import annotations

import pytest

from api.wallet_authn import (
    issue_device_enrollment_grant,
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


def _register(wallet_fixture, *, device_id: str = "legacy"):
    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
        device_id=device_id,
        enrollment_grant=issue_device_enrollment_grant(
            wallet_id=wallet_fixture["wallet_id"],
            source="test_wallet_authn",
        ),
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
        enrollment_grant=issue_device_enrollment_grant(
            wallet_id=wallet_fixture["wallet_id"],
            source="test_idempotent",
        ),
    )
    second = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
    )
    assert first.ok and second.ok


def test_register_concurrent_insert_is_idempotent(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    """Two requests can pass the no-existing-row check and race the INSERT
    against the wallet_signing_keys PK. The loser's commit raises
    IntegrityError; registration must treat the matching-pubkey winner as a
    success instead of bubbling a 500 (the live register-signing-key bug).
    """
    from sqlalchemy.exc import IntegrityError

    from tests.conftest import _FakeDbSession

    monkeypatch.setattr(
        "api.database.SessionLocal", fake_ishuman_db_session_factory.session_local
    )

    calls = {"n": 0}
    real_commit = _FakeDbSession.commit

    def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate the concurrent INSERT winning the PK first.
            raise IntegrityError("INSERT INTO wallet_signing_keys", {}, Exception("dup"))
        return real_commit(self)

    monkeypatch.setattr(_FakeDbSession, "commit", flaky_commit)

    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
        enrollment_grant=issue_device_enrollment_grant(
            wallet_id=wallet_fixture["wallet_id"],
            source="test_concurrent",
        ),
    )

    assert result.ok, (result.code, result.error)
    assert calls["n"] >= 1


def test_register_replace_pubkey_blocked_for_same_device(
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
        device_id="legacy",
        pubkey_b64=other_pubkey,
        signature_b64=b64url_encode(sig),
    )
    assert not result.ok
    assert result.code == "wallet_pubkey_mismatch"


def test_register_additional_device_requires_transfer_grant(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    _register(wallet_fixture)

    _priv, pub = derive_wallet_signing_keypair("ef" * 32)
    other_pubkey = pubkey_to_b64url(pub)
    from api.wallet_keys import build_register_payload, sign_message, b64url_encode

    payload = build_register_payload(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=other_pubkey,
    )
    sig = sign_message(_priv, payload)
    denied = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        device_id="dev_phone",
        pubkey_b64=other_pubkey,
        signature_b64=b64url_encode(sig),
    )
    assert not denied.ok
    assert denied.code == "device_enrollment_authorization_required"

    grant = issue_device_enrollment_grant(
        wallet_id=wallet_fixture["wallet_id"],
        source="test_transfer",
    )
    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        device_id="dev_phone",
        pubkey_b64=other_pubkey,
        signature_b64=b64url_encode(sig),
        enrollment_grant=grant,
    )
    assert result.ok

    third_priv, third_pub = derive_wallet_signing_keypair("12" * 32)
    third_pubkey = pubkey_to_b64url(third_pub)
    third_payload = build_register_payload(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=third_pubkey,
    )
    replayed = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        device_id="dev_tablet",
        pubkey_b64=third_pubkey,
        signature_b64=b64url_encode(sign_message(third_priv, third_payload)),
        enrollment_grant=grant,
    )
    assert not replayed.ok
    assert replayed.code == "device_enrollment_grant_invalid"


def test_established_identity_cannot_bootstrap_signing_key_without_recovery(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaWalletBinding

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        LemmaWalletBinding(
            wallet_id=wallet_fixture["wallet_id"],
            lemma_person_id="person_existing",
            binding_status="active",
        )
    )
    db.commit()
    db.close()

    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
    )
    assert not result.ok
    assert result.code == "device_enrollment_authorization_required"


def test_unbound_first_device_requires_webauthn_enrollment(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    denied = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
    )
    assert not denied.ok
    assert denied.code == "first_device_webauthn_enrollment_required"

    allowed = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
        allow_first_device_bootstrap=True,
    )
    assert allowed.ok


def test_revoke_device_marks_key_revoked(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import WalletSigningKey
    from api.wallet_authn import count_active_wallet_devices, revoke_wallet_device

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    _register(wallet_fixture)
    assert count_active_wallet_devices(wallet_fixture["wallet_id"]) == 1
    result = revoke_wallet_device(wallet_id=wallet_fixture["wallet_id"], device_id="legacy")
    assert result.ok
    assert count_active_wallet_devices(wallet_fixture["wallet_id"]) == 0


def test_assertion_with_device_id_matches_wallet_sdk_binding(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    """Wallet SDK always signs device_id; server must verify the same payload."""
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    pubkey_b64, sig_b64 = register_self_signature(
        wallet_fixture["wallet_id"],
        wallet_fixture["wallet_secret"],
    )
    result = register_wallet_signing_key(
        wallet_id=wallet_fixture["wallet_id"],
        pubkey_b64=pubkey_b64,
        signature_b64=sig_b64,
        device_id="dev_browser",
        enrollment_grant=issue_device_enrollment_grant(
            wallet_id=wallet_fixture["wallet_id"],
            source="test_device_binding",
        ),
    )
    assert result.ok

    challenge = issue_wallet_challenge(
        wallet_id=wallet_fixture["wallet_id"],
        device_id="dev_browser",
    )
    body = {
        "wallet_id": wallet_fixture["wallet_id"],
        "master_credential_id": "ishuman_master_x",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
        "issue_mode": "site_proof",
    }
    assertion = build_wallet_assertion(
        wallet_id=wallet_fixture["wallet_id"],
        wallet_secret=wallet_fixture["wallet_secret"],
        field_names=DERIVE_ASSERTION_FIELDS,
        field_values={**body, "device_id": "dev_browser"},
        nonce_b64=challenge["nonce"],
    )
    body["wallet_assertion"] = {
        "nonce": assertion.nonce,
        "signature": assertion.signature,
        "device_id": "dev_browser",
    }

    ok_result, fields = verify_assertion_from_body(
        body,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert ok_result.ok
    assert fields.get("device_id") == "dev_browser"


def test_legacy_register_defaults_device_id_and_asserts_without_device_id(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    """Pre-migration wallets register without device_id and keep asserting as legacy."""
    from api.database import WalletSigningKey

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    pubkey_b64 = _register(wallet_fixture)

    db = fake_ishuman_db_session_factory.session_local()
    row = (
        db.query(WalletSigningKey)
        .filter_by(wallet_id=wallet_fixture["wallet_id"], device_id="legacy")
        .first()
    )
    db.close()
    assert row is not None
    assert row.device_id == "legacy"

    challenge = issue_wallet_challenge(wallet_id=wallet_fixture["wallet_id"])
    body = {
        "wallet_id": wallet_fixture["wallet_id"],
        "master_credential_id": "ishuman_master_x",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
        "issue_mode": "site_proof",
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

    ok_result, fields = verify_assertion_from_body(
        body,
        wallet_id=wallet_fixture["wallet_id"],
        field_names=DERIVE_ASSERTION_FIELDS,
    )
    assert ok_result.ok
    assert fields.get("device_id") == "legacy"



def test_lost_device_recovery_authorization_is_one_time(
    wallet_fixture,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import IsHumanVerification, LemmaWalletBinding
    from api.wallet_authn import issue_lost_device_recovery_authorization

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        LemmaWalletBinding(
            wallet_id=wallet_fixture["wallet_id"],
            lemma_person_id="person_recovery",
            binding_status="active",
        )
    )
    db.add(
        IsHumanVerification(
            session_id="idv_recovery_1",
            wallet_id=wallet_fixture["wallet_id"],
            status="verified",
        )
    )
    db.commit()
    db.close()

    denied = issue_lost_device_recovery_authorization(
        wallet_id=wallet_fixture["wallet_id"],
        idv_session_id="idv_unknown",
    )
    assert not denied[0].ok

    first = issue_lost_device_recovery_authorization(
        wallet_id=wallet_fixture["wallet_id"],
        idv_session_id="idv_recovery_1",
    )
    assert first[0].ok
    assert first[1].startswith("wra_")

    replay = issue_lost_device_recovery_authorization(
        wallet_id=wallet_fixture["wallet_id"],
        idv_session_id="idv_recovery_1",
    )
    assert not replay[0].ok
    assert replay[0].code == "idv_recovery_already_consumed"
