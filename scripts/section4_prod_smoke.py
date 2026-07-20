"""Quick Section 4 production smoke checks."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def get(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "section4-prod-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    try:
        code, body = get("https://lemma.id/health")
        checks.append(("health", code == 200 and body.get("status") == "healthy", body))
    except Exception as exc:
        checks.append(("health", False, str(exc)))

    bloom_body = None
    try:
        code, bloom_body = get("https://lemma.id/api/revocation/bloom-filter")
        tl = bloom_body.get("trust_list") or {}
        snap = bloom_body.get("snapshot") or {}
        ok = bool(bloom_body.get("success") and tl.get("signer_pubkey") and snap.get("signature"))
        checks.append(
            (
                "bloom-filter",
                ok,
                {"signer_prefix": str(tl.get("signer_pubkey", ""))[:16], "seq": snap.get("sequence_number")},
            )
        )
    except Exception as exc:
        checks.append(("bloom-filter", False, str(exc)))

    try:
        req = urllib.request.Request(
            "https://lemma.id/sdk/lemma-ishuman-verify.mjs",
            headers={"User-Agent": "section4-prod-smoke/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        checks.append(
            (
                "node-sdk",
                "DEFAULT_NETWORK_ROOT_PUBKEYS_HEX" in text and "signerPubkeyIsPinned" in text,
                len(text),
            )
        )
    except Exception as exc:
        checks.append(("node-sdk", False, str(exc)))

    try:
        req = urllib.request.Request(
            "https://lemma.id/sdk/proof-verifier.js",
            headers={"User-Agent": "section4-prod-smoke/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        checks.append(
            (
                "browser-sdk",
                "signerPubkeyIsPinned" in text and "BROWSER_CANONICAL_V2" in text,
                len(text),
            )
        )
    except Exception as exc:
        checks.append(("browser-sdk", False, str(exc)))

    if bloom_body:
        try:
            os.environ["LEMMA_NETWORK_ROOT_PUBKEYS"] = "3782cf10beea1dcc9a88127a5dbb71c6cba30c1c8c63327a83b8f09867d6a6c2"
            from api.issuer_trust_list import verify_signed_trust_list

            ok, reason = verify_signed_trust_list(bloom_body["trust_list"])
            checks.append(("trust-list-verify", ok, reason))
        except Exception as exc:
            checks.append(("trust-list-verify", False, str(exc)))

    failed = False
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {detail}")
        if not ok:
            failed = True

    if failed:
        return 1
    print("All Section 4 prod smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
