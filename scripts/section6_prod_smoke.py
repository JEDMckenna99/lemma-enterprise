"""Section 6 production smoke: recovery hardening signals on lemma.id."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

ORIGIN = "https://lemma.id"
UA = "section6-prod-smoke/1.0"


def get_text(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"error": raw[:200]}


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    try:
        code, recover_html = get_text(f"{ORIGIN}/recover/complete?token=invalid")
        checks.append(
            (
                "recover-complete-ui",
                code == 200 and "passkey" in recover_html.lower(),
                code,
            )
        )
    except Exception as exc:
        checks.append(("recover-complete-ui", False, str(exc)))

    try:
        code, body = post_json(f"{ORIGIN}/api/recovery/complete", {"token": "invalid"})
        checks.append(
            (
                "complete-rejects-token-only",
                code == 400 and body.get("error") in ("replacement_ppid_required", "Token required"),
                body.get("error"),
            )
        )
    except Exception as exc:
        checks.append(("complete-rejects-token-only", False, str(exc)))

    try:
        code, body = post_json(
            f"{ORIGIN}/api/recovery/complete",
            {"token": "invalid", "passkey_credential_id": "pk-test"},
        )
        checks.append(
            (
                "complete-requires-ppid",
                code == 400 and body.get("error") == "replacement_ppid_required",
                body.get("error"),
            )
        )
    except Exception as exc:
        checks.append(("complete-requires-ppid", False, str(exc)))

    try:
        code, body = post_json(f"{ORIGIN}/api/recovery/complete-wallet", {"token": "x"})
        checks.append(
            (
                "complete-wallet-disabled",
                code == 403 and body.get("error") == "recovery_wallet_path_disabled",
                body.get("error"),
            )
        )
    except Exception as exc:
        checks.append(("complete-wallet-disabled", False, str(exc)))

    try:
        _, py_src = get_text(f"{ORIGIN}/sdk/lemma_ishuman_verify.py")
        checks.append(
            (
                "py-sdk-present",
                "VerificationContext" in py_src,
                len(py_src),
            )
        )
    except Exception as exc:
        checks.append(("py-sdk-present", False, str(exc)))

    failed = False
    print(f"Section 6 production smoke @ {ORIGIN}")
    print("-" * 60)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {detail}")
        if not ok:
            failed = True

    if failed:
        print("-" * 60)
        print("Section 6 prod smoke FAILED.")
        return 1

    print("-" * 60)
    print("All Section 6 prod smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
