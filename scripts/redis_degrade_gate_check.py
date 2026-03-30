#!/usr/bin/env python3
"""
Redis degradation gate checks.

Confirms health endpoints return structured responses (not 500 crashes) even
when optional dependencies/backends are degraded.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")


def request(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url=url, method="GET")
    req.add_header("User-Agent", "lemma-redis-degrade-gate/1.0")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    print(f"Running Redis degrade gate checks against: {BASE_URL}")

    status, content = request(f"{BASE_URL}/api/health/check")
    print(f"GET /api/health/check -> {status}")
    assert_true(status in (200, 206, 503), f"Unexpected health/check status: {status}")
    payload = json.loads(content)
    assert_true("status" in payload, "health/check payload missing status")

    # Ensure we no longer surface raw 500 due to rate limiter/redis transient failures.
    assert_true(status != 500, "health/check returned 500 (degraded mode should prevent this)")

    status2, content2 = request(f"{BASE_URL}/api/health")
    print(f"GET /api/health -> {status2}")
    assert_true(status2 == 200, f"Expected /api/health 200, got {status2}")
    payload2 = json.loads(content2)
    assert_true(payload2.get("status") == "ok", "/api/health status should be ok")

    print("Redis degrade gate checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Redis degrade gate checks failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
