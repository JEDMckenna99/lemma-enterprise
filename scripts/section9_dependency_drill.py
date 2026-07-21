"""Section 9 dependency drill: read-only production checks vs outage playbook."""
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
UA = "section9-dependency-drill/1.0"
PLAYBOOK = REPO_ROOT / "docs" / "operations" / "DEPENDENCY_OUTAGE_PLAYBOOK.md"


def get(url: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(text)
        except json.JSONDecodeError:
            return resp.status, text


def post_empty(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    code, health = get(f"{ORIGIN}/health")
    checks.append(
        (
            "liveness-no-deps",
            code == 200 and isinstance(health, dict) and health.get("status") == "healthy",
            health,
        )
    )

    code, ready = get(f"{ORIGIN}/ready")
    nested = ready.get("checks") if isinstance(ready, dict) else {}
    dep_keys = ("database", "redis", "crypto", "revocation")
    checks.append(
        (
            "readiness-exposes-dependencies",
            isinstance(nested, dict) and all(k in nested for k in dep_keys),
            nested,
        )
    )

    code, bloom = get(f"{ORIGIN}/api/revocation/bloom-filter")
    checks.append(
        (
            "revocation-available-or-fail-closed",
            code in {200, 503},
            {"status": code, "error": bloom.get("error") if isinstance(bloom, dict) else None},
        )
    )

    code, detail = post_empty(f"{ORIGIN}/api/recovery/complete")
    checks.append(
        (
            "recovery-fails-closed-without-token",
            code == 400,
            {"status": code, "body_prefix": detail[:120]},
        )
    )

    code, detail = post_empty(f"{ORIGIN}/api/webhooks/stripe-billing")
    checks.append(
        (
            "billing-webhook-rejects-unsigned",
            code == 400,
            {"status": code, "body_prefix": detail[:120]},
        )
    )

    checks.append(
        (
            "playbook-present",
            PLAYBOOK.is_file(),
            str(PLAYBOOK),
        )
    )

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}\t{name}\t{detail}")
    print(f"\nsection9_dependency_drill: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
