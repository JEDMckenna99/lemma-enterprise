"""Live wallet flow against staging: signing keys, challenges, and guardrails."""

from __future__ import annotations

import secrets

import pytest

requests = pytest.importorskip("requests")

from api.wallet_keys import build_wallet_assertion, register_self_signature  # noqa: E402
from tests.live.live_test_helpers import (  # noqa: E402
    assert_status,
    post_json,
    register_wallet_signing_key,
    require_platform_staging_env,
    wallet_challenge,
)

pytestmark = pytest.mark.live_platform


def test_live_staging_wallet_signing_and_guardrails():
    base = require_platform_staging_env()
    wallet_id = "wallet_platform_" + secrets.token_hex(5)
    wallet_secret = "ab" * 32
    session = requests.Session()

    register_wallet_signing_key(session, base, wallet_id, wallet_secret)

    nonce = wallet_challenge(session, base, wallet_id)
    assert nonce

    return_url = f"{base}/demo/ishuman"
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=["return_url"],
        field_values={"return_url": return_url},
        nonce_b64=nonce,
    )
    status, data = post_json(
        session,
        base,
        "/api/ishuman/start-verification",
        {
            "wallet_id": wallet_id,
            "return_url": return_url,
            "provider": "didit",
            "wallet_assertion": {"nonce": assertion.nonce, "signature": assertion.signature},
        },
    )
    assert (data.get("error") or "") != "wallet_assertion_invalid_signature", data
    assert status in (200, 400, 403), data

    status, _ = post_json(session, base, "/api/wallet/session-sync", {})
    assert status in (401, 403), f"session-sync should deny unauthenticated callers, got {status}"

    status, data = post_json(session, base, "/api/passkey/authenticate/begin", {})
    assert status == 200, data
    assert data.get("success") is True, data

    status, data = post_json(
        session,
        base,
        "/api/wallet/cli-link/start",
        {"requested_scope": "wallet:revoke"},
    )
    assert status == 200, data
    assert data.get("success") is True, data
    assert "/api/wallet/cli-link/approve?state=" in (data.get("approve_url") or ""), data
    assert "/api/wallet/cli-link/poll?state=" in (data.get("poll_url") or ""), data

    pubkey_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    reg = session.post(
        f"{base}/api/wallet/register-signing-key",
        json={"wallet_id": wallet_id, "pubkey": pubkey_b64, "signature": sig_b64},
        timeout=30,
    )
    assert_status(reg, {200, 403}, label="idempotent re-register")
