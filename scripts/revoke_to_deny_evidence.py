#!/usr/bin/env python3
"""
Create hard evidence for proof-first revoke-to-deny propagation.

Flow (canvas revoke-to-deny smoke):
1) Acquire a wallet unlock token from CLI session-link.
2) Issue a temporary wallet-authenticated proof credential.
3) Confirm /api/auth/exchange-proof succeeds before revoke (ALLOW).
4) Revoke via POST /api/wallet/revoke (credential_type permission or identity).
5) Assert credential id in GET /api/v1/revocation/list within 60s.
6) Assert bloom filter membership (SHA-256 hash of credential id in snapshot).
7) Assert verification endpoint rejects credential (DENY / 403).
8) Write markdown + json artifacts under ops/evidence/launch.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = WORKSPACE_ROOT / "scripts" / "lemma_cli.py"
OUTPUT_DIR = WORKSPACE_ROOT / "ops" / "evidence" / "launch"


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    payload = None
    req_headers = {"User-Agent": "lemma-revoke-to-deny-evidence/1.0"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, method=method, data=payload, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            return resp.getcode(), json.loads(data) if data else {}
    except urllib.error.HTTPError as err:
        data = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(data) if data else {}
        except json.JSONDecodeError:
            parsed = {"raw": data[:500]}
        return err.code, parsed


def _mask(value: str | None) -> str:
    token = (value or "").strip()
    if len(token) <= 12:
        return token
    return f"{token[:8]}...{token[-6:]}"


def _session_link_unlock_token() -> str:
    if not CLI_PATH.exists():
        raise AssertionError(f"Missing CLI script: {CLI_PATH}")
    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "session",
            "link",
            "--api-base",
            BASE_URL,
            "--requested-scope",
            "wallet:control_plane",
            "--json",
        ],
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"session link failed: {result.stderr.strip() or result.stdout.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"session link returned invalid JSON: {exc}") from exc
    unlock_token = str(payload.get("unlock_token") or "").strip()
    if not unlock_token:
        raise AssertionError("session link did not return unlock_token")
    return unlock_token


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    steps: list[dict[str, Any]] = []
    unlock_token = _session_link_unlock_token()
    wallet_headers = {"X-Lemma-Unlock": unlock_token}

    status, payload = _request(
        f"{BASE_URL}/api/wallet/runtimes/issue-proof",
        method="POST",
        headers=wallet_headers,
        body={"site_id": "lemma.id", "granted_by": "revoke_to_deny_evidence"},
    )
    steps.append({"step": "issue_temp_proof", "status": status, "payload": payload, "at": _utc_now()})
    _assert(status == 200 and payload.get("success") is True, f"Issue proof failed: status={status}, payload={payload}")
    credential = payload.get("credential") if isinstance(payload.get("credential"), dict) else None
    _assert(isinstance(credential, dict), "Issued response missing credential object")
    credential_id = str(credential.get("id") or "").strip()
    _assert(bool(credential_id), "Issued credential missing id")

    exchange_body = {"credential": credential}
    status, payload = _request(
        f"{BASE_URL}/api/auth/exchange-proof",
        method="POST",
        headers={"Content-Type": "application/json"},
        body=exchange_body,
    )
    steps.append({"step": "exchange_before_revoke", "status": status, "payload": payload, "at": _utc_now()})
    _assert(status == 200 and payload.get("success") is True, f"Expected ALLOW before revoke, got status={status} payload={payload}")

    status, payload = _request(
        f"{BASE_URL}/api/wallet/revoke",
        method="POST",
        headers=wallet_headers,
        body={
            "credential_id": credential_id,
            "credential_type": "permission",
            "credential_scope": "site_specific",
            "site_domain": "lemma.id",
            "reason": "proof_revoke_to_deny_evidence",
        },
    )
    steps.append({"step": "revoke_credential", "status": status, "payload": payload, "at": _utc_now()})
    _assert(status == 200 and payload.get("success") is True, f"Revoke failed: status={status}, payload={payload}")

    credential_hash = hashlib.sha256(credential_id.encode("utf-8")).hexdigest()

    list_seen = False
    list_attempts: list[dict[str, Any]] = []
    list_deadline = time.time() + 60.0
    while time.time() < list_deadline:
        status, payload = _request(f"{BASE_URL}/api/v1/revocation/list")
        revocations = payload.get("revocations") if isinstance(payload.get("revocations"), list) else []
        found = credential_id in revocations
        list_attempts.append(
            {
                "status": status,
                "count": payload.get("count"),
                "found": found,
                "at": _utc_now(),
            }
        )
        if status == 200 and found:
            list_seen = True
            break
        time.sleep(2.0)
    steps.append({"step": "revocation_list_contains_credential", "attempts": list_attempts})
    _assert(list_seen, f"Credential not in revocation list within 60s: attempts={list_attempts}")

    bloom_seen = False
    bloom_attempts: list[dict[str, Any]] = []
    bloom_deadline = time.time() + 60.0
    while time.time() < bloom_deadline:
        status, payload = _request(f"{BASE_URL}/api/revocation/bloom-filter")
        hashed_ids = payload.get("hashed_revoked_ids") if isinstance(payload.get("hashed_revoked_ids"), list) else []
        found_hash = credential_hash in hashed_ids
        bloom_attempts.append(
            {
                "status": status,
                "count": payload.get("count"),
                "hash_found": found_hash,
                "at": _utc_now(),
            }
        )
        if status == 200 and found_hash:
            bloom_seen = True
            break
        time.sleep(2.0)
    steps.append({"step": "bloom_contains_credential_hash", "attempts": bloom_attempts})
    _assert(bloom_seen, f"Bloom hash not present within 60s: hash={credential_hash}, attempts={bloom_attempts}")

    denied = False
    deny_attempts: list[dict[str, Any]] = []
    for _ in range(8):
        status, payload = _request(
            f"{BASE_URL}/api/auth/exchange-proof",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=exchange_body,
        )
        attempt = {"status": status, "payload": payload, "at": _utc_now()}
        deny_attempts.append(attempt)
        if status >= 400 or payload.get("success") is False:
            denied = True
            break
        time.sleep(1.0)
    steps.append({"step": "exchange_after_revoke", "attempts": deny_attempts})
    _assert(denied, f"Credential was not denied after revoke: attempts={deny_attempts}")

    status_seen = False
    status_attempts: list[dict[str, Any]] = []
    for _ in range(8):
        status, payload = _request(
            f"{BASE_URL}/api/wallet/revocation-status?credential_ids={credential_id}",
            headers=wallet_headers,
        )
        statuses = payload.get("statuses") if isinstance(payload.get("statuses"), dict) else {}
        entry = statuses.get(credential_id) if isinstance(statuses.get(credential_id), dict) else {}
        revoked = bool(entry.get("revoked"))
        status_attempts.append({"status": status, "revoked": revoked, "at": _utc_now()})
        if status == 200 and revoked:
            status_seen = True
            break
        time.sleep(1.0)
    steps.append({"step": "revocation_status_contains_credential", "attempts": status_attempts})
    _assert(status_seen, f"Revoked credential did not appear in revocation status: attempts={status_attempts}")

    delta_seen = False
    delta_shape_ok = False
    delta_attempts: list[dict[str, Any]] = []
    for _ in range(8):
        status, payload = _request(f"{BASE_URL}/api/authz/revocation/delta?since=0&limit=500")
        changes = payload.get("changes") if isinstance(payload.get("changes"), list) else []
        matching = [
            item
            for item in changes
            if isinstance(item, dict) and str(item.get("credential_id") or "").strip() == credential_id
        ]
        found = bool(matching)
        shape_ok = False
        if found:
            first = matching[0]
            ancestor_ids = first.get("ancestor_ids") if isinstance(first.get("ancestor_ids"), list) else []
            shape_ok = bool(first.get("subject_type")) and bool(ancestor_ids)
        delta_attempts.append(
            {
                "status": status,
                "count": len(changes),
                "found": found,
                "shape_ok": shape_ok,
                "at": _utc_now(),
            }
        )
        if status == 200 and found:
            delta_seen = True
            delta_shape_ok = shape_ok
            break
        time.sleep(1.0)
    steps.append({"step": "revocation_delta_contains_credential_best_effort", "attempts": delta_attempts})
    if delta_seen:
        _assert(delta_shape_ok, f"Revocation delta missing shape metadata for credential: attempts={delta_attempts}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    json_path = OUTPUT_DIR / f"{stamp}-revoke-to-deny-evidence.json"
    md_path = OUTPUT_DIR / f"{stamp}-revoke-to-deny-evidence.md"

    evidence = {
        "base_url": BASE_URL,
        "created_at": _utc_now(),
        "unlock_token_masked": _mask(unlock_token),
        "credential_id": credential_id,
        "result": "pass",
        "steps": steps,
    }
    json_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Revoke-To-Deny Evidence",
        "",
        f"- Base URL: {BASE_URL}",
        f"- Created at: {evidence['created_at']}",
        f"- Unlock token: `{evidence['unlock_token_masked']}`",
        f"- Credential id: `{credential_id}`",
        "",
        "## Verification Steps",
        "",
    ]
    for step in steps:
        name = step.get("step", "unknown")
        if "status" in step:
            md_lines.append(f"- `{name}` => status `{step.get('status')}`")
        else:
            attempts = step.get("attempts") or []
            md_lines.append(f"- `{name}` => {len(attempts)} attempt(s), final status `{attempts[-1].get('status') if attempts else 'n/a'}`")
    md_lines += [
        "",
        "## Result",
        "",
        "- PASS: proof exchange ALLOW before revoke and DENY after revoke; revocation status confirms credential revoked.",
        f"- Revocation list contains credential id within 60s: `{list_seen}`.",
        f"- Bloom snapshot contains SHA-256 hash: `{bloom_seen}` (`{credential_hash}`).",
        f"- Revocation delta observed credential id: `{delta_seen}` (best effort endpoint).",
        f"- Revocation delta shape metadata present: `{delta_shape_ok}`.",
        "",
        f"- JSON artifact: `{json_path}`",
    ]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"evidence_json={json_path}")
    print(f"evidence_md={md_path}")
    print("revoke_to_deny_result=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"revoke_to_deny_result=FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1)
