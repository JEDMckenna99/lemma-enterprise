#!/usr/bin/env python3
"""
Provision (or refresh) the production isHuman test wallet fixture.

Creates:
  - verified master credential via demo test-complete path
  - optional per-site derived credential for tickets-demo.lemma.id

Requires prod env:
  - LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true
  - STRIPE_SECRET_KEY=sk_test_...
  - LEMMA_ISHUMAN_DEMO_TEST_TOKEN
  - LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET (generated on first run if unset)

Usage:
  python scripts/provision_ishuman_prod_test_wallet.py
  python scripts/provision_ishuman_prod_test_wallet.py --base-url https://lemma.id
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ishuman_prod_test_wallet import (  # noqa: E402
    generate_wallet_secret,
    prod_test_target_site,
    prod_test_wallet_id,
    prod_test_wallet_secret,
)


def _json(resp: requests.Response) -> dict:
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision isHuman prod test wallet")
    parser.add_argument("--base-url", default=os.getenv("ISHUMAN_LIVE_BASE_URL", "https://lemma.id"))
    parser.add_argument("--print-secret", action="store_true", help="Print wallet secret (first-time setup)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    wallet_id = prod_test_wallet_id()
    wallet_secret = prod_test_wallet_secret() or generate_wallet_secret()
    test_token = os.getenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "")
    if not test_token:
        print("ERROR: LEMMA_ISHUMAN_DEMO_TEST_TOKEN is required", file=sys.stderr)
        return 1

    target_site = prod_test_target_site()

    print(f"Provisioning wallet_id={wallet_id} on {base}")

    start = _json(
        requests.post(
            f"{base}/api/ishuman/start-verification",
            json={
                "wallet_id": wallet_id,
                "wallet_secret": wallet_secret,
                "return_url": f"{base}/demo/ishuman",
            },
            timeout=60,
        )
    )
    if not start.get("success"):
        print("start-verification failed:", start, file=sys.stderr)
        return 1

    session_id = start["session_id"]
    print(f"  session_id={session_id}")

    complete = _json(
        requests.post(
            f"{base}/api/demo/ishuman/test-complete-verification",
            headers={"X-Demo-Test-Token": test_token},
            json={
                "session_id": session_id,
                "wallet_secret": wallet_secret,
            },
            timeout=60,
        )
    )
    if not complete.get("success"):
        print("test-complete-verification failed:", complete, file=sys.stderr)
        return 1

    master_id = complete.get("credential_id")
    master_ppid = complete.get("ppid")
    print(f"  master_credential_id={master_id}")
    print(f"  master_ppid={master_ppid}")

    derive = _json(
        requests.post(
            f"{base}/api/ishuman/derive-site-proof",
            json={
                "master_credential_id": master_id,
                "wallet_id": wallet_id,
                "wallet_secret": wallet_secret,
                "target_site": target_site,
            },
            timeout=60,
        )
    )
    if not derive.get("success"):
        print("derive-site-proof failed:", derive, file=sys.stderr)
        return 1

    site_cred = derive.get("credential") or {}
    site_ppid = site_cred.get("subject")
    site_cred_id = site_cred.get("id")
    print(f"  site_credential_id={site_cred_id}")
    print(f"  site_ppid={site_ppid}")
    print(f"  target_site={target_site}")

    manifest = {
        "wallet_id": wallet_id,
        "master_credential_id": master_id,
        "master_ppid": master_ppid,
        "site_credential_id": site_cred_id,
        "site_ppid": site_ppid,
        "target_site": target_site,
        "site_id": os.getenv("LEMMA_ISHUMAN_PROD_TEST_SITE_ID", "site_demo_tickets"),
    }
    print("\nManifest (safe to log):")
    print(json.dumps(manifest, indent=2))

    print("\nSet Heroku config (run once for new secret):")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_WALLET_ID={wallet_id} -a lemma-enterprise")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET=<secret> -a lemma-enterprise")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_TARGET_SITE={target_site} -a lemma-enterprise")
    if args.print_secret:
        print(f"\nGenerated/used wallet_secret={wallet_secret}")
    else:
        print("\nRe-run with --print-secret to display the secret for first-time Heroku config.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
