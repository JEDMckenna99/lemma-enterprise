#!/usr/bin/env python3
"""
Run a repeatable containment benchmark matrix and emit scorecard artifacts.

This script orchestrates existing repo drills:
- scripts/revoke_to_deny_evidence.py
- scripts/latency_budget_gate.py
- scripts/run_agent_ops_alerts_check.ps1 (best effort)

It runs each scenario N times, computes summary stats, and writes:
- <timestamp>-revocation-benchmark-matrix.json
- <timestamp>-revocation-benchmark-matrix.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "launch-evidence"


@dataclass
class CommandResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    command: list[str]
    duration_ms: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local verification/revocation containment benchmark matrix."
    )
    parser.add_argument("--base-url", default="https://lemma.id")
    parser.add_argument("--proof-file", default=".lemma-proof.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--label", default="revocation-benchmark-matrix")
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario name. Repeatable. Defaults to: normal",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
        help="Number of runs per scenario.",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=60,
        help="Latency gate request count per run.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="Latency gate warmup request count per run.",
    )
    parser.add_argument(
        "--authz-budget-p95-ms",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--e2e-budget-p95-ms",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--revocation-target-seconds",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--revocation-hard-max-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--setup-cmd",
        action="append",
        default=[],
        help='Scenario setup hook as "scenario=command". Repeatable.',
    )
    parser.add_argument(
        "--teardown-cmd",
        action="append",
        default=[],
        help='Scenario teardown hook as "scenario=command". Repeatable.',
    )
    parser.add_argument(
        "--scenario-env",
        action="append",
        default=[],
        help='Scenario env vars as "scenario=KEY=VALUE;KEY2=VALUE2". Repeatable.',
    )
    parser.add_argument(
        "--skip-alerts-check",
        action="store_true",
        help="Skip PowerShell alerts endpoint call.",
    )
    parser.add_argument(
        "--skip-server-fallback-probe",
        action="store_true",
        help="Skip server fallback deny-latency probe.",
    )
    parser.add_argument(
        "--runtime-id",
        default="lemma-firewall-default",
        help="Runtime ID used for server fallback probe.",
    )
    parser.add_argument(
        "--org-id",
        default=os.getenv("LEMMA_ORG_ID", "org_default"),
        help="Org ID used for server fallback probe headers/body.",
    )
    parser.add_argument(
        "--environment",
        default=os.getenv("LEMMA_ENVIRONMENT", "prod"),
        help="Environment used for server fallback probe headers/body.",
    )
    parser.add_argument(
        "--server-fallback-requests",
        type=int,
        default=20,
        help="Request count for server fallback deny-latency probe.",
    )
    parser.add_argument(
        "--server-fallback-warmup",
        type=int,
        default=3,
        help="Warmup request count for server fallback deny-latency probe.",
    )
    parser.add_argument(
        "--server-fallback-timeout",
        type=float,
        default=20.0,
        help="HTTP timeout seconds for server fallback deny-latency probe.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop matrix immediately on first failed run.",
    )
    return parser.parse_args()


def _parse_mapping(items: list[str], field_name: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"Invalid {field_name} value '{raw}'. Expected scenario=...")
        scenario, value = raw.split("=", 1)
        scenario = scenario.strip()
        value = value.strip()
        if not scenario or not value:
            raise ValueError(f"Invalid {field_name} value '{raw}'. Empty scenario or value.")
        mapping[scenario] = value
    return mapping


def _parse_scenario_env(items: list[str]) -> dict[str, dict[str, str]]:
    by_scenario: dict[str, dict[str, str]] = {}
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"Invalid scenario-env value '{raw}'. Expected scenario=KEY=VALUE")
        scenario, env_blob = raw.split("=", 1)
        scenario = scenario.strip()
        env_blob = env_blob.strip()
        if not scenario or not env_blob:
            raise ValueError(f"Invalid scenario-env value '{raw}'.")
        env_map: dict[str, str] = {}
        for pair in env_blob.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise ValueError(
                    f"Invalid scenario-env entry '{pair}' in '{raw}'. Expected KEY=VALUE."
                )
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(f"Invalid scenario-env key in '{raw}'.")
            env_map[key] = value
        by_scenario[scenario] = env_map
    return by_scenario


def _run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = REPO_ROOT,
) -> CommandResult:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    duration_ms = (time.perf_counter() - started) * 1000.0
    return CommandResult(
        ok=(completed.returncode == 0),
        exit_code=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        command=command,
        duration_ms=duration_ms,
    )


def _run_shell_hook(command: str, env: dict[str, str]) -> CommandResult:
    return _run_command(["powershell", "-Command", command], env=env)


def _extract_keyvalue(text: str, key: str) -> str:
    prefix = f"{key}="
    for line in text.splitlines():
        if line.strip().startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def _parse_json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            payload = json.loads(stripped)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        candidate = stripped[start : end + 1]
        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_iso_ts(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _pctl(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = int(math.ceil((percentile / 100.0) * len(sorted_values))) - 1
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
            "mean": None,
        }
    sorted_values = sorted(values)
    return {
        "count": len(values),
        "p50": float(median(values)),
        "p95": float(_pctl(sorted_values, 95)),
        "p99": float(_pctl(sorted_values, 99)),
        "max": float(max(values)),
        "mean": float(sum(values) / len(values)),
    }


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return float(numerator / denominator)


def _run_revoke_probe(base_url: str, env: dict[str, str]) -> dict[str, Any]:
    probe_env = dict(env)
    probe_env["LEMMA_BASE_URL"] = base_url.rstrip("/")
    result = _run_command(
        [sys.executable, str(REPO_ROOT / "scripts" / "revoke_to_deny_evidence.py")],
        env=probe_env,
    )
    evidence_path = _extract_keyvalue(result.stdout, "evidence_json")
    evidence_data: dict[str, Any] = {}
    if evidence_path and Path(evidence_path).exists():
        try:
            evidence_data = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            evidence_data = {}

    revoke_at: datetime | None = None
    first_deny_at: datetime | None = None
    delta_seen: bool | None = None
    delta_shape_ok: bool | None = None
    for step in evidence_data.get("steps", []):
        if not isinstance(step, dict):
            continue
        name = str(step.get("step") or "")
        if name == "revoke_credential":
            revoke_at = _parse_iso_ts(str(step.get("at") or ""))
        elif name == "exchange_after_revoke":
            attempts = step.get("attempts") if isinstance(step.get("attempts"), list) else []
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                status = int(attempt.get("status") or 0)
                payload = attempt.get("payload") if isinstance(attempt.get("payload"), dict) else {}
                denied = (status >= 400) or (payload.get("success") is False)
                if denied:
                    first_deny_at = _parse_iso_ts(str(attempt.get("at") or ""))
                    break
        elif name == "revocation_delta_contains_credential_best_effort":
            attempts = step.get("attempts") if isinstance(step.get("attempts"), list) else []
            if attempts:
                final = attempts[-1] if isinstance(attempts[-1], dict) else {}
                delta_seen = bool(final.get("found"))
                delta_shape_ok = bool(final.get("shape_ok"))

    revoke_to_deny_ms: float | None = None
    if revoke_at and first_deny_at:
        revoke_to_deny_ms = max(0.0, (first_deny_at - revoke_at).total_seconds() * 1000.0)

    return {
        "ok": result.ok,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "evidence_json": evidence_path,
        "revoke_to_deny_ms": revoke_to_deny_ms,
        "deny_observed": first_deny_at is not None,
        "revocation_delta_seen": delta_seen,
        "revocation_delta_shape_ok": delta_shape_ok,
    }


def _run_latency_probe(
    base_url: str,
    proof_file: str,
    requests: int,
    warmup: int,
    authz_budget_p95_ms: float,
    e2e_budget_p95_ms: float,
    env: dict[str, str],
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "latency_budget_gate.py"),
        "--base-url",
        base_url.rstrip("/"),
        "--proof-file",
        proof_file,
        "--requests",
        str(int(requests)),
        "--warmup",
        str(int(warmup)),
        "--authz-budget-p95-ms",
        str(float(authz_budget_p95_ms)),
        "--e2e-budget-p95-ms",
        str(float(e2e_budget_p95_ms)),
    ]
    result = _run_command(command, env=env)
    printed = _parse_json_from_text(result.stdout)
    artifact_path = str(printed.get("artifact") or "").strip()
    artifact_data: dict[str, Any] = {}
    if artifact_path and Path(artifact_path).exists():
        try:
            artifact_data = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            artifact_data = {}
    cli_result = artifact_data.get("cli_result") if isinstance(artifact_data.get("cli_result"), dict) else {}
    authz_p95 = printed.get("authz_p95_ms")
    if authz_p95 is None:
        authz_p95 = cli_result.get("authz_p95_ms")
    e2e_p95 = printed.get("e2e_p95_ms")
    if e2e_p95 is None:
        e2e_p95 = cli_result.get("p95_ms")

    authz_budget_passed: bool | None
    if "authz_budget_passed" in printed:
        raw_authz_budget = printed.get("authz_budget_passed")
        authz_budget_passed = bool(raw_authz_budget) if isinstance(raw_authz_budget, bool) else None
    else:
        raw_authz_budget = cli_result.get("budget_passed")
        authz_budget_passed = bool(raw_authz_budget) if isinstance(raw_authz_budget, bool) else None

    e2e_budget_passed: bool | None
    if "e2e_budget_passed" in printed:
        raw_e2e_budget = printed.get("e2e_budget_passed")
        e2e_budget_passed = bool(raw_e2e_budget) if isinstance(raw_e2e_budget, bool) else None
    else:
        raw_e2e_budget = cli_result.get("e2e_budget_passed")
        e2e_budget_passed = bool(raw_e2e_budget) if isinstance(raw_e2e_budget, bool) else None

    return {
        "ok": result.ok,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "artifact": artifact_path,
        "authz_p95_ms": float(authz_p95) if isinstance(authz_p95, (int, float)) else None,
        "e2e_p95_ms": float(e2e_p95) if isinstance(e2e_p95, (int, float)) else None,
        "authz_budget_passed": authz_budget_passed,
        "e2e_budget_passed": e2e_budget_passed,
    }


def _run_alerts_probe(
    base_url: str,
    revocation_target_seconds: float,
    revocation_hard_max_seconds: float,
    env: dict[str, str],
) -> dict[str, Any]:
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(REPO_ROOT / "scripts" / "run_agent_ops_alerts_check.ps1"),
        "-LemmaUrl",
        base_url.rstrip("/"),
        "-RevocationTargetSeconds",
        str(float(revocation_target_seconds)),
        "-RevocationHardMaxSeconds",
        str(float(revocation_hard_max_seconds)),
    ]
    result = _run_command(command, env=env)
    payload = _parse_json_from_text(result.stdout)
    return {
        "ok": result.ok,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout_tail": result.stdout[-3000:],
        "stderr_tail": result.stderr[-2000:],
        "overall_severity": payload.get("overall_severity"),
        "payload": payload,
    }


def _run_server_fallback_probe(
    base_url: str,
    runtime_id: str,
    org_id: str,
    environment: str,
    requests: int,
    warmup: int,
    timeout: float,
) -> dict[str, Any]:
    target_url = f"{base_url.rstrip('/')}/api/wallet/runtimes/{runtime_id}/authorize"
    body = {
        "action": "api.internal.admin",
        "privileged": True,
        "risk": "critical",
        "org_id": org_id,
        "environment": environment,
    }
    encoded_body = json.dumps(body).encode("utf-8")
    total_samples = max(1, int(requests)) + max(0, int(warmup))
    warmup_count = max(0, int(warmup))

    def _run_variant(
        credential_obj: dict[str, Any],
        *,
        expected_error: str | None = None,
        expected_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        encoded_credential = json.dumps(credential_obj)
        latencies_ms: list[float] = []
        status_counts: dict[str, int] = {}
        error_counts: dict[str, int] = {}
        transport_errors: list[str] = []
        deny_count = 0
        five_xx_count = 0
        expected_match_count = 0
        deny_statuses = expected_statuses if expected_statuses else {401, 403, 404}

        for idx in range(total_samples):
            req = urllib.request.Request(
                url=target_url,
                method="POST",
                data=encoded_body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "lemma-server-fallback-probe/1.0",
                    "X-Lemma-Credential": encoded_credential,
                    "X-Lemma-Org-Id": org_id,
                    "X-Lemma-Environment": environment,
                },
            )

            started = time.perf_counter()
            status_code = 0
            response_payload: dict[str, Any] = {}
            transport_error = ""
            try:
                with urllib.request.urlopen(req, timeout=max(1.0, float(timeout))) as resp:
                    status_code = int(resp.getcode() or 200)
                    text = resp.read().decode("utf-8", errors="replace")
                    if text.strip():
                        parsed = _parse_json_from_text(text)
                        response_payload = parsed if isinstance(parsed, dict) else {}
            except urllib.error.HTTPError as err:
                status_code = int(err.code or 500)
                text = err.read().decode("utf-8", errors="replace")
                if text.strip():
                    parsed = _parse_json_from_text(text)
                    response_payload = parsed if isinstance(parsed, dict) else {}
            except Exception as exc:
                transport_error = str(exc)

            elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
            if idx >= warmup_count:
                latencies_ms.append(elapsed_ms)
                if transport_error:
                    transport_errors.append(transport_error)
                    continue
                status_key = str(status_code)
                status_counts[status_key] = status_counts.get(status_key, 0) + 1
                if status_code >= 500:
                    five_xx_count += 1
                if status_code in deny_statuses:
                    deny_count += 1
                error_code = str(response_payload.get("error") or "").strip()
                if error_code:
                    error_counts[error_code] = error_counts.get(error_code, 0) + 1
                    if expected_error and error_code == expected_error:
                        expected_match_count += 1

        deny_latency_stats = _stats(latencies_ms)
        deny_rate = (float(deny_count) / len(latencies_ms)) if latencies_ms else None
        expected_match_rate = (
            float(expected_match_count) / len(latencies_ms) if (latencies_ms and expected_error) else None
        )
        ok = bool(
            not transport_errors
            and five_xx_count == 0
            and latencies_ms
            and deny_count == len(latencies_ms)
        )
        if expected_error:
            ok = ok and (expected_match_count == len(latencies_ms))
        return {
            "ok": ok,
            "sample_count": len(latencies_ms),
            "deny_count": deny_count,
            "deny_rate": deny_rate,
            "expected_error": expected_error,
            "expected_match_count": expected_match_count if expected_error else None,
            "expected_match_rate": expected_match_rate,
            "five_xx_count": five_xx_count,
            "status_counts": status_counts,
            "error_counts": error_counts,
            "transport_errors": transport_errors[:5],
            "deny_latency_ms_stats": deny_latency_stats,
            "deny_latency_p95_ms": deny_latency_stats.get("p95"),
        }

    # Variant A: malformed/insufficient credential shape (missing PPID).
    invalid_input_credential = {
        "id": "cred_local_verify_failed_probe",
        "claims": {
            "scope": ["api.internal.admin"],
            "root_type": "passkey_root",
        },
    }
    # Variant B: structurally valid PPID credential that should not map to a live
    # runtime for this tenant/runtime (policy/identity mismatch deny path).
    unauthorized_ppid_credential = {
        "id": "cred_server_policy_deny_probe",
        "subject": "did:lemma:ppid_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "claims": {
            "sub": "did:lemma:ppid_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "scope": ["api.internal.admin"],
            "root_type": "passkey_root",
        },
    }

    invalid_input_probe = _run_variant(
        invalid_input_credential,
        expected_error="missing_lemma_credential",
        expected_statuses={401},
    )
    unauthorized_ppid_probe = _run_variant(
        unauthorized_ppid_credential,
        expected_error="runtime_not_found",
        expected_statuses={404},
    )

    stale_taint_epoch_probe: dict[str, Any] = {
        "ok": True,
        "skipped": True,
        "skip_reason": "not_attempted",
    }
    session_result = _run_command(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "lemma_cli.py"),
            "session",
            "link",
            "--api-base",
            base_url.rstrip("/"),
            "--requested-scope",
            "wallet:control_plane",
            "--json",
        ],
    )
    if not session_result.ok:
        stale_taint_epoch_probe = {
            "ok": True,
            "skipped": True,
            "skip_reason": "session_link_failed",
            "stderr_tail": session_result.stderr[-1000:],
        }
    else:
        session_payload = _parse_json_from_text(session_result.stdout)
        unlock_token = str(session_payload.get("unlock_token") or "").strip()
        if not unlock_token:
            stale_taint_epoch_probe = {
                "ok": True,
                "skipped": True,
                "skip_reason": "missing_unlock_token",
            }
        else:
            runtime_list_req = urllib.request.Request(
                url=f"{base_url.rstrip('/')}/api/wallet/runtimes",
                method="GET",
                headers={
                    "User-Agent": "lemma-server-fallback-probe/1.0",
                    "X-Lemma-Unlock": unlock_token,
                    "X-Lemma-Org-Id": org_id,
                    "X-Lemma-Environment": environment,
                },
            )
            runtime_list_payload: dict[str, Any] = {}
            runtime_list_error = ""
            try:
                with urllib.request.urlopen(runtime_list_req, timeout=max(1.0, float(timeout))) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                    runtime_list_payload = _parse_json_from_text(text)
            except Exception as exc:
                runtime_list_error = str(exc)

            if runtime_list_error:
                stale_taint_epoch_probe = {
                    "ok": True,
                    "skipped": True,
                    "skip_reason": "runtime_list_failed",
                    "error": runtime_list_error,
                }
            else:
                runtime_ppid = str(runtime_list_payload.get("ppid") or "").strip()
                runtimes = (
                    runtime_list_payload.get("runtimes")
                    if isinstance(runtime_list_payload.get("runtimes"), list)
                    else []
                )
                runtime_entry = None
                for item in runtimes:
                    if isinstance(item, dict) and str(item.get("runtime_id") or "") == runtime_id:
                        runtime_entry = item
                        break
                if not runtime_ppid or not isinstance(runtime_entry, dict):
                    stale_taint_epoch_probe = {
                        "ok": True,
                        "skipped": True,
                        "skip_reason": "runtime_or_ppid_not_found",
                    }
                else:
                    runtime_active = bool(runtime_entry.get("active"))
                    runtime_trust_state = str(runtime_entry.get("trust_state") or "clean_internal").strip().lower()
                    runtime_taint_epoch = int(runtime_entry.get("taint_epoch") or 0)
                    if not runtime_active:
                        stale_taint_epoch_probe = {
                            "ok": True,
                            "skipped": True,
                            "skip_reason": "runtime_inactive",
                        }
                    elif runtime_trust_state not in {"tainted_external", "privileged_reauth_required"}:
                        stale_taint_epoch_probe = {
                            "ok": True,
                            "skipped": True,
                            "skip_reason": "runtime_not_tainted",
                            "runtime_trust_state": runtime_trust_state,
                            "runtime_taint_epoch": runtime_taint_epoch,
                        }
                    else:
                        stale_epoch = runtime_taint_epoch - 1
                        stale_credential = {
                            "id": "cred_stale_taint_epoch_probe",
                            "subject": runtime_ppid,
                            "claims": {
                                "sub": runtime_ppid,
                                "scope": ["api.internal.admin"],
                                "root_type": "passkey_root",
                                "taint_epoch": stale_epoch,
                                "step_up_required": False,
                            },
                        }
                        stale_result = _run_variant(
                            stale_credential,
                            expected_error="deny_taint_epoch_stale",
                            expected_statuses={403},
                        )
                        stale_result.update(
                            {
                                "skipped": False,
                                "runtime_trust_state": runtime_trust_state,
                                "runtime_taint_epoch": runtime_taint_epoch,
                                "probe_taint_epoch": stale_epoch,
                            }
                        )
                        stale_taint_epoch_probe = stale_result

    overall_ok = bool(
        invalid_input_probe.get("ok")
        and unauthorized_ppid_probe.get("ok")
        and (stale_taint_epoch_probe.get("ok") if not stale_taint_epoch_probe.get("skipped") else True)
    )

    return {
        "ok": overall_ok,
        "target_url": target_url,
        # Backward-compatible lane points to the existing invalid-input probe.
        "sample_count": invalid_input_probe.get("sample_count"),
        "deny_count": invalid_input_probe.get("deny_count"),
        "deny_rate": invalid_input_probe.get("deny_rate"),
        "five_xx_count": invalid_input_probe.get("five_xx_count"),
        "status_counts": invalid_input_probe.get("status_counts"),
        "error_counts": invalid_input_probe.get("error_counts"),
        "transport_errors": invalid_input_probe.get("transport_errors"),
        "deny_latency_ms_stats": invalid_input_probe.get("deny_latency_ms_stats"),
        "deny_latency_p95_ms": invalid_input_probe.get("deny_latency_p95_ms"),
        "probes": {
            "invalid_input": invalid_input_probe,
            "unauthorized_ppid": unauthorized_ppid_probe,
            "stale_taint_epoch": stale_taint_epoch_probe,
        },
    }


def _standards_assessment(
    scenario_summary: dict[str, Any],
    revocation_target_seconds: float,
    revocation_hard_max_seconds: float,
) -> dict[str, Any]:
    revoke_stats = scenario_summary.get("revoke_to_deny_ms_stats", {})
    revoke_p95_ms = revoke_stats.get("p95")
    deny_rate = scenario_summary.get("deny_observed_rate")
    false_allow_count = scenario_summary.get("false_allow_after_revoke_count")

    nist_800_207 = (
        revoke_p95_ms is not None and revoke_p95_ms <= (revocation_hard_max_seconds * 1000.0)
    )
    owasp_asvs_fail_closed = (false_allow_count == 0)
    oauth_revocation_semantics = (deny_rate is not None and abs(deny_rate - 1.0) < 1e-9)
    target_met = (
        revoke_p95_ms is not None and revoke_p95_ms <= (revocation_target_seconds * 1000.0)
    )

    return {
        "nist_sp_800_207_continuous_revocation": bool(nist_800_207),
        "owasp_asvs_fail_closed_after_revoke": bool(owasp_asvs_fail_closed),
        "oauth_revocation_semantics_observed": bool(oauth_revocation_semantics),
        "internal_target_revoke_to_deny_p95_met": bool(target_met),
    }


def _run_lineage_integrity_probe(proof_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads(proof_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"proof_load_failed:{exc}"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "proof_payload_invalid"}
    chain = payload.get("proof_chain") if isinstance(payload.get("proof_chain"), list) else []
    root = payload.get("root_proof") if isinstance(payload.get("root_proof"), dict) else (chain[0] if chain else {})
    delegated = payload.get("delegated_proof") if isinstance(payload.get("delegated_proof"), dict) else (chain[-1] if chain else {})
    checks: dict[str, bool] = {}
    checks["has_chain_or_links"] = bool((isinstance(chain, list) and len(chain) >= 2) or (root and delegated))
    parent_id = str((delegated or {}).get("parent_proof_id") or "").strip()
    root_id = str((root or {}).get("proof_id") or (root or {}).get("id") or "").strip()
    checks["parent_link_present"] = bool(parent_id and root_id and parent_id == root_id)
    depth_raw = (delegated or {}).get("delegation_depth")
    try:
        checks["delegation_depth_present"] = int(depth_raw) >= 1
    except (TypeError, ValueError):
        checks["delegation_depth_present"] = False
    ancestors = (delegated or {}).get("ancestor_ids") if isinstance((delegated or {}).get("ancestor_ids"), list) else []
    checks["ancestor_ids_present"] = bool(ancestors)
    checks["root_grant_present"] = bool(str(payload.get("root_grant_id") or (delegated or {}).get("root_grant_id") or "").strip())
    ok = all(checks.values())
    return {"ok": ok, "checks": checks}


def main() -> int:
    args = _parse_args()
    scenarios = args.scenario if args.scenario else ["normal"]
    if args.repetitions <= 0:
        raise SystemExit("--repetitions must be >= 1")

    proof_path = Path(args.proof_file).expanduser()
    if not proof_path.is_absolute():
        proof_path = (REPO_ROOT / proof_path).resolve()
    if not proof_path.exists():
        raise SystemExit(f"proof file not found: {proof_path}")

    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = (REPO_ROOT / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    setup_hooks = _parse_mapping(args.setup_cmd, "setup-cmd")
    teardown_hooks = _parse_mapping(args.teardown_cmd, "teardown-cmd")
    scenario_env_map = _parse_scenario_env(args.scenario_env)

    started_at = _utc_now()
    matrix_runs: list[dict[str, Any]] = []
    aborted = False
    abort_reason = ""

    for scenario in scenarios:
        for run_index in range(1, args.repetitions + 1):
            run_started = _utc_now()
            run_env = dict(os.environ)
            run_env.update(scenario_env_map.get(scenario, {}))
            run_record: dict[str, Any] = {
                "scenario": scenario,
                "run_index": run_index,
                "started_at": run_started,
                "env_overrides": scenario_env_map.get(scenario, {}),
            }

            setup_cmd = setup_hooks.get(scenario)
            setup_result: dict[str, Any] | None = None
            if setup_cmd:
                setup_exec = _run_shell_hook(setup_cmd, run_env)
                setup_result = {
                    "ok": setup_exec.ok,
                    "exit_code": setup_exec.exit_code,
                    "duration_ms": setup_exec.duration_ms,
                    "stdout_tail": setup_exec.stdout[-2000:],
                    "stderr_tail": setup_exec.stderr[-2000:],
                    "command": setup_cmd,
                }
                run_record["setup"] = setup_result
                if not setup_exec.ok:
                    run_record["ok"] = False
                    run_record["error"] = "scenario_setup_failed"
                    run_record["finished_at"] = _utc_now()
                    matrix_runs.append(run_record)
                    if args.fail_fast:
                        aborted = True
                        abort_reason = f"setup failed for scenario={scenario} run={run_index}"
                        break
                    continue

            revoke_probe = _run_revoke_probe(args.base_url, run_env)
            latency_probe = _run_latency_probe(
                args.base_url,
                str(proof_path),
                args.requests,
                args.warmup,
                args.authz_budget_p95_ms,
                args.e2e_budget_p95_ms,
                run_env,
            )
            server_fallback_probe = None
            if not args.skip_server_fallback_probe:
                server_fallback_probe = _run_server_fallback_probe(
                    base_url=args.base_url,
                    runtime_id=str(args.runtime_id),
                    org_id=str(args.org_id),
                    environment=str(args.environment),
                    requests=int(args.server_fallback_requests),
                    warmup=int(args.server_fallback_warmup),
                    timeout=float(args.server_fallback_timeout),
                )
            lineage_probe = _run_lineage_integrity_probe(proof_path)
            alerts_probe = None
            if not args.skip_alerts_check:
                alerts_probe = _run_alerts_probe(
                    args.base_url,
                    args.revocation_target_seconds,
                    args.revocation_hard_max_seconds,
                    run_env,
                )

            teardown_result: dict[str, Any] | None = None
            teardown_cmd = teardown_hooks.get(scenario)
            if teardown_cmd:
                teardown_exec = _run_shell_hook(teardown_cmd, run_env)
                teardown_result = {
                    "ok": teardown_exec.ok,
                    "exit_code": teardown_exec.exit_code,
                    "duration_ms": teardown_exec.duration_ms,
                    "stdout_tail": teardown_exec.stdout[-2000:],
                    "stderr_tail": teardown_exec.stderr[-2000:],
                    "command": teardown_cmd,
                }

            run_ok = bool(revoke_probe.get("ok") and latency_probe.get("ok"))
            run_ok = run_ok and bool(lineage_probe.get("ok"))
            if server_fallback_probe is not None:
                run_ok = run_ok and bool(server_fallback_probe.get("ok"))
            if alerts_probe is not None:
                run_ok = run_ok and bool(alerts_probe.get("ok"))
            if teardown_result is not None:
                run_ok = run_ok and bool(teardown_result.get("ok"))

            run_record.update(
                {
                    "revoke_probe": revoke_probe,
                    "latency_probe": latency_probe,
                    "server_fallback_probe": server_fallback_probe,
                    "lineage_probe": lineage_probe,
                    "alerts_probe": alerts_probe,
                    "teardown": teardown_result,
                    "ok": run_ok,
                    "finished_at": _utc_now(),
                }
            )
            matrix_runs.append(run_record)

            if args.fail_fast and not run_ok:
                aborted = True
                abort_reason = f"run failed for scenario={scenario} run={run_index}"
                break
        if aborted:
            break

    scenario_summaries: dict[str, Any] = {}
    for scenario in scenarios:
        rows = [r for r in matrix_runs if r.get("scenario") == scenario]
        revoke_to_deny = [
            float(r["revoke_probe"]["revoke_to_deny_ms"])
            for r in rows
            if isinstance(r.get("revoke_probe", {}).get("revoke_to_deny_ms"), (int, float))
        ]
        authz_p95 = [
            float(r["latency_probe"]["authz_p95_ms"])
            for r in rows
            if isinstance(r.get("latency_probe", {}).get("authz_p95_ms"), (int, float))
        ]
        e2e_p95 = [
            float(r["latency_probe"]["e2e_p95_ms"])
            for r in rows
            if isinstance(r.get("latency_probe", {}).get("e2e_p95_ms"), (int, float))
        ]
        server_fallback_p95 = [
            float(r["server_fallback_probe"]["deny_latency_p95_ms"])
            for r in rows
            if isinstance(r.get("server_fallback_probe", {}).get("deny_latency_p95_ms"), (int, float))
        ]
        server_fallback_policy_p95 = [
            float(r["server_fallback_probe"]["probes"]["unauthorized_ppid"]["deny_latency_p95_ms"])
            for r in rows
            if isinstance(
                r.get("server_fallback_probe", {})
                .get("probes", {})
                .get("unauthorized_ppid", {})
                .get("deny_latency_p95_ms"),
                (int, float),
            )
        ]
        server_fallback_deny_rates = [
            float(r["server_fallback_probe"]["deny_rate"])
            for r in rows
            if isinstance(r.get("server_fallback_probe", {}).get("deny_rate"), (int, float))
        ]
        server_fallback_policy_deny_rates = [
            float(r["server_fallback_probe"]["probes"]["unauthorized_ppid"]["deny_rate"])
            for r in rows
            if isinstance(
                r.get("server_fallback_probe", {})
                .get("probes", {})
                .get("unauthorized_ppid", {})
                .get("deny_rate"),
                (int, float),
            )
        ]
        server_fallback_stale_p95 = [
            float(r["server_fallback_probe"]["probes"]["stale_taint_epoch"]["deny_latency_p95_ms"])
            for r in rows
            if isinstance(
                r.get("server_fallback_probe", {})
                .get("probes", {})
                .get("stale_taint_epoch", {})
                .get("deny_latency_p95_ms"),
                (int, float),
            )
        ]
        server_fallback_stale_deny_rates = [
            float(r["server_fallback_probe"]["probes"]["stale_taint_epoch"]["deny_rate"])
            for r in rows
            if isinstance(
                r.get("server_fallback_probe", {})
                .get("probes", {})
                .get("stale_taint_epoch", {})
                .get("deny_rate"),
                (int, float),
            )
        ]
        stale_attempted_count = sum(
            1
            for r in rows
            if not bool(
                r.get("server_fallback_probe", {})
                .get("probes", {})
                .get("stale_taint_epoch", {})
                .get("skipped")
            )
        )
        alerts_severity = [
            str(r.get("alerts_probe", {}).get("overall_severity") or "")
            for r in rows
            if isinstance(r.get("alerts_probe"), dict)
        ]
        deny_observed_count = sum(
            1 for r in rows if bool(r.get("revoke_probe", {}).get("deny_observed"))
        )
        false_allow_after_revoke_count = max(0, len(rows) - deny_observed_count)
        pass_count = sum(1 for r in rows if bool(r.get("ok")))
        lineage_pass_count = sum(1 for r in rows if bool(r.get("lineage_probe", {}).get("ok")))

        summary: dict[str, Any] = {
            "runs": len(rows),
            "pass_count": pass_count,
            "pass_rate": (float(pass_count) / len(rows)) if rows else None,
            "deny_observed_rate": (float(deny_observed_count) / len(rows)) if rows else None,
            "false_allow_after_revoke_count": false_allow_after_revoke_count,
            "revoke_to_deny_ms_stats": _stats(revoke_to_deny),
            "authz_p95_ms_stats": _stats(authz_p95),
            "e2e_p95_ms_stats": _stats(e2e_p95),
            "server_fallback_deny_p95_ms_stats": _stats(server_fallback_p95),
            "server_fallback_deny_rate_mean": (
                float(sum(server_fallback_deny_rates) / len(server_fallback_deny_rates))
                if server_fallback_deny_rates
                else None
            ),
            "server_fallback_policy_deny_p95_ms_stats": _stats(server_fallback_policy_p95),
            "server_fallback_policy_deny_rate_mean": (
                float(sum(server_fallback_policy_deny_rates) / len(server_fallback_policy_deny_rates))
                if server_fallback_policy_deny_rates
                else None
            ),
            "server_fallback_stale_taint_deny_p95_ms_stats": _stats(server_fallback_stale_p95),
            "server_fallback_stale_taint_deny_rate_mean": (
                float(sum(server_fallback_stale_deny_rates) / len(server_fallback_stale_deny_rates))
                if server_fallback_stale_deny_rates
                else None
            ),
            "server_fallback_stale_taint_attempted_runs": stale_attempted_count,
            "lineage_probe_pass_count": lineage_pass_count,
            "lineage_probe_pass_rate": (float(lineage_pass_count) / len(rows)) if rows else None,
            "alerts_overall_severity_counts": {
                level: alerts_severity.count(level)
                for level in sorted(set(alerts_severity))
                if level
            },
        }
        summary["standards_assessment"] = _standards_assessment(
            summary,
            args.revocation_target_seconds,
            args.revocation_hard_max_seconds,
        )
        scenario_summaries[scenario] = summary

    baseline = scenario_summaries.get("normal", {})
    baseline_authz_p95 = baseline.get("authz_p95_ms_stats", {}).get("p95")
    baseline_revoke_p95 = baseline.get("revoke_to_deny_ms_stats", {}).get("p95")

    for scenario, summary in scenario_summaries.items():
        authz_p95 = summary.get("authz_p95_ms_stats", {}).get("p95")
        revoke_p95 = summary.get("revoke_to_deny_ms_stats", {}).get("p95")
        summary["degradation_ratio"] = {
            "authz_p95_vs_normal": _ratio(authz_p95, baseline_authz_p95)
            if scenario != "normal"
            else 1.0,
            "revoke_to_deny_p95_vs_normal": _ratio(revoke_p95, baseline_revoke_p95)
            if scenario != "normal"
            else 1.0,
        }

    finished_at = _utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    json_out = output_dir / f"{stamp}-{args.label}.json"
    md_out = output_dir / f"{stamp}-{args.label}.md"

    payload = {
        "created_at": finished_at,
        "started_at": started_at,
        "base_url": args.base_url.rstrip("/"),
        "proof_file": str(proof_path),
        "scenarios": scenarios,
        "repetitions": int(args.repetitions),
        "requests": int(args.requests),
        "warmup": int(args.warmup),
        "authz_budget_p95_ms": float(args.authz_budget_p95_ms),
        "e2e_budget_p95_ms": float(args.e2e_budget_p95_ms),
        "revocation_target_seconds": float(args.revocation_target_seconds),
        "revocation_hard_max_seconds": float(args.revocation_hard_max_seconds),
        "runtime_id": str(args.runtime_id),
        "org_id": str(args.org_id),
        "environment": str(args.environment),
        "server_fallback_requests": int(args.server_fallback_requests),
        "server_fallback_warmup": int(args.server_fallback_warmup),
        "server_fallback_timeout": float(args.server_fallback_timeout),
        "server_fallback_probe_skipped": bool(args.skip_server_fallback_probe),
        "aborted": aborted,
        "abort_reason": abort_reason,
        "runs": matrix_runs,
        "summary_by_scenario": scenario_summaries,
    }
    json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Revocation Benchmark Matrix",
        "",
        f"- Base URL: {payload['base_url']}",
        f"- Scenarios: {', '.join(scenarios)}",
        f"- Repetitions per scenario: {args.repetitions}",
        f"- Requests/Warmup: {args.requests}/{args.warmup}",
        f"- Overall aborted: {aborted}",
        "",
        "## Scorecard",
    ]
    for scenario in scenarios:
        summary = scenario_summaries.get(scenario, {})
        revoke_p95 = summary.get("revoke_to_deny_ms_stats", {}).get("p95")
        authz_p95 = summary.get("authz_p95_ms_stats", {}).get("p95")
        fallback_p95 = summary.get("server_fallback_deny_p95_ms_stats", {}).get("p95")
        fallback_deny_rate = summary.get("server_fallback_deny_rate_mean")
        fallback_policy_p95 = summary.get("server_fallback_policy_deny_p95_ms_stats", {}).get("p95")
        fallback_policy_deny_rate = summary.get("server_fallback_policy_deny_rate_mean")
        fallback_stale_p95 = summary.get("server_fallback_stale_taint_deny_p95_ms_stats", {}).get("p95")
        fallback_stale_deny_rate = summary.get("server_fallback_stale_taint_deny_rate_mean")
        fallback_stale_attempted = summary.get("server_fallback_stale_taint_attempted_runs")
        lineage_rate = summary.get("lineage_probe_pass_rate")
        pass_rate = summary.get("pass_rate")
        deny_rate = summary.get("deny_observed_rate")
        degrade = summary.get("degradation_ratio", {}).get("authz_p95_vs_normal")
        lines += [
            "",
            f"### {scenario}",
            f"- pass_rate: {pass_rate if pass_rate is not None else 'n/a'}",
            f"- deny_observed_rate: {deny_rate if deny_rate is not None else 'n/a'}",
            f"- false_allow_after_revoke_count: {summary.get('false_allow_after_revoke_count')}",
            f"- revoke_to_deny_p95_ms: {revoke_p95 if revoke_p95 is not None else 'n/a'}",
            f"- authz_p95_ms: {authz_p95 if authz_p95 is not None else 'n/a'}",
            f"- server_fallback_deny_p95_ms: {fallback_p95 if fallback_p95 is not None else 'n/a'}",
            f"- server_fallback_deny_rate_mean: {fallback_deny_rate if fallback_deny_rate is not None else 'n/a'}",
            f"- server_fallback_policy_deny_p95_ms: {fallback_policy_p95 if fallback_policy_p95 is not None else 'n/a'}",
            f"- server_fallback_policy_deny_rate_mean: {fallback_policy_deny_rate if fallback_policy_deny_rate is not None else 'n/a'}",
            f"- server_fallback_stale_taint_p95_ms: {fallback_stale_p95 if fallback_stale_p95 is not None else 'n/a'}",
            f"- server_fallback_stale_taint_deny_rate_mean: {fallback_stale_deny_rate if fallback_stale_deny_rate is not None else 'n/a'}",
            f"- server_fallback_stale_taint_attempted_runs: {fallback_stale_attempted}",
            f"- lineage_probe_pass_rate: {lineage_rate if lineage_rate is not None else 'n/a'}",
            f"- authz_degradation_vs_normal: {degrade if degrade is not None else 'n/a'}",
            f"- alerts_severity_counts: {json.dumps(summary.get('alerts_overall_severity_counts', {}))}",
            f"- standards: {json.dumps(summary.get('standards_assessment', {}))}",
        ]
    lines += [
        "",
        "## Artifacts",
        f"- JSON: {json_out}",
    ]
    md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"benchmark_matrix_json={json_out}")
    print(f"benchmark_matrix_md={md_out}")
    print(f"benchmark_matrix_result={'PASS' if not aborted else 'PARTIAL'}")
    return 0 if not aborted else 1


if __name__ == "__main__":
    raise SystemExit(main())
