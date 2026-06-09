#!/usr/bin/env python3
"""
Poll production health until deploy rollout is stable.

Used by CI before live post-deploy gates to avoid racing Heroku rollouts.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
TIMEOUT_SECONDS = int(os.environ.get("LEMMA_DEPLOY_WAIT_TIMEOUT", "300"))
POLL_INTERVAL_SECONDS = int(os.environ.get("LEMMA_DEPLOY_WAIT_INTERVAL", "10"))
REQUIRED_CONSECUTIVE_OK = int(os.environ.get("LEMMA_DEPLOY_WAIT_CONSECUTIVE", "2"))


def _health_ok() -> bool:
    url = f"{BASE_URL}/api/health"
    req = urllib.request.Request(url=url, method="GET")
    req.add_header("User-Agent", "lemma-deploy-wait/1.0")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.getcode() != 200:
                return False
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            return payload.get("status") == "ok"
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return False


def main() -> int:
    print(
        f"Waiting for deploy health at {BASE_URL}/api/health "
        f"(timeout={TIMEOUT_SECONDS}s, interval={POLL_INTERVAL_SECONDS}s, "
        f"consecutive_ok={REQUIRED_CONSECUTIVE_OK})"
    )

    deadline = time.monotonic() + TIMEOUT_SECONDS
    consecutive_ok = 0

    while time.monotonic() < deadline:
        if _health_ok():
            consecutive_ok += 1
            print(f"Health ok ({consecutive_ok}/{REQUIRED_CONSECUTIVE_OK})")
            if consecutive_ok >= REQUIRED_CONSECUTIVE_OK:
                print("Deploy health gate passed.")
                return 0
        else:
            consecutive_ok = 0
            print("Health not ready yet.")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(POLL_INTERVAL_SECONDS, remaining))

    print(
        f"Deploy health gate timed out after {TIMEOUT_SECONDS}s "
        f"without {REQUIRED_CONSECUTIVE_OK} consecutive ok responses.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
