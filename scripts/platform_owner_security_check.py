#!/usr/bin/env python3
"""Non-destructive prod checks for lemma.id platform-owner + signed-permission auth."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
FAKE_PPID = "did:lemma:ppid_" + ("b" * 64)


def request(url: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=data)
    req.add_header("User-Agent", "lemma-platform-owner-security-check/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        status = err.code
    else:
        status = resp.getcode()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw
    return status, payload


class Check:
    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.detail = ""

    def pass_(self, detail: str = "") -> None:
        self.ok = True
        self.detail = detail

    def fail(self, detail: str) -> None:
        self.ok = False
        self.detail = detail


def main() -> int:
    checks: list[Check] = []

    # 1) Bootstrap page reachable
    c = Check("Admin bootstrap page loads")
    status, _ = request(f"{BASE_URL}/admin/bootstrap")
    if status == 200:
        c.pass_(f"HTTP {status}")
    else:
        c.fail(f"Expected 200, got {status}")
    checks.append(c)

    # 2) Protected admin API requires signed credential
    c = Check("Admin API rejects unauthenticated calls")
    status, payload = request(f"{BASE_URL}/api/admin/platform-stats")
    if status == 401 and isinstance(payload, dict) and payload.get("error") == "auth_required":
        c.pass_("401 auth_required without X-Lemma-Credential")
    elif status in (401, 403):
        c.pass_(f"HTTP {status} (credential required)")
    else:
        c.fail(f"Expected 401 auth_required, got {status} {payload!r}")
    checks.append(c)

    # 3) Bootstrap status endpoint responds (owner config probe)
    c = Check("Platform bootstrap status endpoint")
    status, payload = request(
        f"{BASE_URL}/api/v1/iam/admin/platform-bootstrap/status",
        method="POST",
        body={"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    if status == 200 and isinstance(payload, dict) and payload.get("success") is True:
        owner_cfg = payload.get("owner_configured")
        c.pass_(
            f"owner_configured={owner_cfg}, "
            f"is_platform_owner={payload.get('is_platform_owner')}"
        )
    else:
        c.fail(f"Unexpected response: {status} {payload!r}")
    checks.append(c)

    owner_configured = (
        checks[-1].ok
        and isinstance(checks[-1].detail, str)
        and "owner_configured=True" in checks[-1].detail
    )

    # 4) Auto-issue denies non-owner when owner gate is configured
    c = Check("Auto-bootstrap denies non-owner PPID")
    status, payload = request(
        f"{BASE_URL}/api/v1/iam/admin/platform-bootstrap/auto-issue",
        method="POST",
        body={"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    if not owner_configured:
        if status in (403, 503) and isinstance(payload, dict):
            c.pass_(f"Gate inactive or blocked: {payload.get('error')}")
        else:
            c.fail(f"Owner not configured; expected 403/503, got {status}")
    elif status == 403 and isinstance(payload, dict) and payload.get("error") in {
        "platform_owner_required",
        "person_root_required",
        "ppid_mismatch",
    }:
        c.pass_(f"403 {payload.get('error')}")
    else:
        c.fail(f"Expected 403 for fake PPID, got {status} {payload!r}")
    checks.append(c)

    # 5) Platform login fails closed for unbound/fake wallet
    c = Check("Platform login denies unbound/fake wallet")
    status, payload = request(
        f"{BASE_URL}/api/wallet-auth/platform-login",
        method="POST",
        body={"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    if status == 403 and isinstance(payload, dict) and payload.get("error") in {
        "person_root_required",
        "wallet_id_required",
        "platform_membership_required",
        "ppid_mismatch",
    }:
        c.pass_(f"403 {payload.get('error')}")
    else:
        c.fail(f"Expected fail-closed 403, got {status} {payload!r}")
    checks.append(c)

    # 6) Revocation data available for local VC verify
    c = Check("Revocation list available for wallet verify")
    status, payload = request(f"{BASE_URL}/api/v1/revocation/list")
    if status == 200 and isinstance(payload, dict) and payload.get("success") is True:
        c.pass_(f"count={payload.get('count')}")
    else:
        c.fail(f"Expected revocation list 200, got {status}")
    checks.append(c)

    print(f"Platform owner security checks, {BASE_URL}\n")
    failed = 0
    for item in checks:
        mark = "PASS" if item.ok else "FAIL"
        print(f"  [{mark}] {item.name}")
        if item.detail:
            print(f"         {item.detail}")
        if not item.ok:
            failed += 1

    print()
    if owner_configured:
        print("Server: LEMMA_PLATFORM_OWNER_PPID appears configured.")
    else:
        print("Server: LEMMA_PLATFORM_OWNER_PPID not configured (owner gate inactive).")

    print()
    print("Browser checks (unlock wallet on lemma.id, paste in DevTools console):")
    print("  1) PPID:  const p = await globalLemmaWallet.derivePPID('lemma.id'); console.log(p);")
    print("  2) Perms: const v = await globalLemmaWallet.getVerifiedPermissions('lemma.id'); console.log(v);")
    print("  3) Admin:  v.role should be admin; v.permissionId should include admin_access")
    print("  4) API:    fetch('/api/admin/platform-stats', {headers: await getLemmaAuthHeadersAsync()}).then(r=>r.json()).then(console.log)")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
