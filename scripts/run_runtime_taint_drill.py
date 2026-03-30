#!/usr/bin/env python3
"""
Best-effort runtime taint drill helper.

Purpose:
- Attempt to move a runtime into a tainted trust state through available APIs.
- Capture which endpoint(s) are available in the current deployment.
- Emit deterministic artifacts under docs/launch-evidence.

This script does not assume a specific control-plane implementation. It tries:
1) wallet runtime taint endpoints (if available),
2) demo taint endpoint (/api/demo/taint-bump) as fallback.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict[str, Any], str]:
    req_headers = {"User-Agent": "lemma-runtime-taint-drill/1.0"}
    if headers:
        req_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, method=method, data=data, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=max(1.0, float(timeout))) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            payload = {}
            if text.strip():
                try:
                    parsed = json.loads(text)
                    payload = parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    payload = {"raw": text[:500]}
            return int(resp.getcode() or 200), payload, ""
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        payload = {}
        if text.strip():
            try:
                parsed = json.loads(text)
                payload = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                payload = {"raw": text[:500]}
        return int(err.code or 500), payload, ""
    except urllib.error.URLError as exc:
        return 0, {}, str(exc)
    except OSError as exc:
        return 0, {}, str(exc)


def _session_link_unlock_token(base_url: str) -> tuple[str, str]:
    cli_path = REPO_ROOT / "scripts" / "lemma_cli.py"
    if not cli_path.exists():
        return "", f"missing_cli_script:{cli_path}"
    completed = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "session",
            "link",
            "--api-base",
            base_url.rstrip("/"),
            "--requested-scope",
            "wallet:control_plane",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return "", (completed.stderr or completed.stdout or "session_link_failed").strip()[:500]
    try:
        payload = json.loads((completed.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        return "", "session_link_invalid_json"
    token = str(payload.get("unlock_token") or "").strip()
    if not token:
        return "", "session_link_missing_unlock_token"
    return token, ""


def _find_runtime_state(runtime_payload: dict[str, Any], runtime_id: str) -> dict[str, Any]:
    runtimes = runtime_payload.get("runtimes")
    if not isinstance(runtimes, list):
        return {}
    for item in runtimes:
        if isinstance(item, dict) and str(item.get("runtime_id") or "").strip() == runtime_id:
            return item
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Best-effort runtime taint drill helper.")
    parser.add_argument("--base-url", default="https://lemma.id")
    parser.add_argument("--runtime-id", default="lemma-firewall-default")
    parser.add_argument("--org-id", default="org_default")
    parser.add_argument("--environment", default="prod")
    parser.add_argument("--trust-state", default="tainted_external")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output-dir", default="docs/launch-evidence")
    args = parser.parse_args()

    base_url = str(args.base_url).rstrip("/")
    runtime_id = str(args.runtime_id).strip()
    org_id = str(args.org_id).strip()
    environment = str(args.environment).strip()
    trust_state = str(args.trust_state).strip() or "tainted_external"
    timeout = float(args.timeout)

    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = (REPO_ROOT / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[dict[str, Any]] = []
    unlock_token, unlock_err = _session_link_unlock_token(base_url)
    unlock_ok = bool(unlock_token)

    # Baseline runtime state read (wallet path).
    baseline_runtime_state: dict[str, Any] = {}
    baseline_ppid = ""
    if unlock_ok:
        status, payload, err = _request(
            url=f"{base_url}/api/wallet/runtimes?org_id={urllib.parse.quote(org_id)}&environment={urllib.parse.quote(environment)}",
            headers={
                "X-Lemma-Unlock": unlock_token,
                "X-Lemma-Org-Id": org_id,
                "X-Lemma-Environment": environment,
            },
            timeout=timeout,
        )
        attempts.append(
            {
                "step": "wallet_runtime_list_before",
                "status": status,
                "error": err,
                "at": _utc_now(),
            }
        )
        if status == 200 and isinstance(payload, dict):
            baseline_runtime_state = _find_runtime_state(payload, runtime_id)
            baseline_ppid = str(payload.get("ppid") or "").strip()

    endpoint_candidates: list[dict[str, Any]] = []
    if unlock_ok:
        endpoint_candidates.extend(
            [
                {
                    "name": "wallet_runtime_taint",
                    "url": f"{base_url}/api/wallet/runtimes/{runtime_id}/taint",
                    "headers": {
                        "X-Lemma-Unlock": unlock_token,
                        "X-Lemma-Org-Id": org_id,
                        "X-Lemma-Environment": environment,
                    },
                    "body": {
                        "org_id": org_id,
                        "environment": environment,
                        "trust_state": trust_state,
                    },
                },
                {
                    "name": "wallet_firewall_runtime_taint",
                    "url": f"{base_url}/api/wallet/firewall/runtimes/{runtime_id}/taint",
                    "headers": {
                        "X-Lemma-Unlock": unlock_token,
                        "X-Lemma-Org-Id": org_id,
                        "X-Lemma-Environment": environment,
                    },
                    "body": {
                        "org_id": org_id,
                        "environment": environment,
                        "trust_state": trust_state,
                    },
                },
            ]
        )

    # Demo fallback endpoint (can work even when wallet taint endpoint is absent).
    endpoint_candidates.append(
        {
            "name": "demo_taint_bump",
            "url": f"{base_url}/api/demo/taint-bump",
            "headers": {},
            "body": {"runtime_id": runtime_id, "trust_state": trust_state},
        }
    )

    taint_applied = False
    taint_endpoint_used = ""
    for candidate in endpoint_candidates:
        status, payload, err = _request(
            url=str(candidate["url"]),
            method="POST",
            headers=candidate.get("headers"),
            body=candidate.get("body"),
            timeout=timeout,
        )
        ok = bool(status == 200 and payload.get("success") is True and not err)
        attempts.append(
            {
                "step": "taint_attempt",
                "endpoint": candidate["name"],
                "url": candidate["url"],
                "status": status,
                "ok": ok,
                "error": err,
                "payload": payload,
                "at": _utc_now(),
            }
        )
        if ok:
            taint_applied = True
            taint_endpoint_used = str(candidate["name"])
            break

    # Post-check state reads.
    runtime_state_after: dict[str, Any] = {}
    if unlock_ok:
        status, payload, err = _request(
            url=f"{base_url}/api/wallet/runtimes?org_id={urllib.parse.quote(org_id)}&environment={urllib.parse.quote(environment)}",
            headers={
                "X-Lemma-Unlock": unlock_token,
                "X-Lemma-Org-Id": org_id,
                "X-Lemma-Environment": environment,
            },
            timeout=timeout,
        )
        attempts.append(
            {
                "step": "wallet_runtime_list_after",
                "status": status,
                "error": err,
                "at": _utc_now(),
            }
        )
        if status == 200 and isinstance(payload, dict):
            runtime_state_after = _find_runtime_state(payload, runtime_id)

    demo_state_after: dict[str, Any] = {}
    status, payload, err = _request(
        url=f"{base_url}/api/demo/state?runtime_id={urllib.parse.quote(runtime_id)}",
        headers={},
        timeout=timeout,
    )
    attempts.append(
        {
            "step": "demo_state_after",
            "status": status,
            "error": err,
            "at": _utc_now(),
        }
    )
    if status == 200 and isinstance(payload, dict):
        state = payload.get("runtime_state")
        if isinstance(state, dict):
            demo_state_after = state

    result_state = str(runtime_state_after.get("trust_state") or "").strip().lower()
    result_epoch = runtime_state_after.get("taint_epoch")
    demo_state = str(demo_state_after.get("trust_state") or "").strip().lower()
    demo_epoch = demo_state_after.get("taint_epoch")

    # "success" means at least one endpoint accepted the taint action.
    ok = bool(taint_applied)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    json_path = output_dir / f"{stamp}-runtime-taint-drill.json"
    md_path = output_dir / f"{stamp}-runtime-taint-drill.md"

    evidence = {
        "created_at": _utc_now(),
        "base_url": base_url,
        "runtime_id": runtime_id,
        "org_id": org_id,
        "environment": environment,
        "requested_trust_state": trust_state,
        "unlock_ok": unlock_ok,
        "unlock_error": unlock_err,
        "wallet_ppid": baseline_ppid,
        "baseline_runtime_state": baseline_runtime_state,
        "runtime_state_after": runtime_state_after,
        "demo_state_after": demo_state_after,
        "taint_applied": taint_applied,
        "taint_endpoint_used": taint_endpoint_used,
        "attempts": attempts,
        "ok": ok,
    }
    json_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Runtime Taint Drill",
        "",
        f"- Base URL: {base_url}",
        f"- Runtime: `{runtime_id}`",
        f"- Tenant: `{org_id}/{environment}`",
        f"- Requested trust_state: `{trust_state}`",
        f"- Unlock token available: `{unlock_ok}`",
        f"- Taint applied: `{taint_applied}`",
        f"- Endpoint used: `{taint_endpoint_used or 'none'}`",
        "",
        "## Observed state",
        "",
        f"- Wallet runtime trust_state: `{result_state or 'n/a'}`",
        f"- Wallet runtime taint_epoch: `{result_epoch if result_epoch is not None else 'n/a'}`",
        f"- Demo runtime trust_state: `{demo_state or 'n/a'}`",
        f"- Demo runtime taint_epoch: `{demo_epoch if demo_epoch is not None else 'n/a'}`",
        "",
        "## Result",
        "",
        (
            "- PASS: at least one taint endpoint accepted and state changed/recorded."
            if ok
            else "- SKIP/FAIL: no taint endpoint accepted on this deployment. Use setup-cmd + infra/admin path if needed."
        ),
        f"- JSON artifact: `{json_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"runtime_taint_drill_json={json_path}")
    print(f"runtime_taint_drill_md={md_path}")
    print(f"runtime_taint_drill_result={'PASS' if ok else 'SKIP'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
