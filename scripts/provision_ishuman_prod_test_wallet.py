#!/usr/bin/env python3
"""
Provision (or refresh) the production isHuman test wallet fixture via real Didit IDV.

Creates:
  - registered automation wallet signing key
  - verified master credential after Didit completion
  - per-site derived credential for tickets-demo.lemma.id

Requires production env with Didit enabled. Does NOT use demo test-complete rails.

Usage:
  python scripts/provision_ishuman_prod_test_wallet.py
  python scripts/provision_ishuman_prod_test_wallet.py --base-url https://lemma.id
  python scripts/provision_ishuman_prod_test_wallet.py --wait-seconds 900
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.wallet_keys import b64url_encode, register_self_signature  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402
from scripts.ishuman_prod_test_wallet import (  # noqa: E402
    generate_wallet_secret,
    prod_test_site_id,
    prod_test_target_site,
    prod_test_wallet_id,
    prod_test_wallet_secret,
)
from tests.live.live_test_helpers import (  # noqa: E402
    derive_site_proof_with_assertion,
    get_json_or_raise,
    register_wallet_signing_key,
    start_didit_verification,
)


def _load_site_api_key(site_id: str) -> str:
    env_key = os.getenv("LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY", "").strip()
    if env_key:
        return env_key
    import platform
    import subprocess

    cmd = [
        "heroku",
        "pg:psql",
        "-a",
        "lemma-enterprise",
        "-t",
        "-A",
        "-c",
        f"SELECT api_key FROM sites WHERE site_id='{site_id}';",
    ]
    if platform.system() == "Windows":
        proc = subprocess.run(subprocess.list2cmdline(cmd), capture_output=True, text=True, shell=True)
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("lm_"):
            return line
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision isHuman prod test wallet via Didit")
    parser.add_argument("--base-url", default=os.getenv("ISHUMAN_LIVE_BASE_URL", "https://lemma.id"))
    parser.add_argument("--wait-seconds", type=int, default=int(os.getenv("ISHUMAN_LIVE_VERIFY_TIMEOUT_SECONDS", "900")))
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("ISHUMAN_LIVE_VERIFY_POLL_SECONDS", "5")))
    parser.add_argument("--print-secret", action="store_true", help="Print wallet secret (first-time setup)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    wallet_id = prod_test_wallet_id()
    wallet_secret = prod_test_wallet_secret() or generate_wallet_secret()
    target_site = prod_test_target_site()
    site_id = prod_test_site_id()

    print(f"Provisioning wallet_id={wallet_id} on {base}")
    session = requests.Session()
    register_wallet_signing_key(session, base, wallet_id, wallet_secret)

    start = start_didit_verification(
        session,
        base_url=base,
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        return_url=f"{base}/demo/ishuman",
    )
    session_id = start["session_id"]
    didit_url = start.get("url")
    print(f"  session_id={session_id}")
    if didit_url:
        print(f"\nComplete Didit verification at:\n  {didit_url}\n")

    master_id = ""
    deadline = time.time() + args.wait_seconds
    while time.time() < deadline:
        status_resp = session.get(f"{base}/api/ishuman/verification-status/{session_id}", timeout=30)
        status_data = get_json_or_raise(status_resp)
        if status_resp.status_code == 200 and status_data.get("status") == "verified":
            master_id = status_data.get("credential_id") or ""
            if master_id:
                break
        if status_data.get("status") in ("failed", "declined", "expired"):
            print("Didit verification failed:", status_data, file=sys.stderr)
            return 1
        time.sleep(args.poll_seconds)

    if not master_id:
        print(
            "ERROR: Timed out waiting for Didit verification. Complete the hosted flow and re-run.",
            file=sys.stderr,
        )
        return 1

    site_priv = Ed25519PrivateKey.generate()
    site_pub_b64 = b64url_encode(site_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    derive = derive_site_proof_with_assertion(
        session,
        base_url=base,
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        master_credential_id=master_id,
        target_site=target_site,
        site_signing_pubkey=site_pub_b64,
    )
    if not derive.get("success"):
        print("derive-site-proof failed:", derive, file=sys.stderr)
        return 1

    site_cred = derive.get("credential") or {}
    site_ppid = site_cred.get("subject")
    site_cred_id = site_cred.get("id")
    site_api_key = _load_site_api_key(site_id)

    manifest = {
        "wallet_id": wallet_id,
        "master_credential_id": master_id,
        "site_credential_id": site_cred_id,
        "site_ppid": site_ppid,
        "target_site": target_site,
        "site_id": site_id,
        "site_api_key_present": bool(site_api_key),
    }
    print("\nManifest (safe to log):")
    print(json.dumps(manifest, indent=2))

    print("\nSet Heroku config:")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_WALLET_ID={wallet_id} -a lemma-enterprise")
    print("  heroku config:set LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET=<secret> -a lemma-enterprise")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_TARGET_SITE={target_site} -a lemma-enterprise")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_SITE_ID={site_id} -a lemma-enterprise")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID={master_id} -a lemma-enterprise")
    print(f"  heroku config:set LEMMA_ISHUMAN_PROD_TEST_SITE_PPID={site_ppid} -a lemma-enterprise")
    if site_api_key:
        print("  heroku config:set LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY=<lm_...> -a lemma-enterprise")

    print("\nSet GitHub Actions secrets:")
    print("  gh secret set LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET")
    print("  gh secret set LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID")
    print("  gh secret set LEMMA_ISHUMAN_PROD_TEST_SITE_PPID")
    print("  gh secret set LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY")
    print("  gh secret set ISHUMAN_LIVE_WALLET_ID")
    print("  gh secret set ISHUMAN_LIVE_WALLET_SECRET")
    print("  gh secret set ISHUMAN_LIVE_BASE_URL")

    if args.print_secret:
        print(f"\nGenerated/used wallet_secret={wallet_secret}")
    else:
        print("\nRe-run with --print-secret to display the secret for first-time Heroku config.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
