#!/usr/bin/env python3
"""
Run Lemma latency gate and emit timestamped evidence.

This wrapper executes `lemma authz-latency` in JSON mode, captures the result,
writes an evidence artifact, and exits non-zero when a configured budget fails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run authz/e2e latency gate and write evidence artifact")
    parser.add_argument("--base-url", default="https://lemma.id")
    parser.add_argument("--agent-token", default="")
    parser.add_argument("--auth-mode", choices=["auto", "token", "proof"], default="auto")
    parser.add_argument("--proof", default="")
    parser.add_argument("--proof-file", default="")
    parser.add_argument("--pop", default="")
    parser.add_argument("--pop-file", default="")
    parser.add_argument("--pop-agent-key-id", default="lemma-cli")
    parser.add_argument("--decision-probe-path", default="/api/developer/sites")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--authz-budget-p95-ms", type=float, default=5.0)
    parser.add_argument("--e2e-budget-p95-ms", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output-path", default="")
    parser.add_argument("--output-dir", default="ops/evidence/launch")
    parser.add_argument("--label", default="post-deploy-authz-latency")
    return parser.parse_args()


def _run_cli_gate(args: argparse.Namespace) -> tuple[int, dict[str, Any], str]:
    command = [
        sys.executable,
        "scripts/lemma_cli.py",
        "authz-latency",
        "--api-base",
        str(args.base_url),
        "--auth-mode",
        str(args.auth_mode),
        "--decision-probe-path",
        str(args.decision_probe_path),
        "--requests",
        str(int(args.requests)),
        "--warmup",
        str(int(args.warmup)),
        "--budget-p95-ms",
        str(float(args.authz_budget_p95_ms)),
        "--e2e-budget-p95-ms",
        str(float(args.e2e_budget_p95_ms)),
        "--timeout",
        str(float(args.timeout)),
        "--json",
    ]
    if str(args.agent_token or "").strip():
        command.extend(["--agent-token", str(args.agent_token)])
    if str(args.proof or "").strip():
        command.extend(["--proof", str(args.proof)])
    if str(args.proof_file or "").strip():
        command.extend(["--proof-file", str(args.proof_file)])
    if str(args.pop or "").strip():
        command.extend(["--pop", str(args.pop)])
    if str(args.pop_file or "").strip():
        command.extend(["--pop-file", str(args.pop_file)])
    if str(args.pop_agent_key_id or "").strip():
        command.extend(["--pop-agent-key-id", str(args.pop_agent_key_id)])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout = (completed.stdout or "").strip()
    payload = json.loads(stdout) if stdout else {}
    return completed.returncode, payload if isinstance(payload, dict) else {}, " ".join(command)


def _build_output_path(args: argparse.Namespace) -> Path:
    if args.output_path:
        return Path(args.output_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M%S", time.gmtime())
    return output_dir / f"{stamp}-{args.label}.json"


def main() -> int:
    args = _parse_args()
    if (
        not str(args.agent_token or "").strip()
        and not str(args.proof or "").strip()
        and not str(args.proof_file or "").strip()
    ):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_auth_input",
                    "message": "Provide --agent-token or --proof/--proof-file for latency gate auth.",
                },
                indent=2,
            )
        )
        return 1
    exit_code, cli_payload, command_text = _run_cli_gate(args)
    output_path = _build_output_path(args)
    artifact = {
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": str(args.base_url),
        "decision_probe_path": str(args.decision_probe_path),
        "authz_budget_p95_ms": float(args.authz_budget_p95_ms),
        "e2e_budget_p95_ms": float(args.e2e_budget_p95_ms),
        "command": command_text,
        "cli_exit_code": int(exit_code),
        "cli_result": cli_payload,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "ok": bool(exit_code == 0),
            "artifact": str(output_path),
            "authz_p95_ms": (cli_payload or {}).get("authz_p95_ms"),
            "e2e_p95_ms": (cli_payload or {}).get("p95_ms"),
            "authz_budget_passed": (cli_payload or {}).get("budget_passed"),
            "e2e_budget_passed": (cli_payload or {}).get("e2e_budget_passed"),
        },
        indent=2,
    ))
    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
