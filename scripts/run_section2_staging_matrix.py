#!/usr/bin/env python3
"""API-level Section 2 wallet-authority matrix against staging.

Usage:
  export LEMMA_STAGING_BASE_URL=https://<staging-app>.herokuapp.com
  python scripts/run_section2_staging_matrix.py

Optional:
  LEMMA_STAGING_ORIGIN=https://lemma.id   # Origin header for lemma-bound routes
  LEMMA_DEPLOY_WAIT=1                    # wait for /api/health first

This script does not exercise real WebAuthn create/get ceremonies. Pair it with
docs/status/SECTION2_STAGING_BROWSER_MATRIX.md after deploy.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.error
import urllib.request

from api.wallet_keys import register_self_signature


def _base() -> str:
    base = (os.environ.get("LEMMA_STAGING_BASE_URL") or "").rstrip("/")
    if not base:
        print("LEMMA_STAGING_BASE_URL is required", file=sys.stderr)
        sys.exit(2)
    return base


def _origin() -> str:
    return (os.environ.get("LEMMA_STAGING_ORIGIN") or "https://lemma.id").rstrip("/")


def _request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Origin", _origin())
    req.add_header("User-Agent", "lemma-section2-staging-matrix/1.0")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return int(resp.getcode()), data if isinstance(data, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw[:300]}
        return int(exc.code), data if isinstance(data, dict) else {}


def _ok(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{mark}] {name}{suffix}")
    if not condition:
        raise AssertionError(name)


def main() -> int:
    base = _base()
    if os.environ.get("LEMMA_DEPLOY_WAIT", "").strip() in {"1", "true", "yes", "on"}:
        import subprocess

        env = os.environ.copy()
        env["LEMMA_BASE_URL"] = base
        wait = subprocess.run(
            [sys.executable, "scripts/wait_for_deploy_health.py"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            env=env,
            check=False,
        )
        if wait.returncode != 0:
            return 1

    wallet_id = f"wallet_s2_{secrets.token_hex(6)}"
    wallet_secret = secrets.token_hex(32)
    device_id = f"dev_{secrets.token_hex(4)}"
    failures = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        try:
            _ok(name, condition, detail)
        except AssertionError:
            failures += 1

    status, data = _request("GET", f"{base}/api/health")
    check("health", status == 200 and data.get("status") == "ok", f"{status} {data}")

    status, data = _request(
        "POST",
        f"{base}/api/wallet/init-first-session",
        body={"wallet_id": wallet_id},
    )
    check(
        "init-first-session retired",
        status == 410 and data.get("error") == "first_session_route_retired",
        f"{status} {data}",
    )

    pubkey_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    status, data = _request(
        "POST",
        f"{base}/api/wallet/register-signing-key",
        body={
            "wallet_id": wallet_id,
            "device_id": device_id,
            "pubkey": pubkey_b64,
            "signature": sig_b64,
        },
    )
    check(
        "unbound first-device self-bootstrap closed",
        status == 403
        and data.get("code") == "first_device_webauthn_enrollment_required",
        f"{status} {data}",
    )

    status, data = _request(
        "POST",
        f"{base}/api/wallet/device-enroll/begin",
        body={"wallet_id": wallet_id, "device_id": device_id},
    )
    check(
        "device-enroll begin issues challenge",
        status == 200
        and bool(data.get("challenge_key"))
        and bool(data.get("challenge")),
        f"{status} {data}",
    )
    challenge_key = str(data.get("challenge_key") or "")

    status, data = _request(
        "POST",
        f"{base}/api/wallet/device-enroll/complete",
        body={
            "challenge_key": challenge_key or "missing",
            "credential": {"id": "not-a-real-credential", "response": {}},
            "pubkey": pubkey_b64,
            "signature": sig_b64,
        },
    )
    check(
        "device-enroll complete rejects forged WebAuthn",
        status in (401, 403),
        f"{status} {data}",
    )

    status, data = _request(
        "POST",
        f"{base}/api/wallet/session-unlock/begin",
        body={
            "wallet_id": wallet_id,
            "device_id": device_id,
            "credential_id": "missing",
        },
    )
    check(
        "session-unlock begin requires registered passkey",
        status == 403 and data.get("error") == "wallet_passkey_not_registered",
        f"{status} {data}",
    )

    status, data = _request(
        "POST",
        f"{base}/api/wallet/lost-device-recovery/authorize",
        body={"wallet_id": wallet_id, "session_id": "idv_missing"},
    )
    check(
        "lost-device authorize fails closed without verified IDV",
        status == 403,
        f"{status} {data}",
    )

    status, data = _request(
        "POST",
        f"{base}/api/wallet/clear-session",
        body={"wallet_id": wallet_id},
    )
    check(
        "clear-session rejects ambient cookie-less clear",
        status in (401, 403),
        f"{status} {data}",
    )

    status, data = _request(
        "POST",
        f"{base}/api/wallet/signal-unlock",
        body={"wallet_id": wallet_id, "unlocked_at": 1, "expires_at": 2},
    )
    check(
        "signal-unlock requires prior WebAuthn session",
        status == 403
        and data.get("code") == "fresh_webauthn_session_required",
        f"{status} {data}",
    )

    if failures:
        print(f"\nSection 2 staging API matrix FAILED ({failures} checks)")
        return 1
    print("\nSection 2 staging API matrix PASSED")
    print("Next: run docs/status/SECTION2_STAGING_BROWSER_MATRIX.md on this deploy.")
    return 0


if __name__ == "__main__":
    # Allow `python scripts/run_section2_staging_matrix.py` from repo root.
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    raise SystemExit(main())
