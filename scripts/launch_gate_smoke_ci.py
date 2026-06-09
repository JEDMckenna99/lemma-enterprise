#!/usr/bin/env python3
"""
Non-destructive launch gate smoke checks for Lemma.id production endpoints.

This script is intended for CI usage and performs read-only requests plus
expected-failure guardrail checks. It exits non-zero if required checks fail.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
MAX_ATTEMPTS = int(os.environ.get("LEMMA_SMOKE_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = int(os.environ.get("LEMMA_SMOKE_RETRY_BACKOFF", "15"))


def request(url: str, method: str = "GET", body: bytes | None = None) -> tuple[int, str, dict]:
    req = urllib.request.Request(url=url, method=method, data=body)
    req.add_header("User-Agent", "lemma-launch-gate-ci/1.0")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            content = resp.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return status, content, headers
    except urllib.error.HTTPError as err:
        content = err.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in err.headers.items()}
        return err.code, content, headers


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_checks() -> None:
    # Required availability and revocation data endpoints.
    get_endpoints = [
        f"{BASE_URL}/",
        f"{BASE_URL}/api/health",
        f"{BASE_URL}/api/revocation/bloom-filter",
        f"{BASE_URL}/api/v1/revocation/list",
    ]
    for url in get_endpoints:
        status, content, _ = request(url, method="GET")
        print(f"GET {url} -> {status}")
        assert_true(status == 200, f"Expected 200 for {url}, got {status}")

        if url.endswith("/bloom-filter") or url.endswith("/revocation/list"):
            payload = json.loads(content)
            assert_true(payload.get("success") is True, f"{url} success != true")
            print(f"  success={payload.get('success')} count={payload.get('count')}")
        elif url.endswith("/api/health"):
            payload = json.loads(content)
            assert_true(payload.get("status") == "ok", "/api/health status != ok")

    # Detailed health should be structured and never 500 due to transient backend issues.
    health_check_url = f"{BASE_URL}/api/health/check"
    health_status, health_content, _ = request(health_check_url, method="GET")
    print(f"GET {health_check_url} -> {health_status}")
    assert_true(
        health_status in (200, 206, 503),
        f"Expected 200/206/503 for health check, got {health_status}",
    )
    health_payload = json.loads(health_content)
    assert_true("status" in health_payload, "health/check payload missing status")

    # Phase 2.1: the /wallet/bridge iframe endpoint was removed; verification is
    # popup-only now, so there is no bridge header smoke check.

    # Expected-failure / guardrail checks with no auth context.
    no_session_status, _, _ = request(f"{BASE_URL}/api/wallet/session-sync", method="POST", body=b"{}")
    print(f"POST {BASE_URL}/api/wallet/session-sync -> {no_session_status}")
    assert_true(
        no_session_status in (401, 403),
        f"Expected 401/403 for unauthenticated session-sync, got {no_session_status}",
    )

    register_status, _, _ = request(
        f"{BASE_URL}/api/passkey/register/begin",
        method="POST",
        body=b'{"email":"launch-gate-check@lemma.id"}',
    )
    print(f"POST {BASE_URL}/api/passkey/register/begin -> {register_status}")
    # Rate limiting can return 429 before auth checks. This is still safe because
    # the unauthenticated caller is denied and does not receive registration state.
    assert_true(
        register_status in (401, 403, 429),
        f"Expected 401/403/429 for unauthenticated passkey register, got {register_status}",
    )

    authn_status, authn_content, _ = request(
        f"{BASE_URL}/api/passkey/authenticate/begin", method="POST", body=b"{}"
    )
    print(f"POST {BASE_URL}/api/passkey/authenticate/begin -> {authn_status}")
    assert_true(authn_status == 200, "Passkey authenticate begin did not return 200")
    authn_payload = json.loads(authn_content)
    assert_true(authn_payload.get("success") is True, "Passkey authenticate begin success != true")


def main() -> int:
    print(f"Running launch-gate smoke checks against: {BASE_URL}")

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if attempt > 1:
                print(f"Retry attempt {attempt}/{MAX_ATTEMPTS}")
            run_checks()
            print("Launch-gate smoke checks passed.")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed: {exc}", file=sys.stderr)
            if attempt < MAX_ATTEMPTS:
                print(f"Waiting {RETRY_BACKOFF_SECONDS}s before retry...")
                time.sleep(RETRY_BACKOFF_SECONDS)

    print(f"Launch-gate smoke checks failed after {MAX_ATTEMPTS} attempts: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

