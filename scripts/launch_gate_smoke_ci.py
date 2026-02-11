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
import urllib.error
import urllib.request


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")


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


def main() -> int:
    print(f"Running launch-gate smoke checks against: {BASE_URL}")

    # Required availability and revocation data endpoints.
    get_endpoints = [
        f"{BASE_URL}/",
        f"{BASE_URL}/wallet/bridge",
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

    # Bridge header presence checks (values can evolve; presence is required).
    bridge_url = f"{BASE_URL}/wallet/bridge"
    status, _, headers = request(bridge_url, method="HEAD")
    print(f"HEAD {bridge_url} -> {status}")
    assert_true(status == 200, "Bridge HEAD endpoint is not healthy")
    required_headers = ["cache-control", "content-security-policy"]
    for name in required_headers:
        value = headers.get(name)
        print(f"  {name}={value}")
        assert_true(bool(value), f"Missing required header: {name}")

    # X-Frame-Options is optional when CSP frame-ancestors is enforced.
    xfo = headers.get("x-frame-options")
    print(f"  x-frame-options={xfo}")
    csp = headers.get("content-security-policy", "")
    assert_true(
        "frame-ancestors" in csp.lower(),
        "CSP frame-ancestors directive missing on bridge endpoint",
    )

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
    assert_true(
        register_status in (401, 403),
        f"Expected 401/403 for unauthenticated passkey register, got {register_status}",
    )

    authn_status, authn_content, _ = request(
        f"{BASE_URL}/api/passkey/authenticate/begin", method="POST", body=b"{}"
    )
    print(f"POST {BASE_URL}/api/passkey/authenticate/begin -> {authn_status}")
    assert_true(authn_status == 200, "Passkey authenticate begin did not return 200")
    authn_payload = json.loads(authn_content)
    assert_true(authn_payload.get("success") is True, "Passkey authenticate begin success != true")

    print("Launch-gate smoke checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Launch-gate smoke checks failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

