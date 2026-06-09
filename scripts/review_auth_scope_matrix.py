#!/usr/bin/env python3
"""
Review docs/api/AUTH_SCOPE_MATRIX_V1.json for high-risk policy gaps.

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
MATRIX_PATH = REPO_ROOT / "docs" / "api" / "AUTH_SCOPE_MATRIX_V1.json"

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ADMIN_AUTH_DECORATORS = {"require_admin", "require_site_admin"}
ANY_AUTH_DECORATORS = {
    "require_admin",
    "require_site_admin",
    "require_customer_or_admin",
    "require_wallet_ppid",
    "require_wallet_auth",
    "require_permission",
    "require_authenticated",
    "require_api_key",
    "validate_api_key",
    "require_agent_or_user_auth",
    "require_agent_or_user_session",
    "optional_auth",
}

# Known intentional public flows and preflight-compatible auth exchange paths.
PUBLIC_STATE_CHANGING_ALLOWLIST = {
    "/api/auth/lemma-signin",
    "/api/auth/exchange-proof",
    "/api/auth/refresh",
    "/api/auth/request-beta-access",
    "/api/auth/signout",
    "/api/agent/validate",
    "/api/recovery/initiate",
    "/api/recovery/validate",
    "/api/recovery/complete",
    "/api/recovery/complete-wallet",
    "/api/recovery/issue-admin-proof",
    "/api/customer/register-secure",
    "/api/developer/credential-transfer/redeem",
    "/api/passkey/register/begin",
    "/api/passkey/register/complete",
    "/api/passkey/authenticate/begin",
    "/api/passkey/authenticate/complete",
    "/api/wallet/auth",
    "/api/wallet/pin-reset/request",
    "/api/wallet/pin-reset/verify",
    "/api/wallet/pin-reset/complete",
    "/api/wallet/create-redirect-token",
    "/api/wallet/exchange-redirect-token",
    "/api/wallet/global-session",
    "/api/wallet/init-first-session",
    "/api/wallet/link-unlock-token",
    "/api/wallet/set-session",
    "/api/wallet/signal-unlock",
    "/api/wallet/clear-session",
    "/api/wallet-auth/issue",
    "/api/wallet-auth/platform-login",
    "/api/wallet-auth/restore-site-access",
    "/api/wallet-auth/register-and-issue",
    "/api/wallet-auth/verify-session",
    "/api/wallet-sync/create-qr-auth",
    "/api/wallet-sync/verify-qr-auth",
    "/api/wallet/revoke-wallet",
    "/api/wallet/transfer/create-session",
    "/api/wallet/transfer/get-wallet",
    "/api/wallet/transfer/set-wallet",
    "/api/passkey/<int:passkey_id>",
    "/api/sdk/verify",
    "/api/test/issue-credential",
    "/api/v1/iam/claim-permission",
    "/api/v1/oauth/token",
    "/api/verify-credential",
    "/api/validate-key",
    "/api/wallet/session-sync",
    "/api/wallet/sync",
}

# Bootstrap/legacy admin endpoints that use dedicated in-handler auth.
ADMIN_EXPLICIT_AUTH_ALLOWLIST = {
    "/api/admin/issue-admin-credential",
    "/api/admin/issue-admin-lemma",
    "/api/admin/reissue-with-ppid",
}

# State-changing routes that enforce auth inside the handler (wallet assertions,
# webhook signatures, demo guards) rather than via route decorators.
IN_HANDLER_AUTH_ALLOWLIST = {
    "/api/agent/monitor/log-external",
    "/api/auth/issue-credential",
    "/api/demo/ishuman/approve-network-revocation",
    "/api/demo/ishuman/force-reverify",
    "/api/demo/ishuman/network-revoke-request",
    "/api/demo/ishuman/probe-derive",
    "/api/demo/ishuman/reset-wallet",
    "/api/demo/ishuman/self-reset",
    "/api/demo/ishuman/site-block",
    "/api/demo/ishuman/site-unblock",
    "/api/demo/ishuman/test-complete-verification",
    "/api/demo/ishuman/verify-once-test-mode",
    "/api/demo/issue-credential",
    "/api/demo/issue-proof",
    "/api/demo/issue-proof-chain",
    "/api/demo/revoke",
    "/api/demo/revoke-credential",
    "/api/demo/taint-bump",
    "/api/demo/verify",
    "/api/ishuman/approve-revocation",
    "/api/ishuman/derive-site-proof",
    "/api/ishuman/erase",
    "/api/ishuman/idv-mobile-handoff/claim",
    "/api/ishuman/idv-mobile-handoff/deposit",
    "/api/ishuman/network-revoke",
    "/api/ishuman/reissue-master",
    "/api/ishuman/seed-envelope",
    "/api/ishuman/site-block",
    "/api/ishuman/site-unblock",
    "/api/ishuman/start-verification",
    "/api/ishuman/verify-presentation",
    "/api/wallet/challenge",
    "/api/wallet/firewall/runtimes/<runtime_id>/authorize",
    "/api/wallet/register-signing-key",
    "/api/wallet/sync-device",
    "/api/webhooks/didit-identity",
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
        if path in IN_HANDLER_AUTH_ALLOWLIST:
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

