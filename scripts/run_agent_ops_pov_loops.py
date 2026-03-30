#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 25.0,
) -> tuple[int, dict[str, Any]]:
    req_headers = {"User-Agent": "lemma-agent-ops-pov-loops/1.0"}
    if headers:
        req_headers.update(headers)
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    request_obj = urllib.request.Request(url=url, method=method, data=payload, headers=req_headers)
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return int(resp.getcode() or 200), json.loads(text) if text else {}
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", errors="replace")
        try:
            payload_obj = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload_obj = {"raw": text[:500]}
        return int(err.code or 500), payload_obj


def _read_proof(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _session_link_unlock_token(cli_path: Path, base_url: str) -> str:
    result = subprocess.run(
        [sys.executable, str(cli_path), "session", "link", "--api-base", base_url, "--requested-scope", "wallet:control_plane", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"session link failed: {result.stderr.strip() or result.stdout.strip()}")
    payload = json.loads(result.stdout or "{}")
    unlock_token = str(payload.get("unlock_token") or "").strip()
    if not unlock_token:
        raise RuntimeError("session link did not return unlock_token")
    return unlock_token


def _run_loop_b_revoke_to_deny(script_path: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True, check=False, env=env)
    lines = (result.stdout or "").splitlines()
    evidence_json = ""
    evidence_md = ""
    for line in lines:
        if line.startswith("evidence_json="):
            evidence_json = line.split("=", 1)[1].strip()
        elif line.startswith("evidence_md="):
            evidence_md = line.split("=", 1)[1].strip()
    ok = result.returncode == 0
    return {
        "ok": ok,
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:] if result.stdout else "",
        "stderr": result.stderr[-4000:] if result.stderr else "",
        "evidence_json": evidence_json,
        "evidence_md": evidence_md,
    }


def run(args: argparse.Namespace) -> int:
    workspace = Path(__file__).resolve().parents[1]
    cli_path = workspace / "scripts" / "lemma_cli.py"
    revoke_script = workspace / "scripts" / "revoke_to_deny_evidence.py"
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")

    proof_file = Path(args.proof_file).expanduser().resolve()
    if not proof_file.exists():
        raise RuntimeError(f"proof file not found: {proof_file}")
    credential_json = _read_proof(proof_file)

    unlock_token = _session_link_unlock_token(cli_path, args.api_base)

    loop_a_steps: list[dict[str, Any]] = []
    authorize_headers = {
        "X-Lemma-Credential": credential_json,
        "X-Lemma-Org-Id": args.org_id,
        "X-Lemma-Environment": args.environment,
    }
    authorize_body = {
        "action": args.action,
        "org_id": args.org_id,
        "environment": args.environment,
        "root_type": args.root_type,
    }
    status, payload = _request(
        f"{args.api_base.rstrip('/')}/api/wallet/runtimes/{args.runtime_id}/authorize",
        method="POST",
        headers=authorize_headers,
        body=authorize_body,
        timeout=args.timeout,
    )
    loop_a_steps.append({"step": "authorize_allow", "status": status, "payload": payload, "at": _utc_now()})
    allow_ok = bool(status == 200 and payload.get("success") is True)

    list_headers = {
        "X-Lemma-Unlock": unlock_token,
        "X-Lemma-Org-Id": args.org_id,
        "X-Lemma-Environment": args.environment,
    }
    query = f"runtime_id={args.runtime_id}&org_id={args.org_id}&environment={args.environment}&limit=20"
    status, payload = _request(
        f"{args.api_base.rstrip('/')}/api/wallet/runtimes/decisions?{query}",
        method="GET",
        headers=list_headers,
        timeout=args.timeout,
    )
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    loop_a_steps.append({"step": "decisions_list", "status": status, "count": len(decisions), "at": _utc_now()})

    explain_ok = False
    lineage_explain_ok = False
    correlation_id = ""
    reason_code = ""

    def _lineage_snapshot_ok(lineage_obj: dict[str, Any]) -> bool:
        if not isinstance(lineage_obj, dict):
            return False
        root_grant_present = bool(str(lineage_obj.get("root_grant_id") or "").strip())
        parent_present = bool(str(lineage_obj.get("parent_proof_id") or "").strip())
        try:
            depth_value = int(lineage_obj.get("delegation_depth") or 0)
        except (TypeError, ValueError):
            depth_value = 0
        return bool(root_grant_present and (parent_present or depth_value >= 1))
    if decisions:
        first = decisions[0] if isinstance(decisions[0], dict) else {}
        decision_id = str(first.get("decision_id") or "").strip()
        correlation_id = str(first.get("request_correlation_id") or "").strip()
        reason_code = str(first.get("reason_code") or "").strip()
        if decision_id:
            status, payload = _request(
                f"{args.api_base.rstrip('/')}/api/wallet/runtimes/decisions/{decision_id}/explain",
                method="GET",
                headers=list_headers,
                timeout=args.timeout,
            )
            explain_ok = bool(status == 200 and payload.get("success") is True)
            explain_decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
            explain_lineage = explain_decision.get("delegation_lineage") if isinstance(explain_decision.get("delegation_lineage"), dict) else {}
            lineage_explain_ok = _lineage_snapshot_ok(explain_lineage)
            loop_a_steps.append({"step": "decision_explain", "status": status, "payload": payload, "at": _utc_now()})

    export_ok = False
    lineage_export_ok = False
    status, payload = _request(
        f"{args.api_base.rstrip('/')}/api/wallet/runtimes/decisions/export?format=json&{query}",
        method="GET",
        headers=list_headers,
        timeout=args.timeout,
    )
    if status == 200 and payload.get("success") is True:
        export_ok = True
        export_decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
        if export_decisions:
            first_export = export_decisions[0] if isinstance(export_decisions[0], dict) else {}
            export_lineage = first_export.get("delegation_lineage") if isinstance(first_export.get("delegation_lineage"), dict) else {}
            lineage_export_ok = _lineage_snapshot_ok(export_lineage)
    loop_a_steps.append({"step": "decision_export", "status": status, "at": _utc_now()})

    loop_b = {"ok": True, "skipped": True}
    if not args.skip_loop_b:
        env = os.environ.copy()
        env["LEMMA_BASE_URL"] = args.api_base.rstrip("/")
        loop_b = _run_loop_b_revoke_to_deny(revoke_script, env)

    result = {
        "created_at": _utc_now(),
        "api_base": args.api_base.rstrip("/"),
        "runtime_id": args.runtime_id,
        "org_id": args.org_id,
        "environment": args.environment,
        "root_type": args.root_type,
        "loop_a": {
            "ok": bool(
                allow_ok
                and export_ok
                and (explain_ok or not decisions)
                and (lineage_explain_ok or not decisions)
                and (lineage_export_ok or not decisions)
            ),
            "allow_ok": allow_ok,
            "export_ok": export_ok,
            "explain_ok": explain_ok or not decisions,
            "lineage_explain_ok": lineage_explain_ok or not decisions,
            "lineage_export_ok": lineage_export_ok or not decisions,
            "decision_count": len(decisions),
            "reason_code": reason_code,
            "request_correlation_id": correlation_id,
            "steps": loop_a_steps,
        },
        "loop_b": loop_b,
    }
    result["ok"] = bool(result["loop_a"]["ok"] and loop_b.get("ok", True))

    json_path = output_dir / f"{stamp}-agent-ops-pov-loops.json"
    md_path = output_dir / f"{stamp}-agent-ops-pov-loops.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Agent Ops PoV Loops",
        "",
        f"- Base URL: {result['api_base']}",
        f"- Runtime: `{args.runtime_id}`",
        f"- Tenant: `{args.org_id}/{args.environment}` root `{args.root_type}`",
        f"- Loop A (allow/explain/export): `{'PASS' if result['loop_a']['ok'] else 'FAIL'}`",
        f"- Loop B (containment revoke->deny): `{'PASS' if loop_b.get('ok', False) else ('SKIP' if loop_b.get('skipped') else 'FAIL')}`",
        f"- Overall: `{'PASS' if result['ok'] else 'FAIL'}`",
        "",
        "## Explainability snapshot",
        "",
        f"- reason_code: `{result['loop_a'].get('reason_code') or 'n/a'}`",
        f"- request_correlation_id: `{result['loop_a'].get('request_correlation_id') or 'n/a'}`",
        f"- lineage_explain_ok: `{result['loop_a'].get('lineage_explain_ok')}`",
        f"- lineage_export_ok: `{result['loop_a'].get('lineage_export_ok')}`",
        "",
        f"- JSON artifact: `{json_path}`",
    ]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"pov_loops_json={json_path}")
    print(f"pov_loops_md={md_path}")
    print(f"pov_loops_result={'PASS' if result['ok'] else 'FAIL'}")
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded Agent Ops PoV loops and emit deterministic artifacts.")
    parser.add_argument("--api-base", default="https://lemma.id")
    parser.add_argument("--runtime-id", default="lemma-firewall-default")
    parser.add_argument("--proof-file", default=".lemma-proof.json")
    parser.add_argument("--org-id", default=os.getenv("LEMMA_ORG_ID", "org_default"))
    parser.add_argument("--environment", default=os.getenv("LEMMA_ENVIRONMENT", "prod"))
    parser.add_argument("--root-type", default=os.getenv("LEMMA_ROOT_TYPE", "passkey_root"))
    parser.add_argument("--action", default="api.internal.read")
    parser.add_argument("--output-dir", default="docs/launch-evidence")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--skip-loop-b", action="store_true")
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except Exception as exc:
        print(f"pov_loops_result=FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1) from exc
