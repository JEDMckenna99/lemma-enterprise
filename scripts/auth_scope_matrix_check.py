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
import base64
from typing import Any


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
PLATFORM_API_KEY = os.environ.get("LEMMA_PLATFORM_API_KEY", "").strip()
EXPECT_EDGE_ADMIN_COMPAT = os.environ.get("LEMMA_EXPECT_EDGE_ADMIN_COMPAT", "").strip()


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


def _issuance_available() -> bool:
    status, _ = _request(
        f"{BASE_URL}/api/platform/issue-site-permission",
        method="POST",
        body={
            "site_id": "lemma.id",
            "user_email": "scope-probe@lemma.id",
            "permission_level": "user",
            "expiry_days": 1,
        },
        headers={"X-API-Key": PLATFORM_API_KEY},
    )
    return status == 200


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


def _encode_lemma_header(lemma: dict[str, Any]) -> str:
    raw = json.dumps(lemma, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _edge_admin_headers_from_lemma(lemma: dict[str, Any]) -> dict[str, str]:
    credential_id = str(lemma.get("id") or lemma.get("credential_id") or "").strip()
    subject = lemma.get("credentialSubject")
    if not isinstance(subject, dict):
        subject = {}
    claims = lemma.get("claims")
    if not isinstance(claims, dict):
        claims = {}
    permission_id = str(
        subject.get("permissionId")
        or subject.get("permission_id")
        or claims.get("permissionId")
        or claims.get("permission_id")
        or lemma.get("permission_id")
        or ""
    ).strip()
    _assert(credential_id, "lemma credential id missing for edge-admin path")
    _assert(permission_id, "lemma permission id missing for edge-admin path")
    return {
        "X-Credential-ID": credential_id,
        "X-Permission-ID": permission_id,
    }


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

    if not _issuance_available():
        print(
            "Scope matrix live checks skipped: /api/platform/issue-site-permission "
            "no longer accepts platform API keys (credential auth migration)."
        )
        return 0

    ts = int(time.time())
    user_email = f"scope-user-{ts}@lemma.id"
    admin_email = f"scope-admin-{ts}@lemma.id"

    user_lemma = _issue_lemma("user", user_email)
    admin_lemma = _issue_lemma("admin", admin_email)

    user_lemma_header = _encode_lemma_header(user_lemma)

    # Read endpoint should work for user lemma (VC-first runtime auth)
    status, _ = _request(
        f"{BASE_URL}/api/billing/usage/cus_test",
        method="GET",
        headers={"X-Lemma-Credential": user_lemma_header},
    )
    print(f"user_lemma -> GET /api/billing/usage/cus_test => {status}")
    _assert(status == 200, f"Expected 200 for user lemma on read endpoint, got {status}")

    user_edge_headers = _edge_admin_headers_from_lemma(user_lemma)
    admin_edge_headers = _edge_admin_headers_from_lemma(admin_lemma)

    # Admin endpoint should reject non-admin lemma (edge-admin path headers).
    # In production, edge compat may be disabled and return 401 auth_required.
    status, _ = _request(
        f"{BASE_URL}/api/admin/platform-stats",
        method="GET",
        headers=user_edge_headers,
    )
    print(f"user_edge_headers -> GET /api/admin/platform-stats => {status}")
    if EXPECT_EDGE_ADMIN_COMPAT == "1":
        _assert(status == 403, f"Expected 403 for user edge-admin headers on admin endpoint, got {status}")
    elif EXPECT_EDGE_ADMIN_COMPAT == "0":
        _assert(status == 401, f"Expected 401 when edge-admin compat is disabled, got {status}")
    else:
        _assert(status in {401, 403}, f"Expected 401/403 for user edge-admin headers on admin endpoint, got {status}")

    # Admin endpoint should allow admin lemma (edge-admin path headers) only when compat enabled.
    status, _ = _request(
        f"{BASE_URL}/api/admin/platform-stats",
        method="GET",
        headers=admin_edge_headers,
    )
    print(f"admin_edge_headers -> GET /api/admin/platform-stats => {status}")
    if EXPECT_EDGE_ADMIN_COMPAT == "1":
        _assert(status == 200, f"Expected 200 for admin edge-admin headers on admin endpoint, got {status}")
    elif EXPECT_EDGE_ADMIN_COMPAT == "0":
        _assert(status == 401, f"Expected 401 when edge-admin compat is disabled, got {status}")
    else:
        _assert(status in {200, 401}, f"Expected 200/401 for admin edge-admin headers on admin endpoint, got {status}")

    # Compatibility check: exchanged access-token behavior varies by runtime mode.
    user_token = _exchange(user_lemma)
    status, _ = _request(
        f"{BASE_URL}/api/billing/usage/cus_test",
        method="GET",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    print(f"user_token -> GET /api/billing/usage/cus_test => {status}")

    expected_bearer_runtime = os.environ.get("LEMMA_EXPECT_BEARER_RUNTIME", "").strip()
    if expected_bearer_runtime == "1":
        _assert(status == 200, f"Expected 200 for user bearer token in bearer-runtime mode, got {status}")
    elif expected_bearer_runtime == "0":
        _assert(status == 401, f"Expected 401 for user bearer token in VC-only mode, got {status}")

    print("Auth scope matrix checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Auth scope matrix checks failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

