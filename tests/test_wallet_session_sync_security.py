import os

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
