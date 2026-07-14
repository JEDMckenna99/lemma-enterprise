"""Shared helpers for live/staging isHuman integration tests."""

from __future__ import annotations

import os
from typing import Iterable

import pytest
import requests

from api.wallet_keys import build_wallet_assertion, register_self_signature


def live_tests_strict() -> bool:
    """When true, missing config or timeouts fail instead of skipping."""
    return os.getenv("ISHUMAN_LIVE_STRICT", os.getenv("LEMMA_LIVE_TESTS_STRICT", "")).strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


def staging_tests_strict() -> bool:
    return os.getenv("LEMMA_STAGING_STRICT", os.getenv("LEMMA_LIVE_TESTS_STRICT", "")).strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_env_vars(names: Iterable[str], *, strict: bool, context: str) -> None:
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if not missing:
        return
    message = f"{context} requires env vars: {', '.join(names)}. Missing: {', '.join(missing)}"
    if strict:
        pytest.fail(message)
    pytest.skip(message)


def require_staging_env() -> tuple[str, str]:
    require_env_vars(
        ("LEMMA_STAGING_BASE_URL", "LEMMA_STAGING_DEMO_TEST_TOKEN"),
        strict=staging_tests_strict(),
        context="staging live tests",
    )
    return (
        os.environ["LEMMA_STAGING_BASE_URL"].rstrip("/"),
        os.environ["LEMMA_STAGING_DEMO_TEST_TOKEN"],
    )


def require_live_didit_env() -> tuple[str, str, str]:
    require_env_vars(
        ("ISHUMAN_LIVE_BASE_URL", "ISHUMAN_LIVE_WALLET_ID", "ISHUMAN_LIVE_WALLET_SECRET"),
        strict=live_tests_strict(),
        context="live Didit tests",
    )
    return (
        os.environ["ISHUMAN_LIVE_BASE_URL"].rstrip("/"),
        os.environ["ISHUMAN_LIVE_WALLET_ID"],
        os.environ["ISHUMAN_LIVE_WALLET_SECRET"],
    )


def get_json_or_raise(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except Exception as exc:  # pragma: no cover - defensive path for live failures
        raise AssertionError(
            f"Expected JSON response, got status={resp.status_code}, body={resp.text}"
        ) from exc


def wallet_challenge(session: requests.Session, base_url: str, wallet_id: str) -> str:
    resp = session.post(
        f"{base_url}/api/wallet/challenge",
        json={"wallet_id": wallet_id},
        timeout=30,
    )
    data = get_json_or_raise(resp)
    assert resp.status_code == 200, data
    nonce = data.get("nonce")
    assert nonce, data
    return nonce


def register_wallet_signing_key(
    session: requests.Session,
    base_url: str,
    wallet_id: str,
    wallet_secret: str,
) -> None:
    pubkey_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    resp = session.post(
        f"{base_url}/api/wallet/register-signing-key",
        json={"wallet_id": wallet_id, "pubkey": pubkey_b64, "signature": sig_b64},
        timeout=30,
    )
    data = get_json_or_raise(resp)
    if resp.status_code not in (200, 403):
        raise AssertionError(f"register-signing-key failed: HTTP {resp.status_code} {data}")
    if resp.status_code == 200:
        assert data.get("success"), data


def build_assertion_payload(
    *,
    wallet_id: str,
    wallet_secret: str,
    field_names: list[str],
    field_values: dict[str, str],
    nonce_b64: str,
) -> dict[str, str]:
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=field_names,
        field_values=field_values,
        nonce_b64=nonce_b64,
    )
    return {"nonce": assertion.nonce, "signature": assertion.signature}


def start_didit_verification(
    session: requests.Session,
    *,
    base_url: str,
    wallet_id: str,
    wallet_secret: str,
    return_url: str | None = None,
) -> dict:
    return_url = return_url or os.getenv("ISHUMAN_LIVE_RETURN_URL", f"{base_url}/app")
    field_values = {"return_url": return_url}
    assertion = build_assertion_payload(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=["return_url"],
        field_values=field_values,
        nonce_b64=wallet_challenge(session, base_url, wallet_id),
    )
    resp = session.post(
        f"{base_url}/api/ishuman/start-verification",
        json={
            "wallet_id": wallet_id,
            "return_url": return_url,
            "provider": "didit",
            "wallet_assertion": assertion,
        },
        timeout=30,
    )
    data = get_json_or_raise(resp)
    if resp.status_code == 400 and data.get("error") == "didit_not_enabled":
        if os.getenv("ISHUMAN_LIVE_REQUIRE_DIDIT_ENABLED") == "1" or live_tests_strict():
            pytest.fail("Didit rail is not enabled on the strict live smoke target.")
        pytest.skip("Didit rail not enabled on the target deploy.")
    assert resp.status_code == 200, data
    return data


def derive_site_proof_with_assertion(
    session: requests.Session,
    *,
    base_url: str,
    wallet_id: str,
    wallet_secret: str,
    master_credential_id: str,
    target_site: str,
    site_signing_pubkey: str | None = None,
) -> dict:
    body: dict = {
        "wallet_id": wallet_id,
        "master_credential_id": master_credential_id,
        "target_site": target_site,
        "issue_mode": "site_proof",
    }
    if site_signing_pubkey:
        body["site_signing_pubkey"] = site_signing_pubkey
    field_names = ["master_credential_id", "target_site", "issue_mode"]
    if site_signing_pubkey:
        field_names.insert(2, "site_signing_pubkey")
    field_values = {key: str(body.get(key) or "") for key in field_names}
    body["wallet_assertion"] = build_assertion_payload(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=field_names,
        field_values=field_values,
        nonce_b64=wallet_challenge(session, base_url, wallet_id),
    )
    resp = session.post(f"{base_url}/api/ishuman/derive-site-proof", json=body, timeout=30)
    data = get_json_or_raise(resp)
    assert resp.status_code == 200, data
    return data
