"""Section 9 production smoke: operational reliability signals on lemma.id."""
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
UA = "section9-prod-smoke/1.0"


def get(url: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(text)
        except json.JSONDecodeError:
            return resp.status, text


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    try:
        code, body = get(f"{ORIGIN}/health")
        liveness_ok = (
            code == 200
            and isinstance(body, dict)
            and body.get("status") == "healthy"
            and "timestamp" in body
        )
        checks.append(("health-liveness", liveness_ok, body))
    except Exception as exc:
        checks.append(("health-liveness", False, str(exc)))

    try:
        code, body = get(f"{ORIGIN}/ready")
        ready = isinstance(body, dict) and body.get("ready") is True
        nested = body.get("checks") if isinstance(body, dict) else {}
        checks_ok = isinstance(nested, dict) and all(
            key in nested for key in ("database", "redis", "crypto", "revocation", "billing_outbox")
        )
        rev = nested.get("revocation") if isinstance(nested, dict) else {}
        rev_fresh = isinstance(rev, dict) and rev.get("ok") is True
        checks.append(
            (
                "ready-dependencies",
                code == 200 and ready and checks_ok and rev_fresh,
                body if isinstance(body, dict) else code,
            )
        )
    except Exception as exc:
        checks.append(("ready-dependencies", False, str(exc)))

    try:
        code, bloom = get(f"{ORIGIN}/api/revocation/bloom-filter")
        snap = bloom.get("snapshot") if isinstance(bloom, dict) else {}
        bloom_ok = (
            code == 200
            and isinstance(bloom, dict)
            and bloom.get("success") is True
            and isinstance(snap, dict)
            and bool(snap.get("signature"))
            and bloom.get("generated_at")
        )
        checks.append(
            (
                "bloom-filter-freshness-fields",
                bloom_ok,
                {
                    "sequence": bloom.get("sequence_number") if isinstance(bloom, dict) else None,
                    "generated_at": bloom.get("generated_at") if isinstance(bloom, dict) else None,
                },
            )
        )
    except Exception as exc:
        checks.append(("bloom-filter-freshness-fields", False, str(exc)))

    try:
        from api.config import is_ishuman_didit_purge_enabled

        checks.append(
            (
                "didit-purge-flag-readable",
                isinstance(is_ishuman_didit_purge_enabled(), bool),
                {"enabled": is_ishuman_didit_purge_enabled()},
            )
        )
    except Exception as exc:
        checks.append(("didit-purge-flag-readable", False, str(exc)))

    try:
        proc = (REPO_ROOT / "Procfile").read_text(encoding="utf-8")
        checks.append(
            (
                "procfile-release-and-retention",
                "release:" in proc and "retention_worker:" in proc,
                {"has_release": "release:" in proc, "has_retention_worker": "retention_worker:" in proc},
            )
        )
    except Exception as exc:
        checks.append(("procfile-release-and-retention", False, str(exc)))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status}\t{name}\t{detail}")

    print(f"\nsection9_prod_smoke: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
