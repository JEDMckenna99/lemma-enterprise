import os
import time

os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-unit-tests")

from flask import Flask

from api import wallet_session_sync


def test_suffix_matching_requires_domain_boundary():
    assert wallet_session_sync._host_matches_suffix("api.example.com", "example.com") is True
    assert wallet_session_sync._host_matches_suffix("example.com", "example.com") is True
    assert wallet_session_sync._host_matches_suffix("badexample.com", "example.com") is False


def test_origin_allowed_rejects_boundary_bypass(monkeypatch):
    monkeypatch.setattr(wallet_session_sync, "_ALLOWED_ORIGINS", set())
    monkeypatch.setattr(wallet_session_sync, "_ALLOWED_ORIGIN_SUFFIXES", ["example.com"])
    monkeypatch.setattr(wallet_session_sync, "_ALLOW_DEV_ORIGINS", False)

    assert wallet_session_sync._origin_allowed("https://api.example.com") is True
    assert wallet_session_sync._origin_allowed("https://badexample.com") is False


def test_lemma_origin_allowed_rejects_substring_spoof(monkeypatch):
    monkeypatch.setattr(wallet_session_sync, "_ALLOW_DEV_ORIGINS", False)

    assert wallet_session_sync._lemma_origin_allowed("https://lemma.id") is True
    assert wallet_session_sync._lemma_origin_allowed("https://wallet.lemma.id") is True
    assert wallet_session_sync._lemma_origin_allowed("https://lemma.id.attacker.com") is False


def test_init_first_session_is_retired():
    response = _client().post(
        "/api/wallet/init-first-session",
        json={"wallet_id": "wallet_known"},
        headers={"Origin": "https://lemma.id"},
    )
    assert response.status_code == 410
    assert response.get_json()["error"] == "first_session_route_retired"


def test_signal_unlock_rejects_wallet_id_without_assertion():
    now_ms = int(time.time() * 1000)
    response = _client().post(
        "/api/wallet/signal-unlock",
        json={
            "wallet_id": "wallet_known",
            "unlocked_at": now_ms,
            "expires_at": int(time.time()) + 3600,
            "profile_id": "default",
            "profile_name": "Personal",
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "fresh_webauthn_session_required"


def test_signal_unlock_accepts_verified_wallet_assertion(monkeypatch):
    from api.wallet_authn import Result

    monkeypatch.setattr(
        wallet_session_sync,
        "validate_session_token",
        lambda _token: {"wallet_id": "wallet_verified"},
    )
    monkeypatch.setattr(
        "api.wallet_authn.verify_assertion_from_body",
        lambda *_args, **_kwargs: (Result(True), {}),
    )
    client = _client()
    client.set_cookie(wallet_session_sync.SESSION_COOKIE_NAME, "session")
    client.set_cookie(wallet_session_sync.CSRF_COOKIE_NAME, "csrf")
    now_ms = int(time.time() * 1000)
    response = client.post(
        "/api/wallet/signal-unlock",
        json={
            "wallet_id": "wallet_verified",
            "unlocked_at": now_ms,
            "expires_at": int(time.time()) + 3600,
            "profile_id": "default",
            "profile_name": "Personal",
            "wallet_assertion": {"nonce": "nonce", "signature": "signature"},
        },
        headers={"Origin": "https://lemma.id", "X-Lemma-CSRF": "csrf"},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert wallet_session_sync.SESSION_COOKIE_NAME in response.headers.getlist("Set-Cookie")[0]


def test_signal_unlock_refresh_requires_csrf(monkeypatch):
    monkeypatch.setattr(
        wallet_session_sync,
        "validate_session_token",
        lambda _token: {"wallet_id": "wallet_verified"},
    )
    client = _client()
    client.set_cookie(wallet_session_sync.SESSION_COOKIE_NAME, "session")
    client.set_cookie(wallet_session_sync.CSRF_COOKIE_NAME, "csrf")
    response = client.post(
        "/api/wallet/signal-unlock",
        json={
            "wallet_id": "wallet_verified",
            "unlocked_at": int(time.time() * 1000),
            "expires_at": int(time.time()) + 3600,
            "profile_id": "default",
            "profile_name": "Personal",
            "wallet_assertion": {"nonce": "nonce", "signature": "signature"},
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "csrf_validation_failed"


def test_server_webauthn_unlock_issues_session_once(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import WalletPasskey

    monkeypatch.setattr(
        "api.database.SessionLocal",
        fake_ishuman_db_session_factory.session_local,
    )
    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        WalletPasskey(
            wallet_id="wallet_webauthn",
            device_id="dev_browser",
            credential_id="credential_1",
            public_key="public_key_1",
            sign_count=0,
        )
    )
    db.commit()
    db.close()

    client = _client()
    begin = client.post(
        "/api/wallet/session-unlock/begin",
        json={
            "wallet_id": "wallet_webauthn",
            "device_id": "dev_browser",
            "credential_id": "credential_1",
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert begin.status_code == 200
    challenge_key = begin.get_json()["challenge_key"]

    monkeypatch.setattr(
        "api.fresh_passkey_attestation.verify_wallet_webauthn_assertion",
        lambda **_kwargs: (True, "valid", 1),
    )
    monkeypatch.setattr(
        "api.fresh_passkey_attestation.update_wallet_passkey_sign_count",
        lambda *_args, **_kwargs: None,
    )
    complete = client.post(
        "/api/wallet/session-unlock/complete",
        json={
            "challenge_key": challenge_key,
            "credential": {"id": "credential_1", "response": {}},
            "profile_id": "default",
            "profile_name": "Personal",
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert complete.status_code == 200
    assert complete.get_json()["auth_method"] == "webauthn"
    assert any(
        wallet_session_sync.SESSION_COOKIE_NAME in value
        for value in complete.headers.getlist("Set-Cookie")
    )

    replay = client.post(
        "/api/wallet/session-unlock/complete",
        json={
            "challenge_key": challenge_key,
            "credential": {"id": "credential_1", "response": {}},
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert replay.status_code == 401
    assert replay.get_json()["error"] == "wallet_unlock_challenge_expired"


def test_clear_session_requires_bound_session_and_csrf(monkeypatch):
    unauthenticated = _client().post(
        "/api/wallet/clear-session",
        json={"wallet_id": "wallet_victim"},
        headers={"Origin": "https://lemma.id"},
    )
    assert unauthenticated.status_code == 401

    monkeypatch.setattr(
        wallet_session_sync,
        "validate_session_token",
        lambda _token: {"wallet_id": "wallet_owner"},
    )
    client = _client()
    client.set_cookie(wallet_session_sync.SESSION_COOKIE_NAME, "session")
    client.set_cookie(wallet_session_sync.CSRF_COOKIE_NAME, "csrf")

    mismatch = client.post(
        "/api/wallet/clear-session",
        json={"wallet_id": "wallet_victim"},
        headers={"Origin": "https://lemma.id", "X-Lemma-CSRF": "csrf"},
    )
    assert mismatch.status_code == 403
    assert mismatch.get_json()["error"] == "wallet_session_mismatch"

    valid = client.post(
        "/api/wallet/clear-session",
        json={"wallet_id": "wallet_owner"},
        headers={"Origin": "https://lemma.id", "X-Lemma-CSRF": "csrf"},
    )
    assert valid.status_code == 200
    assert valid.get_json()["session_cleared"] is True


def _client():
    app = Flask(__name__)
    app.register_blueprint(wallet_session_sync.wallet_session_sync_bp)
    return app.test_client()


def test_cli_link_start_returns_approve_and_poll_urls():
    client = _client()
    response = client.post("/api/wallet/cli-link/start", json={"requested_scope": "wallet:revoke"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["state"]
    assert "/api/wallet/cli-link/approve?state=" in payload["approve_url"]
    assert "/api/wallet/cli-link/poll?state=" in payload["poll_url"]


def test_cli_link_approve_then_poll_returns_unlock_token_once(monkeypatch):
    client = _client()
    start = client.post("/api/wallet/cli-link/start", json={"requested_scope": "wallet:revoke"}).get_json()
    state = start["state"]

    monkeypatch.setattr(
        wallet_session_sync,
        "validate_session_token",
        lambda _token: {"wallet_id": "wallet_demo", "unlocked_at": 1700000000},
    )
    monkeypatch.setattr(wallet_session_sync, "generate_unlock_token", lambda *_args: "lm_unlock_demo")

    client.set_cookie(wallet_session_sync.SESSION_COOKIE_NAME, "session_cookie_value")
    client.set_cookie(wallet_session_sync.CSRF_COOKIE_NAME, "csrf")
    confirmation = client.get(f"/api/wallet/cli-link/approve?state={state}")
    assert confirmation.status_code == 200
    assert b"Approve CLI Link" in confirmation.data

    approve = client.post(
        f"/api/wallet/cli-link/approve?state={state}",
        data={"csrf_token": "csrf"},
    )
    assert approve.status_code == 200
    assert b"CLI Link Approved" in approve.data

    poll = client.get(f"/api/wallet/cli-link/poll?state={state}")
    assert poll.status_code == 200
    poll_payload = poll.get_json()
    assert poll_payload["approved"] is True
    assert poll_payload["wallet_id"] == "wallet_demo"
    assert poll_payload["unlock_token"] == "lm_unlock_demo"

    # One-time read semantics: subsequent poll should not return token again.
    poll_again = client.get(f"/api/wallet/cli-link/poll?state={state}")
    assert poll_again.status_code == 404


def test_cli_link_approve_without_session_points_to_unlock_return(monkeypatch):
    client = _client()
    start = client.post("/api/wallet/cli-link/start", json={"requested_scope": "wallet:revoke"}).get_json()
    state = start["state"]
    monkeypatch.setattr(wallet_session_sync, "validate_session_token", lambda _token: None)
    approve = client.get(f"/api/wallet/cli-link/approve?state={state}")
    assert approve.status_code == 401
    body = approve.data.decode("utf-8", errors="replace")
    assert "/unlock?return_url=" in body
    assert f"state%3D{state}" in body


def test_cli_link_approval_post_requires_csrf(monkeypatch):
    client = _client()
    start = client.post("/api/wallet/cli-link/start", json={"requested_scope": "wallet:revoke"}).get_json()
    state = start["state"]
    monkeypatch.setattr(
        wallet_session_sync,
        "validate_session_token",
        lambda _token: {"wallet_id": "wallet_demo", "unlocked_at": 1700000000},
    )
    client.set_cookie(wallet_session_sync.SESSION_COOKIE_NAME, "session_cookie_value")
    client.set_cookie(wallet_session_sync.CSRF_COOKIE_NAME, "csrf")
    denied = client.post(f"/api/wallet/cli-link/approve?state={state}")
    assert denied.status_code == 403


def test_cli_link_start_normalizes_duplicated_base_url(monkeypatch):
    client = _client()
    repeated = "https://lemma.id" * 7
    monkeypatch.setenv("LEMMA_BASE_URL", repeated)
    response = client.post("/api/wallet/cli-link/start", json={"requested_scope": "wallet:revoke"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["approve_url"].startswith("https://lemma.id/api/wallet/cli-link/approve")
    assert payload["approve_url"].count("https://lemma.id") == 1


def test_register_signing_key_rejects_unbound_first_device_without_ceremony(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.wallet_keys import register_self_signature

    monkeypatch.setattr(
        "api.database.SessionLocal",
        fake_ishuman_db_session_factory.session_local,
    )
    pubkey_b64, sig_b64 = register_self_signature("wallet_first", "ab" * 32)
    response = _client().post(
        "/api/wallet/register-signing-key",
        json={
            "wallet_id": "wallet_first",
            "device_id": "dev_browser",
            "pubkey": pubkey_b64,
            "signature": sig_b64,
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "first_device_webauthn_enrollment_required"


def test_device_enroll_complete_registers_signing_key_and_passkey(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import WalletPasskey, WalletSigningKey
    from api.wallet_keys import register_self_signature

    monkeypatch.setattr(
        "api.database.SessionLocal",
        fake_ishuman_db_session_factory.session_local,
    )

    class _Verification:
        credential_id = b"cred-bytes-1"
        credential_public_key = b"\x01" * 32
        sign_count = 0
        fmt = "none"

    monkeypatch.setattr(
        "webauthn.verify_registration_response",
        lambda **_kwargs: _Verification(),
    )

    client = _client()
    begin = client.post(
        "/api/wallet/device-enroll/begin",
        json={"wallet_id": "wallet_enroll", "device_id": "dev_browser"},
        headers={"Origin": "https://lemma.id"},
    )
    assert begin.status_code == 200
    challenge_key = begin.get_json()["challenge_key"]

    pubkey_b64, sig_b64 = register_self_signature("wallet_enroll", "cd" * 32)
    complete = client.post(
        "/api/wallet/device-enroll/complete",
        json={
            "challenge_key": challenge_key,
            "credential": {"id": "cred-1", "response": {}},
            "pubkey": pubkey_b64,
            "signature": sig_b64,
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert complete.status_code == 200, complete.get_json()
    payload = complete.get_json()
    assert payload["ceremony"] == "first_device"
    assert payload["credential_id"]

    db = fake_ishuman_db_session_factory.session_local()
    assert db.query(WalletSigningKey).filter_by(wallet_id="wallet_enroll").count() == 1
    assert db.query(WalletPasskey).filter_by(wallet_id="wallet_enroll").count() == 1
    db.close()

    replay = client.post(
        "/api/wallet/device-enroll/complete",
        json={
            "challenge_key": challenge_key,
            "credential": {"id": "cred-1", "response": {}},
            "pubkey": pubkey_b64,
            "signature": sig_b64,
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert replay.status_code == 401


def test_cross_device_revoke_requires_fresh_webauthn(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import WalletPasskey
    from api.wallet_authn import issue_device_enrollment_grant, register_wallet_signing_key
    from api.wallet_keys import register_self_signature

    monkeypatch.setattr(
        "api.database.SessionLocal",
        fake_ishuman_db_session_factory.session_local,
    )

    acting_secret = "11" * 32
    target_secret = "22" * 32
    wallet_id = "wallet_revoke_cross"
    acting_pub, acting_sig = register_self_signature(wallet_id, acting_secret)
    target_pub, target_sig = register_self_signature(wallet_id, target_secret)
    assert register_wallet_signing_key(
        wallet_id=wallet_id,
        device_id="dev_acting",
        pubkey_b64=acting_pub,
        signature_b64=acting_sig,
        enrollment_grant=issue_device_enrollment_grant(wallet_id=wallet_id, source="test"),
    ).ok
    assert register_wallet_signing_key(
        wallet_id=wallet_id,
        device_id="dev_target",
        pubkey_b64=target_pub,
        signature_b64=target_sig,
        enrollment_grant=issue_device_enrollment_grant(wallet_id=wallet_id, source="test"),
    ).ok

    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        WalletPasskey(
            wallet_id=wallet_id,
            device_id="dev_acting",
            credential_id="cred_acting",
            public_key="pk_acting",
            sign_count=0,
        )
    )
    db.commit()
    db.close()

    body = {
        "wallet_id": wallet_id,
        "device_id": "dev_target",
        "acting_device_id": "dev_acting",
        "target_device_id": "dev_target",
    }
    # Build assertion with the acting device secret/key.
    from api.wallet_authn import issue_wallet_challenge
    from api.wallet_keys import build_wallet_assertion

    challenge = issue_wallet_challenge(wallet_id=wallet_id, device_id="dev_acting")
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=acting_secret,
        field_names=["wallet_id", "device_id", "target_device_id"],
        field_values={
            "wallet_id": wallet_id,
            "device_id": "dev_acting",
            "target_device_id": "dev_target",
        },
        nonce_b64=challenge["nonce"],
    )
    body["wallet_assertion"] = {
        "nonce": assertion.nonce,
        "signature": assertion.signature,
    }

    denied = _client().post(
        "/api/wallet/revoke-device",
        json=body,
        headers={"Origin": "https://lemma.id"},
    )
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "fresh_webauthn_required_for_cross_device_revoke"

    begin = _client().post(
        "/api/wallet/device-revoke/begin",
        json={
            "wallet_id": wallet_id,
            "acting_device_id": "dev_acting",
            "target_device_id": "dev_target",
            "credential_id": "cred_acting",
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert begin.status_code == 200
    challenge_key = begin.get_json()["challenge_key"]

    monkeypatch.setattr(
        "api.fresh_passkey_attestation.verify_wallet_webauthn_assertion",
        lambda **_kwargs: (True, "valid", 1),
    )
    monkeypatch.setattr(
        "api.fresh_passkey_attestation.update_wallet_passkey_sign_count",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "api.fresh_passkey_attestation.lookup_wallet_passkey_public_key",
        lambda _credential_id: ("pk_acting", 0),
    )

    # Fresh assertion for the authorized revoke.
    challenge = issue_wallet_challenge(wallet_id=wallet_id, device_id="dev_acting")
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=acting_secret,
        field_names=["wallet_id", "device_id", "target_device_id"],
        field_values={
            "wallet_id": wallet_id,
            "device_id": "dev_acting",
            "target_device_id": "dev_target",
        },
        nonce_b64=challenge["nonce"],
    )
    authorized = _client().post(
        "/api/wallet/revoke-device",
        json={
            "wallet_id": wallet_id,
            "device_id": "dev_target",
            "acting_device_id": "dev_acting",
            "target_device_id": "dev_target",
            "challenge_key": challenge_key,
            "credential": {"id": "cred_acting", "response": {}},
            "wallet_assertion": {
                "nonce": assertion.nonce,
                "signature": assertion.signature,
            },
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert authorized.status_code == 200, authorized.get_json()
    assert authorized.get_json()["cross_device"] is True


def test_lost_device_recovery_complete_enrolls_and_revokes_prior_devices(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import IsHumanVerification, LemmaWalletBinding, WalletSigningKey
    from api.wallet_authn import (
        issue_device_enrollment_grant,
        issue_lost_device_recovery_authorization,
        register_wallet_signing_key,
    )
    from api.wallet_keys import register_self_signature

    monkeypatch.setattr(
        "api.database.SessionLocal",
        fake_ishuman_db_session_factory.session_local,
    )
    wallet_id = "wallet_lost_recover"
    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        LemmaWalletBinding(
            wallet_id=wallet_id,
            lemma_person_id="person_lost",
            binding_status="active",
        )
    )
    db.add(
        IsHumanVerification(
            session_id="idv_lost_1",
            wallet_id=wallet_id,
            status="verified",
        )
    )
    db.commit()
    db.close()

    old_pub, old_sig = register_self_signature(wallet_id, "aa" * 32)
    assert register_wallet_signing_key(
        wallet_id=wallet_id,
        device_id="dev_old",
        pubkey_b64=old_pub,
        signature_b64=old_sig,
        enrollment_grant=issue_device_enrollment_grant(wallet_id=wallet_id, source="test"),
    ).ok

    auth_result, recovery_auth = issue_lost_device_recovery_authorization(
        wallet_id=wallet_id,
        idv_session_id="idv_lost_1",
    )
    assert auth_result.ok

    class _Verification:
        credential_id = b"recovery-cred"
        credential_public_key = b"\x02" * 32
        sign_count = 0
        fmt = "none"

    monkeypatch.setattr(
        "webauthn.verify_registration_response",
        lambda **_kwargs: _Verification(),
    )

    client = _client()
    begin = client.post(
        "/api/wallet/lost-device-recovery/begin",
        json={
            "wallet_id": wallet_id,
            "device_id": "dev_new",
            "recovery_authorization": recovery_auth,
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert begin.status_code == 200, begin.get_json()
    challenge_key = begin.get_json()["challenge_key"]

    new_pub, new_sig = register_self_signature(wallet_id, "bb" * 32)
    complete = client.post(
        "/api/wallet/lost-device-recovery/complete",
        json={
            "challenge_key": challenge_key,
            "credential": {"id": "recovery-cred", "response": {}},
            "pubkey": new_pub,
            "signature": new_sig,
        },
        headers={"Origin": "https://lemma.id"},
    )
    assert complete.status_code == 200, complete.get_json()
    payload = complete.get_json()
    assert payload["ceremony"] == "lost_device_recovery"
    assert "dev_old" in payload["revoked_devices"]

    db = fake_ishuman_db_session_factory.session_local()
    old = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id, device_id="dev_old").first()
    new = db.query(WalletSigningKey).filter_by(wallet_id=wallet_id, device_id="dev_new").first()
    assert old.revoked_at is not None
    assert new is not None and new.revoked_at is None
    db.close()


def test_lost_device_recovery_rejects_wallet_id_without_idv(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.database.SessionLocal",
        fake_ishuman_db_session_factory.session_local,
    )
    response = _client().post(
        "/api/wallet/lost-device-recovery/authorize",
        json={"wallet_id": "wallet_unknown", "session_id": "idv_missing"},
        headers={"Origin": "https://lemma.id"},
    )
    assert response.status_code == 403
