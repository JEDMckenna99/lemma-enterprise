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
    approve = client.get(f"/api/wallet/cli-link/approve?state={state}")
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
