"""Wave 3 security containment regression tests."""

from __future__ import annotations

import base64
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from flask import Flask

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("SESSION_SECRET", "containment-wave3-session-secret")
os.environ.setdefault("LEMMA_ACCESS_TOKEN_SECRET", "containment-wave3-access-token-secret")


PPID = (
    "did:lemma:ppid_abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
)


@pytest.fixture
def flow_app(monkeypatch):
    monkeypatch.setenv("LEMMA_REQUIRE_VERIFY_FLOW_STATE", "1")
    from api.verify_flow_state import verify_flow_state_bp
    from api.ishuman_demo import ishuman_demo_bp

    app = Flask(
        __name__,
        template_folder=str(REPO_ROOT / "templates"),
        static_folder=str(REPO_ROOT / "static"),
    )
    app.config["TESTING"] = True
    app.register_blueprint(verify_flow_state_bp)
    app.register_blueprint(ishuman_demo_bp)
    return app


def test_flow_state_rejects_origin_site_mismatch(flow_app):
    with flow_app.test_client() as client:
        resp = client.post(
            "/api/verify/flow-state",
            json={"site_id": "victim.example.com", "issue_mode": "site_proof"},
            headers={"Origin": "https://evil.example.com"},
        )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "origin_site_mismatch"


def test_flow_state_mints_for_demo_heroku_hostnames(flow_app):
    """Demo apps use their Heroku hostname as siteId — same as any integrator."""
    with flow_app.test_client() as client:
        tickets_host = "lemma-demo-tickets-1d3d7411af33.herokuapp.com"
        tickets = client.post(
            "/api/verify/flow-state",
            json={"site_id": tickets_host, "issue_mode": "site_proof"},
            headers={"Origin": f"https://{tickets_host}"},
        )
        assert tickets.status_code == 200, tickets.get_json()
        assert tickets.get_json()["site_id"] == tickets_host

        trials_host = "lemma-demo-trials-7090f46cae0d.herokuapp.com"
        trials = client.post(
            "/api/verify/flow-state",
            json={"site_id": trials_host, "issue_mode": "site_proof"},
            headers={"Origin": f"https://{trials_host}"},
        )
        assert trials.status_code == 200, trials.get_json()
        assert trials.get_json()["site_id"] == trials_host


def test_flow_state_mints_and_binds_verify_page(flow_app, monkeypatch):
    monkeypatch.setattr("api.verify_flow_state.require_verify_flow_state", lambda: True)
    with flow_app.test_client() as client:
        mint = client.post(
            "/api/verify/flow-state",
            json={
                "site_id": "tickets.example.com",
                "issue_mode": "site_proof",
                "redirect_return": "https://tickets.example.com/app",
                "request_nonce": "nonce123",
            },
            headers={"Origin": "https://tickets.example.com"},
        )
        assert mint.status_code == 200
        body = mint.get_json()
        assert body["success"] is True
        token = body["flow_state"]
        assert body["opener_origin"] == "https://tickets.example.com"
        assert body["site_id"] == "tickets.example.com"

        # Attacker-controlled query params must not override server binding.
        page = client.get(
            f"/verify?flow_state={token}"
            f"&origin=https%3A%2F%2Fevil.example.com"
            f"&site_id=victim.example.com"
            f"&issue_mode=site_proof"
            f"&session_nonce=abc"
        )
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        assert "https://tickets.example.com" in html
        assert "tickets.example.com" in html
        assert "evil.example.com" not in html.split("const SERVER_FLOW", 1)[1].split(
            "const FLOW_STATE_ERROR", 1
        )[0]


def test_verify_page_requires_flow_state_for_site_ceremony(flow_app, monkeypatch):
    monkeypatch.setattr("api.verify_flow_state.require_verify_flow_state", lambda: True)
    with flow_app.test_client() as client:
        resp = client.get(
            "/verify?origin=https%3A%2F%2Fevil.example.com&site_id=victim.example.com&issue_mode=site_proof&session_nonce=x"
        )
        assert resp.status_code == 400
        assert "flow state" in resp.get_data(as_text=True).lower()


def test_passkey_origin_suffix_default_empty():
    import importlib

    import api.passkey_auth as mod

    importlib.reload(mod)
    # Default env in this process may still carry suffixes; assert code default is empty.
    source = (REPO_ROOT / "api" / "passkey_auth.py").read_text(encoding="utf-8")
    assert "os.getenv('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '')" in source
    assert "os.getenv('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '.lemma.id')" not in source


def test_wallet_session_sync_rejects_subdomain_identity_origin(monkeypatch):
    import api.wallet_session_sync as wss

    monkeypatch.setattr(wss, "_ALLOW_DEV_ORIGINS", False)
    assert wss._lemma_origin_allowed("https://lemma.id") is True
    assert wss._lemma_origin_allowed("https://www.lemma.id") is True
    assert wss._lemma_origin_allowed("https://api.lemma.id") is False
    assert wss._lemma_origin_allowed("https://evil.lemma.id") is False


def test_recovery_begin_binds_challenge(monkeypatch):
    import api.account_recovery as mod
    from api.account_recovery import account_recovery_bp

    monkeypatch.setattr(mod, "redis_client", None)
    with mod._recovery_memory_lock:
        mod.recovery_tokens_memory.clear()

    token = "recovery-wave3-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    mod.store_recovery_token(
        token_hash,
        {
            "site_id": "example.com",
            "admin_email": "admin@example.com",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "used": False,
        },
    )

    monkeypatch.setattr(
        "api.fresh_passkey_attestation.lookup_wallet_passkey_public_key",
        lambda _cid: ("aGVsbG8=", 0),
    )

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "wave3-recovery"
    app.register_blueprint(account_recovery_bp)

    with app.test_client() as client:
        begin = client.post(
            "/api/recovery/webauthn/begin",
            json={
                "token": token,
                "ppid": PPID,
                "passkey_credential_id": "pk-wave3",
            },
        )
        assert begin.status_code == 200
        data = begin.get_json()
        assert data["success"] is True
        assert data["challenge_key"]
        assert data["challenge"]

        # Complete without challenge_key must fail closed.
        complete = client.post(
            "/api/recovery/complete",
            json={
                "token": token,
                "ppid": PPID,
                "passkey_credential_id": "pk-wave3",
                "webauthn_credential": {"id": "pk-wave3"},
            },
        )
        assert complete.status_code == 403
        assert complete.get_json()["error"] == "recovery_challenge_required"

        # Deterministic preimage challenge must no longer verify.
        ok, reason = mod._verify_recovery_webauthn_assertion(
            {
                "challenge_key": "missing",
                "webauthn_credential": {"id": "pk-wave3"},
            },
            token_hash=token_hash,
            passkey_credential_id="pk-wave3",
            ppid=PPID,
        )
        assert ok is False
        assert reason == "recovery_challenge_invalid"


def test_recovery_challenge_token_binding(monkeypatch):
    import api.account_recovery as mod
    from auth.redis_store import store as redis_store

    challenge_key = "rec_test_bind"
    token_hash = hashlib.sha256(b"tok-a").hexdigest()
    other_hash = hashlib.sha256(b"tok-b").hexdigest()
    challenge = base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("=")
    redis_store(
        mod._recovery_challenge_store_key(challenge_key),
        {
            "challenge": challenge,
            "token_hash": token_hash,
            "passkey_credential_id": "pk-1",
            "ppid": PPID,
        },
        ttl_seconds=60,
    )

    ok, reason = mod._verify_recovery_webauthn_assertion(
        {
            "challenge_key": challenge_key,
            "webauthn_credential": {"id": "pk-1"},
        },
        token_hash=other_hash,
        passkey_credential_id="pk-1",
        ppid=PPID,
    )
    assert ok is False
    assert reason == "recovery_challenge_token_mismatch"


def test_sdk_mentions_flow_state_mint():
    src = (REPO_ROOT / "static" / "js" / "ishuman-verifier.js").read_text(encoding="utf-8")
    assert "_mintVerifyFlowState" in src
    assert "/api/verify/flow-state" in src
    assert "flow_state" in src


def test_platform_manager_and_register_mint_flow_state_before_verify():
    """Create/anchor and register must never open /verify without a minted token."""
    manager = (REPO_ROOT / "templates" / "wallet_simple.html").read_text(encoding="utf-8")
    register = (REPO_ROOT / "templates" / "modern" / "register.html").read_text(encoding="utf-8")
    for src in (manager, register):
        assert "mintPlatformVerifyFlowState" in src
        assert "/api/verify/flow-state" in src
        assert "flow_state" in src
    assert "about:blank" in manager
    assert "popupUrl.searchParams.set('flow_state', flowState)" in manager
    assert "url.searchParams.set('flow_state', flowState)" in register


def test_idv_template_prefers_server_flow_binding():
    src = (REPO_ROOT / "templates" / "wallet_ishuman_idv.html").read_text(encoding="utf-8")
    assert "SERVER_FLOW" in src
    assert "verify_flow_binding" in src
    assert "flowStateBlocked" in src
