#!/usr/bin/env python3
"""Autonomous skeleton IDV + optional mobile handoff smoke (no Didit).

Requires on the target deploy (non-production):
  LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true
  LEMMA_ISHUMAN_DEMO_TEST_TOKEN=<shared secret>
  LEMMA_ISHUMAN_SKELETON_IDV_ENABLED=true   (default on non-prod)

Examples:
  python scripts/run_skeleton_idv_e2e.py --base-url https://lemma-staging.herokuapp.com
  python scripts/run_skeleton_idv_e2e.py --base-url http://127.0.0.1:5000 --handoff
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.request


def _post(base_url: str, path: str, body: dict, token: str) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Demo-Test-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if resp.status >= 400:
                raise RuntimeError(f"{path} HTTP {resp.status}: {payload}")
            return payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} HTTP {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run skeleton IDV E2E without Didit")
    parser.add_argument("--base-url", default=os.getenv("LEMMA_BASE_URL", "http://127.0.0.1:5000"))
    parser.add_argument(
        "--token",
        default=os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", ""),
        help="X-Demo-Test-Token value",
    )
    parser.add_argument("--handoff", action="store_true", help="Exercise handoff claim path")
    parser.add_argument("--ttl-seconds", type=int, default=3600)
    args = parser.parse_args()

    if not args.token:
        print("Set LEMMA_ISHUMAN_DEMO_TEST_TOKEN or pass --token", file=sys.stderr)
        return 2

    wallet_id = f"wallet_skeleton_{secrets.token_hex(8)}"
    wallet_secret = secrets.token_hex(32)
    print(f"wallet_id={wallet_id}")

    flow_body = {
        "wallet_id": wallet_id,
        "wallet_secret": wallet_secret,
        "credential_ttl_seconds": args.ttl_seconds,
        "include_handoff": args.handoff,
        "complete_immediately": not args.handoff,
    }
    flow = _post(args.base_url, "/api/demo/ishuman/skeleton-idv-flow", flow_body, args.token)
    session_id = flow["session_id"]
    print(f"session_id={session_id} mode={flow.get('mode')}")

    if args.handoff:
        handoff = flow.get("handoff") or {}
        claim = _post(
            args.base_url,
            "/api/ishuman/idv-mobile-handoff/claim",
            {
                "handoff_id": handoff["handoff_id"],
                "session_id": handoff["session_id"],
                "mk": handoff["mk"],
            },
            args.token,
        )
        print(f"handoff claim ok wallet_id={claim.get('wallet_id')}")

        complete = _post(
            args.base_url,
            "/api/demo/ishuman/skeleton-idv-complete",
            {"session_id": session_id, "wallet_secret": wallet_secret},
            args.token,
        )
        cred = complete.get("credential") or {}
        expires_at = int((cred.get("claims") or {}).get("expiresAt") or 0)
        print(f"credential_id={complete.get('credential_id')} expires_at={expires_at}")
        print(f"mobile_return_url={handoff.get('mobile_return_url')}")
    else:
        cred = flow.get("credential") or {}
        expires_at = int((cred.get("claims") or {}).get("expiresAt") or 0)
        print(f"credential_id={flow.get('credential_id')} expires_at={expires_at}")

    expire = _post(
        args.base_url,
        "/api/demo/ishuman/skeleton-idv-expire",
        {"session_id": session_id},
        args.token,
    )
    print(f"expired_count={expire.get('expired_count')}")
    print("skeleton IDV E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
