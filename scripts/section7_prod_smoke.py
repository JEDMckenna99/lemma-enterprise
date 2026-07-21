"""Section 7 production smoke: query-param API keys rejected; core health green."""
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
UA = "section7-prod-smoke/1.0"


def get(url: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(text)
        except json.JSONDecodeError:
            return resp.status, text


def request_expect(url: str, *, headers: dict | None = None, expected: int) -> tuple[bool, object]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status == expected, {"status": resp.status, "body_prefix": body[:160]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return exc.code == expected, {"status": exc.code, "body_prefix": detail[:160]}
    except Exception as exc:
        return False, str(exc)


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

    ok, detail = request_expect(
        f"{ORIGIN}/api/ishuman/site-block?api_key=lm_query_param_smoke_test",
        expected=401,
        headers={"Content-Type": "application/json"},
    )
    checks.append(("query-param-api-key-rejected", ok, detail))

    ok_header, header_detail = request_expect(
        f"{ORIGIN}/api/ishuman/site-block",
        expected=401,
        headers={"X-API-Key": "lm_invalid_section7_smoke_key"},
    )
    checks.append(("invalid-header-api-key-denied", ok_header, header_detail))

    passed = 0
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if ok:
            passed += 1

    print(f"\nSection 7 prod smoke: {passed}/{len(checks)} passed")
    print("Note: full production key rotation remains an ops follow-up after deploy.")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
