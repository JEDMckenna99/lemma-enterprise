"""Live Didit issue-flow (Phase 3.2).

Requires live env vars and a target deploy with Didit enabled:

    LEMMA_ISHUMAN_DIDIT_ENABLED=true DIDIT_API_KEY=... DIDIT_WORKFLOW_ID=...

Run with:  pytest -m live_didit tests/live/test_ishuman_live_didit_issue_flow.py
"""

from __future__ import annotations

import os
import time

import pytest
import requests

from tests.live.live_test_helpers import (
    derive_site_proof_with_assertion,
    get_json_or_raise,
    live_tests_strict,
    register_wallet_signing_key,
    require_live_didit_env,
    start_didit_verification,
)


@pytest.mark.live_didit
@pytest.mark.integration
def test_live_didit_start_routes_to_didit():
    """start-verification with provider=didit returns a didit hosted URL."""
    base_url, wallet_id, wallet_secret = require_live_didit_env()
    session = requests.Session()
    register_wallet_signing_key(session, base_url, wallet_id, wallet_secret)

    data = start_didit_verification(
        session,
        base_url=base_url,
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
    )

    assert data.get("success") is True, data
    assert data.get("provider") == "didit", data
    assert data.get("provider_session_id"), data
    assert data.get("url"), data
    assert "client_secret" not in data, data


@pytest.mark.live_didit
@pytest.mark.integration
def test_live_didit_issues_master_then_derives_site_proof():
    """Full didit issue flow: poll to verified, then derive a site proof."""
    base_url, wallet_id, wallet_secret = require_live_didit_env()
    target_site = os.getenv("ISHUMAN_LIVE_TARGET_SITE", "tickets-demo.lemma.id")
    timeout_seconds = int(os.getenv("ISHUMAN_LIVE_VERIFY_TIMEOUT_SECONDS", "300"))
    poll_interval_seconds = int(os.getenv("ISHUMAN_LIVE_VERIFY_POLL_SECONDS", "5"))
    session = requests.Session()
    register_wallet_signing_key(session, base_url, wallet_id, wallet_secret)

    start_data = start_didit_verification(
        session,
        base_url=base_url,
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
    )
    session_id = start_data["session_id"]
    didit_url = start_data.get("url")
    if didit_url:
        print(f"\nComplete Didit verification at: {didit_url}\n")

    master_credential_id = os.getenv("ISHUMAN_LIVE_MASTER_CREDENTIAL_ID", "").strip() or None
    deadline = time.time() + timeout_seconds
    while not master_credential_id and time.time() < deadline:
        status_resp = session.get(
            f"{base_url}/api/ishuman/verification-status/{session_id}",
            timeout=30,
        )
        status_data = get_json_or_raise(status_resp)
        assert status_resp.status_code == 200, status_data
        if status_data.get("status") == "verified" and status_data.get("credential_id"):
            master_credential_id = status_data["credential_id"]
            break
        if status_data.get("status") in ("failed", "declined", "expired"):
            pytest.fail(f"Didit verification reached terminal state: {status_data}")
        time.sleep(poll_interval_seconds)

    if not master_credential_id:
        message = (
            "Timed out waiting for live didit verification. Complete the didit "
            "hosted flow for the created session, then re-run."
        )
        if live_tests_strict():
            pytest.fail(message)
        pytest.skip(message)

    derive_data = derive_site_proof_with_assertion(
        session,
        base_url=base_url,
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        master_credential_id=master_credential_id,
        target_site=target_site,
    )
    assert derive_data.get("success") is True, derive_data
    claims = derive_data["credential"].get("claims") or derive_data["credential"].get(
        "credentialSubject"
    ) or {}
    assert claims.get("isHuman") is True, derive_data
    assert claims.get("siteId") == target_site.lower(), derive_data
