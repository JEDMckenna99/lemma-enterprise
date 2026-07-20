"""Section 5 production smoke: revocation fail-closed + replay protection signals."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ORIGIN = "https://lemma.id"
UA = "section5-prod-smoke/1.0"


def get(url: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(text)
        except json.JSONDecodeError:
            return resp.status, text


def get_expect_status(url: str, expected: int) -> tuple[bool, object]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status == expected, {"status": resp.status, "body_prefix": body[:120]}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return exc.code == expected, {"status": exc.code, "body_prefix": detail[:120]}
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    try:
        code, body = get(f"{ORIGIN}/health")
        checks.append(("health", code == 200 and isinstance(body, dict) and body.get("status") == "healthy", body))
    except Exception as exc:
        checks.append(("health", False, str(exc)))

    bloom_body: dict | None = None
    try:
        code, bloom_body_raw = get(f"{ORIGIN}/api/revocation/bloom-filter")
        bloom_body = bloom_body_raw if isinstance(bloom_body_raw, dict) else {}
        snap = bloom_body.get("snapshot") or {}
        hashed = bloom_body.get("hashed_revoked_ids") or []
        ok = (
            code == 200
            and bloom_body.get("success") is True
            and bool(snap.get("signature"))
            and isinstance(hashed, list)
            and all(re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in hashed)
        )
        checks.append(
            (
                "bloom-filter-signed-hashes-only",
                ok,
                {
                    "sequence": snap.get("sequence_number"),
                    "count": bloom_body.get("count"),
                    "has_signature": bool(snap.get("signature")),
                },
            )
        )
    except Exception as exc:
        checks.append(("bloom-filter-signed-hashes-only", False, str(exc)))

    try:
        code, ready_raw = get(f"{ORIGIN}/ready")
        ready_body = ready_raw if isinstance(ready_raw, dict) else {}
        checks_dict = ready_body.get("checks") or {}
        ok = code in (200, 503) and "revocation" in checks_dict
        checks.append(
            (
                "ready-includes-revocation-check",
                ok,
                {
                    "http": code,
                    "ready": ready_body.get("ready"),
                    "checks": checks_dict,
                },
            )
        )
    except Exception as exc:
        checks.append(("ready-includes-revocation-check", False, str(exc)))

    try:
        code, list_raw = get(f"{ORIGIN}/api/v1/revocation/list")
        list_body = list_raw if isinstance(list_raw, dict) else {}
        ok = code == 200 and list_body.get("success") is True and isinstance(list_body.get("revocations"), list)
        checks.append(
            (
                "legacy-revocation-list-healthy",
                ok,
                {"count": list_body.get("count")},
            )
        )
    except Exception as exc:
        checks.append(("legacy-revocation-list-healthy", False, str(exc)))

    try:
        _, sdk_text = get(f"{ORIGIN}/sdk/lemma-ishuman-verify.mjs")
        text = sdk_text if isinstance(sdk_text, str) else ""
        ok = (
            "revocationCandidates" in text
            and "credentialRevokedInSnapshot" in text
            and "async consume(nonce" in text.replace("\n", " ")
            and text.index("invalid_action_signature") < text.index("action_nonce_reused")
        )
        checks.append(
            (
                "node-sdk-revocation-and-nonce-order",
                ok,
                {
                    "has_revocation_candidates": "revocationCandidates" in text,
                    "async_redis_consume": "async consume" in text,
                },
            )
        )
    except Exception as exc:
        checks.append(("node-sdk-revocation-and-nonce-order", False, str(exc)))

    try:
        _, py_text = get(f"{ORIGIN}/sdk/lemma_ishuman_verify.py")
        text = py_text if isinstance(py_text, str) else ""
        ok = "def revocation_candidates" in text and "def credential_revoked_in_snapshot" in text
        checks.append(("py-sdk-revocation-candidates", ok, len(text)))
    except Exception as exc:
        checks.append(("py-sdk-revocation-candidates", False, str(exc)))

    if bloom_body:
        try:
            from api.bloom_snapshot import verify_bloom_snapshot, verify_snapshot_matches_payload

            snap = bloom_body.get("snapshot") or {}
            ok_sig, reason = verify_bloom_snapshot(snap)
            ok_payload, payload_reason = verify_snapshot_matches_payload(
                snap,
                hashed_revoked_ids=bloom_body.get("hashed_revoked_ids") or [],
            )
            checks.append(
                (
                    "bloom-snapshot-crypto-self-check",
                    ok_sig and ok_payload,
                    {"sig": reason, "payload": payload_reason},
                )
            )
        except Exception as exc:
            checks.append(("bloom-snapshot-crypto-self-check", False, str(exc)))

    failed = False
    print(f"Section 5 production smoke @ {ORIGIN}")
    print("-" * 60)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {detail}")
        if not ok:
            failed = True

    if failed:
        print("-" * 60)
        print("Section 5 prod smoke FAILED.")
        return 1

    print("-" * 60)
    print("All Section 5 prod smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
