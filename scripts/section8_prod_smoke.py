"""Section 8 production smoke: billing integrity signals on lemma.id."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ORIGIN = "https://lemma.id"
UA = "section8-prod-smoke/1.0"


def get(url: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(text)
        except json.JSONDecodeError:
            return resp.status, text


def post_raw(url: str, *, body: bytes, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"User-Agent": UA, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    try:
        code, body = get(f"{ORIGIN}/health")
        checks.append(("health", code == 200 and isinstance(body, dict) and body.get("status") == "healthy", body))
    except Exception as exc:
        checks.append(("health", False, str(exc)))

    try:
        code, body = get(f"{ORIGIN}/ready")
        ready = isinstance(body, dict) and body.get("ready") is True
        checks.append(("ready", code == 200 and ready, body if isinstance(body, dict) else code))
    except Exception as exc:
        checks.append(("ready", False, str(exc)))

    code, detail = post_raw(
        f"{ORIGIN}/api/webhooks/stripe-billing",
        body=b"{}",
        headers={"Content-Type": "application/json", "Stripe-Signature": "invalid"},
    )
    checks.append(
        (
            "stripe-webhook-rejects-invalid-signature",
            code == 400 and "invalid_signature" in detail,
            {"status": code, "body_prefix": detail[:160]},
        )
    )

    try:
        from billing.billing_access import billing_enforcement_enabled

        checks.append(
            (
                "billing-enforcement-flag-readable",
                isinstance(billing_enforcement_enabled(), bool),
                {"enabled": billing_enforcement_enabled()},
            )
        )
    except Exception as exc:
        checks.append(("billing-enforcement-flag-readable", False, str(exc)))

    passed = 0
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if ok:
            passed += 1

    print(f"\nSection 8 prod smoke: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
