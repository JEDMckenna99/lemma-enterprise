#!/usr/bin/env python3
"""Quick post-deploy verification for security hardening release."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "https://lemma.id"


def fetch(path: str) -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"User-Agent": "lemma-deploy-verify/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        headers = {k: v for k, v in resp.headers.items()}
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, headers, body


def post(path: str, body: bytes | None = None) -> int:
    req = urllib.request.Request(
        f"{BASE}{path}",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json", "Origin": "https://lemma.id"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        return err.code


def main() -> int:
    results: dict[str, object] = {"base_url": BASE, "checks": []}

    for path in ["/", "/unlock", "/link"]:
        status, headers, _ = fetch(path)
        csp = headers.get("Content-Security-Policy") or headers.get("content-security-policy") or ""
        script_src = ""
        if "script-src " in csp:
            script_src = csp.split("script-src ", 1)[1].split(";", 1)[0]
        results["checks"].append(
            {
                "path": path,
                "status": status,
                "stripe_in_csp": "js.stripe.com" in csp,
                "unpkg_in_csp": "unpkg.com" in csp,
                "cloudflare_analytics_in_csp": "cloudflareinsights" in csp,
                "script_src": script_src,
            }
        )

    _, _, unlock_html = fetch("/unlock")
    results["wallet_bundle_v2545"] = "lemma-wallet.js?v=2545" in unlock_html

    results["legacy_410"] = {
        "create_redirect_token": post("/api/wallet/create-redirect-token", b"{}"),
        "exchange_redirect_token": post("/api/wallet/exchange-redirect-token", b"{}"),
    }

    csp_body = json.dumps(
        {
            "csp-report": {
                "violated-directive": "script-src",
                "blocked-uri": "https://deploy-verify.example.invalid",
                "document-uri": "https://lemma.id/",
            }
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/security/csp-report",
        method="POST",
        data=csp_body,
        headers={"Content-Type": "application/csp-report"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        results["csp_report_status"] = resp.status

    print(json.dumps(results, indent=2))
    home = next(c for c in results["checks"] if c["path"] == "/")
    link = next(c for c in results["checks"] if c["path"] == "/link")
    ok = (
        not home["stripe_in_csp"]
        and not home["unpkg_in_csp"]
        and not home["cloudflare_analytics_in_csp"]
        and link["unpkg_in_csp"]
        and results["wallet_bundle_v2545"]
        and results["legacy_410"]["create_redirect_token"] == 410
        and results["csp_report_status"] == 204
    )
    print(f"deploy_verify={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
