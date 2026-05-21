#!/usr/bin/env python3
"""
Production revocation smoke drill for isHuman.

Uses:
  - site API key from Heroku DB (site_demo_tickets) OR LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY
  - prod test wallet fixture (LEMMA_ISHUMAN_PROD_TEST_WALLET_*)

Usage:
  export LEMMA_ISHUMAN_PROD_TEST_WALLET_SECRET=...
  python scripts/run_ishuman_prod_revocation_smoke.py
  python scripts/run_ishuman_prod_revocation_smoke.py --base-url https://lemma.id
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.bloom_snapshot import verify_bloom_snapshot, verify_snapshot_matches_payload  # noqa: E402
from api.ppid import canonicalize_rp_id, derive_ppid_from_wallet_secret  # noqa: E402
from api.wallet_authn import issue_wallet_challenge  # noqa: E402
from api.wallet_keys import (  # noqa: E402
    build_wallet_assertion,
    derive_wallet_signing_keypair,
    pubkey_to_b64url,
    register_self_signature,
)
from scripts.ishuman_prod_test_wallet import (  # noqa: E402
    prod_test_master_credential_id,
    prod_test_site_id,
    prod_test_site_ppid,
    prod_test_target_site,
    prod_test_wallet_id,
    require_prod_test_secret,
)


def _run_heroku(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run Heroku CLI (shell=True on Windows when heroku is a shim)."""
    if platform.system() == "Windows":
        return subprocess.run(
            subprocess.list2cmdline(args),
            capture_output=True,
            text=True,
            shell=True,
        )
    return subprocess.run(args, capture_output=True, text=True)


def _load_fixture_site_ppid(wallet_id: str, target_site: str) -> str:
    """Resolve fixture site PPID from prod DB when env is unset."""
    proc = _run_heroku(
        [
            "heroku",
            "pg:psql",
            "-a",
            "lemma-enterprise",
            "-t",
            "-A",
            "-c",
            (
                "SELECT derived_ppid FROM derived_credentials "
                f"WHERE wallet_id='{wallet_id}' AND target_site='{target_site}' "
                "AND is_active=true ORDER BY derived_at DESC LIMIT 1;"
            ),
        ],
    )
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("did:lemma:ppid_"):
            return line
    return ""


def _load_ppid_root_key() -> str:
    env_key = os.getenv("LEMMA_PPID_ROOT_KEY", "").strip()
    if env_key:
        return env_key
    try:
        proc = _run_heroku(
            ["heroku", "config:get", "LEMMA_PPID_ROOT_KEY", "-a", "lemma-enterprise"],
        )
    except FileNotFoundError:
        return ""
    key = (proc.stdout or "").strip()
    if key:
        os.environ["LEMMA_PPID_ROOT_KEY"] = key
    return key


def _load_site_api_key(site_id: str) -> str:
    env_key = os.getenv("LEMMA_ISHUMAN_PROD_TEST_SITE_API_KEY", "").strip()
    if env_key:
        return env_key
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
    proc = _run_heroku(cmd)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("lm_"):
            return line
    raise RuntimeError(f"Could not load API key for site {site_id}")


def _ensure_wallet_registered(base: str, wallet_id: str, wallet_secret: str) -> None:
    pubkey_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    r = requests.post(
        f"{base}/api/wallet/register-signing-key",
        json={"wallet_id": wallet_id, "pubkey": pubkey_b64, "signature": sig_b64},
        timeout=30,
    )
    if r.status_code not in (200, 403):
        raise RuntimeError(f"prod register-signing-key failed: HTTP {r.status_code} {r.text[:200]}")


def _derive_assertion(base: str, wallet_id: str, wallet_secret: str, body: dict) -> dict:
    _ensure_wallet_registered(base, wallet_id, wallet_secret)
    challenge = issue_wallet_challenge(wallet_id=wallet_id)
    remote = requests.post(
        f"{base}/api/wallet/challenge",
        json={"wallet_id": wallet_id},
        timeout=30,
    )
    if remote.ok and remote.json().get("nonce"):
        challenge = remote.json()
    field_names = ["master_credential_id", "target_site", "site_signing_pubkey"]
    field_values = {
        key: "" if body.get(key) is None else str(body.get(key, ""))
        for key in field_names
    }
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=field_names,
        field_values=field_values,
        nonce_b64=challenge["nonce"],
    )
    return {"nonce": assertion.nonce, "signature": assertion.signature}


def _step(name: str, ok: bool, detail: str) -> dict:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return {"step": name, "ok": ok, "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("ISHUMAN_LIVE_BASE_URL", "https://lemma.id"))
    parser.add_argument("--master-credential-id", default=os.getenv("LEMMA_ISHUMAN_PROD_TEST_MASTER_CREDENTIAL_ID", ""))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    wallet_id = prod_test_wallet_id()
    wallet_secret = require_prod_test_secret()
    site_id = prod_test_site_id()
    target_site = canonicalize_rp_id(prod_test_target_site())
    site_ppid = prod_test_site_ppid() or _load_fixture_site_ppid(wallet_id, target_site)
    if not site_ppid:
        if _load_ppid_root_key():
            site_ppid = derive_ppid_from_wallet_secret(wallet_secret, target_site)
        else:
            print(
                "WARNING: fixture site PPID unavailable — set LEMMA_ISHUMAN_PROD_TEST_SITE_PPID "
                "or ensure heroku CLI can query derived_credentials.",
            )
            site_ppid = derive_ppid_from_wallet_secret(wallet_secret, target_site)

    api_key = _load_site_api_key(site_id)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    results = []
    ppid_drill = f"did:lemma:ppid_smoke_{int(time.time())}"

    # Health
    r = requests.get(f"{base}/api/health", timeout=30)
    results.append(_step("health", r.status_code == 200, f"HTTP {r.status_code}"))

    # Demo prod-guard (Phase 4): test-verify must fail closed on production
    for path, label in (
        ("/api/demo/ishuman/verify-once-test-mode", "verify-once blocked on prod"),
        ("/api/demo/ishuman/test-complete-verification", "test-complete blocked on prod"),
    ):
        r = requests.post(
            f"{base}{path}",
            json={"wallet_id": wallet_id, "session_id": "ishuman_sess_smoke_guard"},
            timeout=30,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        err = (data.get("error") or "") if isinstance(data, dict) else ""
        guard_ok = r.status_code == 403 and err in {
            "test_verify_disabled",
            "prod_test_verify_forbidden",
            "demo_test_token_required",
            "stripe_test_key_required",
        }
        results.append(_step(label, guard_ok, f"HTTP {r.status_code} error={err or r.text[:120]}"))

    # Signed bloom snapshot (Phase 3)
    r = requests.get(f"{base}/api/revocation/bloom-filter", timeout=30)
    bloom_data = r.json() if r.ok else {}
    snapshot = bloom_data.get("snapshot") or {}
    hashed_ids = bloom_data.get("hashed_revoked_ids") or []
    bloom_ok = (
        r.status_code == 200
        and bloom_data.get("success")
        and snapshot.get("signature")
        and snapshot.get("sequence_number") is not None
        and snapshot.get("generated_at")
    )
    if bloom_ok:
        trust_ok, trust_reason = verify_bloom_snapshot(snapshot)
        payload_ok, payload_reason = verify_snapshot_matches_payload(
            snapshot,
            hashed_revoked_ids=hashed_ids,
        )
        bloom_ok = trust_ok and payload_ok
        bloom_detail = (
            f"seq={snapshot.get('sequence_number')} trust={trust_reason} payload={payload_reason}"
        )
    else:
        bloom_detail = f"HTTP {r.status_code} {str(bloom_data)[:180]}"
    results.append(_step("signed bloom snapshot", bloom_ok, bloom_detail))

    # Site-block synthetic PPID
    r = requests.post(
        f"{base}/api/ishuman/site-block",
        headers=headers,
        json={"ppid": ppid_drill, "reason": "prod smoke synthetic"},
        timeout=30,
    )
    data = r.json()
    results.append(_step("site-block synthetic", r.ok and data.get("success"), str(data)))

    r = requests.get(f"{base}/api/ishuman/check", params={"ppid": ppid_drill, "site_id": site_id}, timeout=30)
    data = r.json()
    results.append(
        _step(
            "check synthetic (site_id)",
            data.get("blocked") and data.get("reason") == "site_block",
            str(data),
        )
    )

    r = requests.get(f"{base}/api/ishuman/check", params={"ppid": ppid_drill}, timeout=30)
    data = r.json()
    results.append(
        _step(
            "check synthetic (canonical revoke, no site_id)",
            data.get("blocked") and data.get("reason") in {"site_ppid_revoked", "network_revocation"},
            str(data),
        )
    )

    # Unblock synthetic
    r = requests.post(
        f"{base}/api/ishuman/site-unblock",
        headers=headers,
        json={"ppid": ppid_drill},
        timeout=30,
    )
    results.append(_step("site-unblock synthetic", r.ok and r.json().get("success"), str(r.json())))

    # Block fixture site PPID and deny derive
    master_id = args.master_credential_id or prod_test_master_credential_id()
    if not master_id:
        # Resolve latest verified master for fixture wallet
        proc = _run_heroku(
            [
                "heroku",
                "pg:psql",
                "-a",
                "lemma-enterprise",
                "-t",
                "-A",
                "-c",
                f"SELECT credential_id FROM ishuman_verifications WHERE wallet_id='{wallet_id}' AND status='verified' ORDER BY verified_at DESC LIMIT 1;",
            ],
        )
        for line in proc.stdout.splitlines():
            if line.startswith("ishuman_master_"):
                master_id = line.strip()
                break

    r = requests.post(
        f"{base}/api/ishuman/site-block",
        headers=headers,
        json={"ppid": site_ppid, "reason": "prod smoke fixture site PPID"},
        timeout=30,
    )
    block_data = r.json()
    results.append(_step("site-block fixture site_ppid", r.ok and block_data.get("success"), str(block_data)))

    if master_id:
        _priv, pub = derive_wallet_signing_keypair(wallet_secret)
        site_signing_pubkey = pubkey_to_b64url(pub)
        derive_body = {
            "master_credential_id": master_id,
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "target_site": target_site,
            "site_signing_pubkey": site_signing_pubkey,
        }
        derive_body["wallet_assertion"] = _derive_assertion(base, wallet_id, wallet_secret, derive_body)
        r = requests.post(
            f"{base}/api/ishuman/derive-site-proof",
            json=derive_body,
            timeout=30,
        )
        denied = r.status_code == 403 and (r.json().get("error") or "") in {
            "site_ppid_blocked",
            "site_ppid_revoked",
            "master_credential_revoked",
        }
        results.append(
            _step(
                "derive-site-proof denied when fixture PPID blocked",
                denied,
                f"HTTP {r.status_code} {r.text[:200]}",
            )
        )
    else:
        results.append(
            _step(
                "derive-site-proof denied when fixture PPID blocked",
                False,
                "no verified master for fixture wallet — run provision_ishuman_prod_test_wallet.py",
            )
        )

    r = requests.post(
        f"{base}/api/ishuman/site-unblock",
        headers=headers,
        json={"ppid": site_ppid},
        timeout=30,
    )
    results.append(_step("site-unblock fixture site_ppid", r.ok and r.json().get("success"), str(r.json())))

    passed = sum(1 for row in results if row["ok"])
    print(f"\nSummary: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
