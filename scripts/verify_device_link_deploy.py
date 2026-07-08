#!/usr/bin/env python3
"""Post-deploy verification for device link transfer (v2.72.0)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "https://lemma.id"
UA = {"User-Agent": "lemma-device-link-verify/1.0"}


def get(path: str) -> tuple[int, str]:
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def post(path: str, data: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={**UA, "Content-Type": "application/json", "Origin": "https://lemma.id"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return err.code, payload


def main() -> int:
    checks: dict[str, object] = {"base_url": BASE, "passed": True, "results": {}}

    _, sdk = get("/static/js/lemma-wallet.js?v=2675")
    sdk_ok = (
        "VERSION = '2.74.0'" in sdk
        and "_importLinkedIsHumanCredentials" in sdk
        and "sealed_wallet_seed" in sdk
        and "link-unlock-token" in sdk
    )
    checks["results"]["sdk_v274"] = sdk_ok

    _, link_html = get("/link")
    checks["results"]["link_page_v2675"] = "v=2675" in link_html
    checks["results"]["link_page_human_proof_copy"] = "human proof" in link_html.lower()
    checks["results"]["link_page_passkey_flow"] = "registerPasskey" in link_html

    code, body = post("/api/wallet/link-unlock-token")
    checks["results"]["link_unlock_requires_session"] = code == 401 and body.get("error") == "no_session"

    code2, body2 = post("/api/wallet/set-session", {"wallet_id": "wallet_probe"})
    checks["results"]["set_session_requires_token"] = code2 == 403 and body2.get("error") == "unlock_token_required"

    code3, _ = post("/api/wallet/store-link", {"walletSecret": "probe"})
    checks["results"]["no_store_link_endpoint"] = code3 in (404, 405)

    for key, ok in checks["results"].items():
        if not ok:
            checks["passed"] = False

    print(json.dumps(checks, indent=2))
    return 0 if checks["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
