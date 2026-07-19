"""Live wallet flow against staging: signing keys, challenges, and guardrails."""

from __future__ import annotations

import secrets

import pytest

requests = pytest.importorskip("requests")

from api.wallet_keys import register_self_signature  # noqa: E402
from tests.live.live_test_helpers import (  # noqa: E402
    get_json_or_raise,
    post_json,
    require_platform_staging_env,
)

pytestmark = pytest.mark.live_platform


def test_live_staging_wallet_signing_and_guardrails():
    """API guardrails for Section 2. Full enroll/unlock needs browser WebAuthn."""
    base = require_platform_staging_env()
    wallet_id = "wallet_platform_" + secrets.token_hex(5)
    wallet_secret = "ab" * 32
    device_id = "dev_" + secrets.token_hex(4)
    session = requests.Session()
    origin = {"Origin": "https://lemma.id"}

    retired = session.post(
        f"{base}/api/wallet/init-first-session",
        json={"wallet_id": wallet_id},
        headers=origin,
        timeout=30,
    )
    assert retired.status_code == 410, retired.text
    assert get_json_or_raise(retired).get("error") == "first_session_route_retired"

    pubkey_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    reg = session.post(
        f"{base}/api/wallet/register-signing-key",
        json={
            "wallet_id": wallet_id,
            "device_id": device_id,
            "pubkey": pubkey_b64,
            "signature": sig_b64,
        },
        headers=origin,
        timeout=30,
    )
    assert reg.status_code == 403, reg.text
    assert get_json_or_raise(reg).get("code") == "first_device_webauthn_enrollment_required"

    begin = session.post(
        f"{base}/api/wallet/device-enroll/begin",
        json={"wallet_id": wallet_id, "device_id": device_id},
        headers=origin,
        timeout=30,
    )
    assert begin.status_code == 200, begin.text
    begin_data = get_json_or_raise(begin)
    assert begin_data.get("challenge_key")
    assert begin_data.get("challenge")

    unlock_begin = session.post(
        f"{base}/api/wallet/session-unlock/begin",
        json={
            "wallet_id": wallet_id,
            "device_id": device_id,
            "credential_id": "missing",
        },
        headers=origin,
        timeout=30,
    )
    assert unlock_begin.status_code == 403, unlock_begin.text

    status, data = post_json(
        session,
        base,
        "/api/wallet/lost-device-recovery/authorize",
        {"wallet_id": wallet_id, "session_id": "idv_missing"},
        headers=origin,
    )
    assert status == 403, data

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
