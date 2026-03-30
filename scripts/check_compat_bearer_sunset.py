#!/usr/bin/env python3
"""
Compatibility bearer sunset gate.

Fails when compat_bearer routes remain after configured sunset date.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.authz_policy import ROUTE_AUTHZ_POLICY


def _parse_iso(text: str) -> datetime:
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when compat bearer routes remain after sunset")
    parser.add_argument("--sunset-utc", default=os.getenv("LEMMA_COMPAT_BEARER_SUNSET_UTC", ""))
    parser.add_argument("--allow-empty-sunset", action="store_true")
    args = parser.parse_args()

    sunset_raw = str(args.sunset_utc or "").strip()
    if not sunset_raw:
        if args.allow_empty_sunset:
            print("compat sunset check: skipped (sunset not set)")
            return 0
        print("compat sunset check: failed (sunset not set)")
        return 1

    try:
        sunset = _parse_iso(sunset_raw)
    except ValueError:
        print(f"compat sunset check: failed (invalid sunset format: {sunset_raw})")
        return 1

    now = datetime.now(timezone.utc)
    compat_routes = [
        f"{method} {path}"
        for (method, path), policy in ROUTE_AUTHZ_POLICY.items()
        if str(getattr(policy, "auth_mode", "compat_bearer") or "compat_bearer") == "compat_bearer"
    ]
    if now >= sunset and compat_routes:
        print(f"compat sunset check: failed (sunset passed at {sunset.isoformat()})")
        print(f"remaining compat_bearer routes: {len(compat_routes)}")
        for route in compat_routes[:25]:
            print(f" - {route}")
        if len(compat_routes) > 25:
            print(" - ...")
        return 1

    print(
        "compat sunset check: pass "
        f"(now={now.isoformat()}, sunset={sunset.isoformat()}, remaining_compat={len(compat_routes)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

