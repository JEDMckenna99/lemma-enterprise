#!/usr/bin/env python3
"""
Review AUTH_SCOPE_MATRIX_V1.json for high-risk policy gaps.

Fail conditions:
1) /api/admin/* routes without an explicit admin auth decorator.
2) State-changing /api/* routes without any explicit auth decorator,
   excluding known public bootstrap/auth endpoints.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "docs" / "AUTH_SCOPE_MATRIX_V1.json"

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ADMIN_AUTH_DECORATORS = {"require_admin", "require_site_admin"}
ANY_AUTH_DECORATORS = {
    "require_admin",
    "require_site_admin",
    "require_customer_or_admin",
    "require_wallet_ppid",
    "require_authenticated",
    "require_api_key",
    "require_agent_or_user_auth",
    "optional_auth",
}

# Known intentional public flows and preflight-compatible auth exchange paths.
PUBLIC_STATE_CHANGING_ALLOWLIST = {
    "/api/auth/exchange-proof",
    "/api/passkey/register/begin",
    "/api/passkey/register/complete",
    "/api/passkey/authenticate/begin",
    "/api/passkey/authenticate/complete",
    "/api/wallet/session-sync",
    "/api/wallet/sync",
}

# Bootstrap/legacy admin endpoints that use dedicated in-handler auth.
ADMIN_EXPLICIT_AUTH_ALLOWLIST = {
    "/api/admin/issue-admin-credential",
    "/api/admin/issue-admin-lemma",
    "/api/admin/reissue-with-ppid",
}


def _fmt(route: dict) -> str:
    methods = ",".join(route.get("methods", []))
    return f"{methods} {route.get('path')} ({route.get('module')}::{route.get('handler')})"


def main() -> int:
    strict_state_changing = os.getenv("LEMMA_SCOPE_POLICY_STRICT", "0").strip() in {"1", "true", "TRUE", "yes", "on"}
    if len(sys.argv) > 1 and sys.argv[1] == "--strict-state-changing":
        strict_state_changing = True

    if not MATRIX_PATH.exists():
        print(f"Missing matrix: {MATRIX_PATH}")
        return 2

    data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    routes = data.get("routes", [])

    admin_missing_explicit_auth = []
    state_changing_missing_auth = []

    for route in routes:
        path = str(route.get("path", ""))
        methods = {str(m).upper() for m in route.get("methods", [])}
        auth_decorators = set(route.get("auth_decorators") or [])

        if path.startswith("/api/admin/"):
            if path in ADMIN_EXPLICIT_AUTH_ALLOWLIST:
                continue
            if not (auth_decorators & ADMIN_AUTH_DECORATORS):
                admin_missing_explicit_auth.append(route)

        if not path.startswith("/api/"):
            continue
        if path in PUBLIC_STATE_CHANGING_ALLOWLIST:
            continue
        if not (methods & STATE_CHANGING_METHODS):
            continue
        if not (auth_decorators & ANY_AUTH_DECORATORS):
            state_changing_missing_auth.append(route)

    print(f"Scope matrix review: {len(routes)} routes scanned")
    print(f" - admin routes missing explicit admin auth: {len(admin_missing_explicit_auth)}")
    print(f" - state-changing routes missing explicit auth: {len(state_changing_missing_auth)}")

    if admin_missing_explicit_auth:
        print("\n[FAIL] Admin routes missing explicit admin auth:")
        for route in admin_missing_explicit_auth:
            print(f"  - {_fmt(route)}")

    if state_changing_missing_auth:
        level = "FAIL" if strict_state_changing else "WARN"
        print(f"\n[{level}] State-changing routes missing explicit auth:")
        for route in state_changing_missing_auth:
            print(f"  - {_fmt(route)}")

    if admin_missing_explicit_auth:
        return 1
    if strict_state_changing and state_changing_missing_auth:
        return 1

    print("Scope matrix review passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

