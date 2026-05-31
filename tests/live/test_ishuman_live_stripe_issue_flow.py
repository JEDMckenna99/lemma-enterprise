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
            "live_stripe tests require env vars: "
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


@pytest.fixture(scope="module", name="live_master_credential_id")
def fixture_live_master_credential_id() -> str:
    explicit_master_id = os.getenv("ISHUMAN_LIVE_MASTER_CREDENTIAL_ID")
    if explicit_master_id:
        return explicit_master_id

    base_url, wallet_id = _require_live_env()
    wallet_secret = os.getenv("ISHUMAN_LIVE_WALLET_SECRET", "")
    timeout_seconds = int(os.getenv("ISHUMAN_LIVE_VERIFY_TIMEOUT_SECONDS", "300"))
    poll_interval_seconds = int(os.getenv("ISHUMAN_LIVE_VERIFY_POLL_SECONDS", "5"))

    start_resp = requests.post(
        f"{base_url}/api/ishuman/start-verification",
        json={
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "return_url": os.getenv("ISHUMAN_LIVE_RETURN_URL", f"{base_url}/app"),
        },
        timeout=30,
    )
    start_data = _get_json_or_raise(start_resp)
    assert start_resp.status_code == 200, start_data
    assert start_data.get("success") is True, start_data
    assert start_data.get("session_id"), start_data
    assert start_data.get("stripe_session_id"), start_data
    assert start_data.get("client_secret"), start_data

    session_id = start_data["session_id"]
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status_resp = requests.get(
            f"{base_url}/api/ishuman/verification-status/{session_id}",
            timeout=30,
        )
        status_data = _get_json_or_raise(status_resp)
        assert status_resp.status_code == 200, status_data
        if status_data.get("status") == "verified" and status_data.get("credential_id"):
            return status_data["credential_id"]
        time.sleep(poll_interval_seconds)

    pytest.skip(
        "Timed out waiting for live Stripe verification to reach verified state. "
        "Complete the Stripe Identity flow for the created session, or set "
        "ISHUMAN_LIVE_MASTER_CREDENTIAL_ID to an existing verified master credential."
    )


@pytest.mark.live_stripe
@pytest.mark.integration
def test_live_stripe_derives_site_specific_proof(live_master_credential_id):
    base_url, wallet_id = _require_live_env()
    target_site = os.getenv("ISHUMAN_LIVE_TARGET_SITE", "customer-live.example")
    wallet_secret = os.getenv("ISHUMAN_LIVE_WALLET_SECRET", "")

    derive_resp = requests.post(
        f"{base_url}/api/ishuman/derive-site-proof",
        json={
            "master_credential_id": live_master_credential_id,
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "target_site": target_site,
        },
        timeout=30,
    )
    derive_data = _get_json_or_raise(derive_resp)

    assert derive_resp.status_code == 200, derive_data
    assert derive_data.get("success") is True, derive_data
    assert derive_data.get("credential"), derive_data
    assert derive_data["credential"].get("id"), derive_data
    claims = derive_data["credential"].get("claims") or derive_data["credential"].get("credentialSubject") or {}
    assert claims.get("isHuman") is True, derive_data
    assert claims.get("siteId") == target_site.lower(), derive_data
