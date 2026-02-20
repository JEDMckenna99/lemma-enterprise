#!/usr/bin/env python3
"""
Scope matrix checks for server-enforced controlled actions.

This script is intended for CI/post-deploy verification and validates:
- read-allowed token can access read endpoint
- non-admin token is forbidden on admin endpoint
- admin token can access admin endpoint
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
PLATFORM_API_KEY = os.environ.get("LEMMA_PLATFORM_API_KEY", "").strip()


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    req_headers = {"User-Agent": "lemma-auth-scope-matrix/1.0"}
    if headers:
        req_headers.update(headers)

    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, data=payload, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _parse_json(content: str) -> dict[str, Any]:
    if not content:
        return {}
    return json.loads(content)


def _issue_lemma(permission_level: str, email: str) -> dict[str, Any]:
    status, content = _request(
        f"{BASE_URL}/api/platform/issue-site-permission",
        method="POST",
        body={
            "site_id": "lemma.id",
            "user_email": email,
            "permission_level": permission_level,
            "expiry_days": 7,
        },
        headers={"X-API-Key": PLATFORM_API_KEY},
    )
    _assert(status == 200, f"Expected 200 from issue-site-permission, got {status}")
    payload = _parse_json(content)
    _assert(payload.get("success") is True, "issue-site-permission success != true")
    lemma = payload.get("permission_lemma")
    _assert(isinstance(lemma, dict), "permission_lemma missing")
    return lemma


def _exchange(lemma: dict[str, Any]) -> str:
    status, content = _request(
        f"{BASE_URL}/api/auth/exchange-proof",
        method="POST",
        body={"credential": lemma, "site_id": "lemma.id"},
    )
    _assert(status == 200, f"Expected 200 from exchange-proof, got {status}")
    payload = _parse_json(content)
    token = payload.get("access_token", "")
    _assert(token.startswith("lm_at_"), "exchange-proof did not return lm_at_ token")
    return token


def main() -> int:
    if not PLATFORM_API_KEY:
        raise AssertionError("LEMMA_PLATFORM_API_KEY is required for scope matrix checks")

    ts = int(time.time())
    user_email = f"scope-user-{ts}@lemma.id"
    admin_email = f"scope-admin-{ts}@lemma.id"

    user_lemma = _issue_lemma("user", user_email)
    admin_lemma = _issue_lemma("admin", admin_email)

    user_token = _exchange(user_lemma)
    admin_token = _exchange(admin_lemma)

    # Read endpoint should work for user token
    status, _ = _request(
        f"{BASE_URL}/api/billing/usage/cus_test",
        method="GET",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    print(f"user_token -> GET /api/billing/usage/cus_test => {status}")
    _assert(status == 200, f"Expected 200 for user token on read endpoint, got {status}")

    # Admin endpoint should reject user token
    status, _ = _request(
        f"{BASE_URL}/api/admin/platform-stats",
        method="GET",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    print(f"user_token -> GET /api/admin/platform-stats => {status}")
    _assert(status == 403, f"Expected 403 for user token on admin endpoint, got {status}")

    # Admin endpoint should allow admin token
    status, _ = _request(
        f"{BASE_URL}/api/admin/platform-stats",
        method="GET",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print(f"admin_token -> GET /api/admin/platform-stats => {status}")
    _assert(status == 200, f"Expected 200 for admin token on admin endpoint, got {status}")

    print("Auth scope matrix checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Auth scope matrix checks failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

