#!/usr/bin/env python3
"""
Non-destructive production platform smoke checks for lemma.id.

Consolidates launch-gate availability/guardrail checks with platform-owner
auth fail-closed probes. Safe for CI (read-only + expected-failure guardrails).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

FAKE_PPID = "did:lemma:ppid_" + ("b" * 64)
USER_AGENT = "lemma-platform-prod-smoke/1.0"


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail


def _base_url() -> str:
    return os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")


def _request(
    base: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> tuple[int, dict | str]:
    url = f"{base}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=data)
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.getcode()
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        status = err.code
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw
    return status, payload


def run_platform_smoke_checks(base: str | None = None) -> list[CheckResult]:
    base = (base or _base_url()).rstrip("/")
    results: list[CheckResult] = []

    for path in ("/", "/api/health", "/api/revocation/bloom-filter", "/api/v1/revocation/list"):
        status, payload = _request(base, path)
        if path == "/":
            ok = status == 200
            detail = f"HTTP {status}"
        elif path == "/api/health":
            ok = status == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
            detail = f"HTTP {status}"
        elif path.endswith("/bloom-filter") or path.endswith("/revocation/list"):
            ok = status == 200 and isinstance(payload, dict) and payload.get("success") is True
            detail = f"HTTP {status}"
            if isinstance(payload, dict) and payload.get("count") is not None:
                detail += f" count={payload.get('count')}"
        else:
            ok = status == 200
            detail = f"HTTP {status}"
        results.append(CheckResult(f"GET {path}", ok, detail))

    status, payload = _request(base, "/api/health/check")
    ok = status in (200, 206, 503) and isinstance(payload, dict) and "status" in payload
    results.append(CheckResult("GET /api/health/check", ok, f"HTTP {status}"))

    status, _ = _request(base, "/api/wallet/session-sync", method="POST", body={})
    ok = status in (401, 403)
    results.append(CheckResult("POST /api/wallet/session-sync unauthenticated", ok, f"HTTP {status}"))

    status, _ = _request(
        base,
        "/api/passkey/register/begin",
        method="POST",
        body={"email": "launch-gate-check@lemma.id"},
    )
    ok = status in (401, 403, 429)
    results.append(CheckResult("POST /api/passkey/register/begin unauthenticated", ok, f"HTTP {status}"))

    status, payload = _request(base, "/api/passkey/authenticate/begin", method="POST", body={})
    ok = status == 200 and isinstance(payload, dict) and payload.get("success") is True
    results.append(CheckResult("POST /api/passkey/authenticate/begin", ok, f"HTTP {status}"))

    status, _ = _request(base, "/admin/bootstrap")
    results.append(CheckResult("GET /admin/bootstrap", status == 200, f"HTTP {status}"))

    status, payload = _request(base, "/api/admin/platform-stats")
    ok = status in (401, 403)
    if status == 401 and isinstance(payload, dict):
        ok = payload.get("error") == "auth_required"
    results.append(CheckResult("GET /api/admin/platform-stats unauthenticated", ok, f"HTTP {status}"))

    status, payload = _request(
        base,
        "/api/v1/iam/admin/platform-bootstrap/status",
        method="POST",
        body={"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    ok = status == 200 and isinstance(payload, dict) and payload.get("success") is True
    owner_detail = ""
    if ok:
        owner_detail = (
            f"owner_configured={payload.get('owner_configured')}, "
            f"is_platform_owner={payload.get('is_platform_owner')}"
        )
    results.append(CheckResult("POST platform-bootstrap/status", ok, owner_detail or f"HTTP {status}"))

    owner_configured = ok and payload.get("owner_configured") is True

    status, payload = _request(
        base,
        "/api/v1/iam/admin/platform-bootstrap/auto-issue",
        method="POST",
        body={"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    if not owner_configured:
        auto_ok = status in (403, 503) and isinstance(payload, dict)
    else:
        auto_ok = status == 403 and isinstance(payload, dict) and payload.get("error") in {
            "platform_owner_required",
            "person_root_required",
            "ppid_mismatch",
        }
    results.append(CheckResult("POST platform-bootstrap/auto-issue fake PPID", auto_ok, f"HTTP {status}"))

    status, payload = _request(
        base,
        "/api/wallet-auth/platform-login",
        method="POST",
        body={"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    login_ok = status == 403 and isinstance(payload, dict) and payload.get("error") in {
        "person_root_required",
        "wallet_id_required",
        "platform_membership_required",
        "ppid_mismatch",
    }
    results.append(CheckResult("POST platform-login fake wallet", login_ok, f"HTTP {status}"))

    for path in ("/login", "/register", "/docs", "/sdk/ishuman-verifier.js"):
        status, _ = _request(base, path)
        results.append(CheckResult(f"GET {path}", status == 200, f"HTTP {status}"))

    status, _ = _request(base, "/docs/operations/INTERNAL_COGS_ESTIMATE.md")
    results.append(
        CheckResult("GET internal docs blocked", status in (403, 404), f"HTTP {status}")
    )

    return results


def main() -> int:
    base = _base_url()
    max_attempts = int(os.environ.get("LEMMA_SMOKE_MAX_ATTEMPTS", "3"))
    retry_backoff = int(os.environ.get("LEMMA_SMOKE_RETRY_BACKOFF", "15"))

    print(f"Running platform prod smoke against: {base}")
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            if attempt > 1:
                print(f"Retry attempt {attempt}/{max_attempts}")
            results = run_platform_smoke_checks(base)
            failed = [item for item in results if not item.ok]
            for item in results:
                mark = "PASS" if item.ok else "FAIL"
                line = f"[{mark}] {item.name}"
                if item.detail:
                    line += f": {item.detail}"
                print(line)
            if failed:
                raise RuntimeError(f"{len(failed)} check(s) failed")
            print("\nPlatform prod smoke passed.")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{max_attempts} failed: {exc}", file=sys.stderr)
            if attempt < max_attempts:
                print(f"Waiting {retry_backoff}s before retry...")
                time.sleep(retry_backoff)

    print(f"Platform prod smoke failed after {max_attempts} attempts: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
