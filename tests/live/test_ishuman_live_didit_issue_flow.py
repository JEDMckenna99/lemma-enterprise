"""Live didit sandbox issue-flow (Phase 3.2).

Mirrors test_ishuman_live_stripe_issue_flow.py for the didit rail. Skipped
unless the live env vars are set AND the target deploy has the didit rail
enabled. Drive these against a staging app with:

    LEMMA_ISHUMAN_DIDIT_ENABLED=true DIDIT_API_KEY=... DIDIT_WORKFLOW_ID=...

Run with:  pytest -m live_didit tests/live/test_ishuman_live_didit_issue_flow.py
"""

from __future__ import annotations

import os
import time

import pytest
import requests


REQUIRED_ENV = ("ISHUMAN_LIVE_BASE_URL", "ISHUMAN_LIVE_WALLET_ID")


def _require_live_env() -> tuple[str, str]:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        pytest.skip(
            "live_didit tests require env vars: "
            + ", ".join(REQUIRED_ENV)
            + ". Missing: "
            + ", ".join(missing)
        )
    return os.environ["ISHUMAN_LIVE_BASE_URL"].rstrip("/"), os.environ["ISHUMAN_LIVE_WALLET_ID"]


def _get_json_or_raise(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except Exception as exc:  # pragma: no cover - defensive path for live failures
        raise AssertionError(f"Expected JSON response, got status={resp.status_code}, body={resp.text}") from exc


@pytest.mark.live_didit
@pytest.mark.integration
def test_live_didit_start_routes_to_didit():
    """start-verification with provider=didit returns a didit hosted URL."""
    base_url, wallet_id = _require_live_env()
    wallet_secret = os.getenv("ISHUMAN_LIVE_WALLET_SECRET", "")

    resp = requests.post(
        f"{base_url}/api/ishuman/start-verification",
        json={
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "return_url": os.getenv("ISHUMAN_LIVE_RETURN_URL", f"{base_url}/app"),
            "provider": "didit",
        },
        timeout=30,
    )
    data = _get_json_or_raise(resp)

    if resp.status_code == 400 and data.get("error") == "didit_not_enabled":
        pytest.skip("Didit rail not enabled on the target deploy (set LEMMA_ISHUMAN_DIDIT_ENABLED + keys).")

    assert resp.status_code == 200, data
    assert data.get("success") is True, data
    assert data.get("provider") == "didit", data
    assert data.get("provider_session_id"), data
    assert data.get("url"), data
    # didit is a hosted redirect; no Stripe client_secret expected.
    assert "client_secret" not in data, data


@pytest.mark.live_didit
@pytest.mark.integration
def test_live_didit_issues_master_then_derives_site_proof():
    """Full didit issue flow: poll to verified, then derive a site proof.

    Requires a human (or didit sandbox auto-approve) to complete the hosted
    flow for the created session. Skips on timeout so CI stays green.
    """
    base_url, wallet_id = _require_live_env()
    wallet_secret = os.getenv("ISHUMAN_LIVE_WALLET_SECRET", "")
    target_site = os.getenv("ISHUMAN_LIVE_TARGET_SITE", "customer-live.example")
    timeout_seconds = int(os.getenv("ISHUMAN_LIVE_VERIFY_TIMEOUT_SECONDS", "300"))
    poll_interval_seconds = int(os.getenv("ISHUMAN_LIVE_VERIFY_POLL_SECONDS", "5"))

    start_resp = requests.post(
        f"{base_url}/api/ishuman/start-verification",
        json={
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "return_url": os.getenv("ISHUMAN_LIVE_RETURN_URL", f"{base_url}/app"),
            "provider": "didit",
        },
        timeout=30,
    )
    start_data = _get_json_or_raise(start_resp)
    if start_resp.status_code == 400 and start_data.get("error") == "didit_not_enabled":
        pytest.skip("Didit rail not enabled on the target deploy.")
    assert start_resp.status_code == 200, start_data
    session_id = start_data["session_id"]

    master_credential_id = None
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status_resp = requests.get(
            f"{base_url}/api/ishuman/verification-status/{session_id}",
            timeout=30,
        )
        status_data = _get_json_or_raise(status_resp)
        assert status_resp.status_code == 200, status_data
        if status_data.get("status") == "verified" and status_data.get("credential_id"):
            master_credential_id = status_data["credential_id"]
            break
        if status_data.get("status") in ("failed", "declined", "expired"):
            pytest.fail(f"Didit verification reached terminal state: {status_data}")
        time.sleep(poll_interval_seconds)

    if not master_credential_id:
        pytest.skip(
            "Timed out waiting for live didit verification. Complete the didit "
            "hosted flow for the created session, then re-run."
        )

    derive_resp = requests.post(
        f"{base_url}/api/ishuman/derive-site-proof",
        json={
            "master_credential_id": master_credential_id,
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "target_site": target_site,
        },
        timeout=30,
    )
    derive_data = _get_json_or_raise(derive_resp)
    assert derive_resp.status_code == 200, derive_data
    assert derive_data.get("success") is True, derive_data
    claims = derive_data["credential"].get("claims") or derive_data["credential"].get("credentialSubject") or {}
    assert claims.get("isHuman") is True, derive_data
    assert claims.get("siteId") == target_site.lower(), derive_data
