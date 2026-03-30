#!/usr/bin/env python3
"""
Lemma Firewall Containment Simulation

Runs 8 scenarios against the live control plane and local firewall
to validate the full agent containment loop end-to-end.

Prerequisites:
  - Firewall running locally: python scripts/lemma_firewall.py
  - Auth: credential issuance (preferred), agent token, or LEMMA_AGENT_TOKEN env var
  - Control plane live at LEMMA_BASE_URL (default https://lemma.id)

Usage:
  python scripts/run_containment_simulation.py
  python scripts/run_containment_simulation.py --api-base https://lemma.id --firewall-url http://localhost:8787
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SCENARIOS = [
    "credential_issuance",
    "firewall_health",
    "allowed_request",
    "denied_wrong_path",
    "denied_wrong_method",
    "taint_epoch_bump",
    "taint_state_verify",
    "final_health_taint_sync",
]


def _resolve_token(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    env_token = os.environ.get("LEMMA_AGENT_TOKEN", "").strip()
    if env_token:
        return env_token
    cli_auth = Path.home() / ".lemma" / "cli_auth.json"
    if cli_auth.exists():
        try:
            data = json.loads(cli_auth.read_text(encoding="utf-8"))
            return str(data.get("agent_token") or data.get("token") or "").strip() or None
        except Exception:
            pass
    return None


def _resolve_credential(api_base: str, runtime_id: str) -> dict | None:
    """Issue a signed credential via POST /api/demo/issue-credential."""
    try:
        resp = requests.post(
            f"{api_base}/api/demo/issue-credential",
            json={"runtime_id": runtime_id, "scope": ["read", "write"]},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            body = resp.json()
            return body.get("credential") or body
        return None
    except Exception:
        return None


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _run_scenario(name: str, fn, results: list[dict]) -> bool:
    start_ms = time.time() * 1000
    try:
        passed, detail = fn()
    except Exception as exc:
        passed, detail = False, {"error": str(exc), "exception": type(exc).__name__}
    elapsed_ms = round(time.time() * 1000 - start_ms)
    status = "PASS" if passed else "FAIL"
    results.append({
        "scenario": name,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "detail": detail,
    })
    label = f"  {name}"
    dots = "." * max(1, 42 - len(label))
    print(f"{label} {dots} {status}  ({elapsed_ms}ms)")
    return passed


def s1_credential_issuance(api_base: str, runtime_id: str) -> tuple[bool, dict]:
    """Issue a signed credential via POST /api/demo/issue-credential."""
    try:
        resp = requests.post(
            f"{api_base}/api/demo/issue-credential",
            json={"runtime_id": runtime_id, "scope": ["read", "write"]},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        body = resp.json() if resp.content else {}
        credential = body.get("credential") or body
        issued = resp.status_code == 200 and bool(credential)
        return issued, {
            "status_code": resp.status_code,
            "issued": issued,
            "credential_type": credential.get("type") if isinstance(credential, dict) else None,
            "runtime_id": runtime_id,
        }
    except Exception as exc:
        return False, {"error": str(exc), "issued": False}


def s2_firewall_health(firewall_url: str) -> tuple[bool, dict]:
    resp = requests.get(f"{firewall_url}/aim/health", timeout=10)
    body = resp.json() if resp.content else {}
    ok = resp.status_code == 200 and body.get("ok") is True
    sync = body.get("sync", {})
    return ok, {
        "status_code": resp.status_code,
        "sync_enabled": sync.get("enabled"),
        "last_revocation_sync_ms": sync.get("last_revocation_sync_ms"),
        "last_taint_sync_ms": sync.get("last_taint_sync_ms"),
        "taint_enforcement_enabled": body.get("taint_enforcement_enabled"),
    }


def s3_allowed_request(firewall_url: str, token: str, has_token: bool, credential: dict | None = None) -> tuple[bool, dict]:
    if has_token:
        headers = {"X-Agent-Token": token}
    elif credential:
        headers = {"X-Lemma-Credential": json.dumps(credential)}
    else:
        headers = {}
    resp = requests.get(
        f"{firewall_url}/firewall/httpbin/get",
        headers=headers,
        timeout=15,
    )
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:200]}
    if has_token or credential:
        passed = resp.status_code == 200
        return passed, {
            "status_code": resp.status_code,
            "upstream_reached": passed,
            "mode": "token_auth" if has_token else "credential_auth",
            "response_keys": list(body.keys()) if isinstance(body, dict) else None,
        }
    else:
        passed = resp.status_code in (401, 403)
        return passed, {
            "status_code": resp.status_code,
            "mode": "no_auth_deny_expected",
            "error": body.get("error") if isinstance(body, dict) else None,
            "note": "No auth: firewall correctly denies unauthenticated requests",
        }


def s4_denied_wrong_path(firewall_url: str, token: str, has_token: bool = True, credential: dict | None = None) -> tuple[bool, dict]:
    if has_token:
        headers = {"X-Agent-Token": token}
    elif credential:
        headers = {"X-Lemma-Credential": json.dumps(credential)}
    else:
        headers = {}
    resp = requests.get(
        f"{firewall_url}/firewall/httpbin/admin/secret",
        headers=headers,
        timeout=10,
    )
    body = resp.json() if resp.content else {}
    passed = resp.status_code == 403 and "path_not_allowed" in str(body.get("error", ""))
    return passed, {
        "status_code": resp.status_code,
        "error": body.get("error"),
        "expected_403": True,
    }


def s5_denied_wrong_method(firewall_url: str, token: str, has_token: bool = True, credential: dict | None = None) -> tuple[bool, dict]:
    if has_token:
        headers = {"X-Agent-Token": token}
    elif credential:
        headers = {"X-Lemma-Credential": json.dumps(credential)}
    else:
        headers = {}
    resp = requests.delete(
        f"{firewall_url}/firewall/httpbin/get",
        headers=headers,
        timeout=10,
    )
    body = resp.json() if resp.content else {}
    passed = resp.status_code == 403 and "method_not_allowed" in str(body.get("error", ""))
    return passed, {
        "status_code": resp.status_code,
        "error": body.get("error"),
        "expected_403": True,
    }


def s6_taint_epoch_bump(api_base: str, runtime_id: str) -> tuple[bool, dict]:
    resp = requests.post(
        f"{api_base}/api/demo/taint-bump",
        json={"runtime_id": runtime_id, "trust_state": "tainted_external"},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    body = resp.json() if resp.content else {}
    passed = resp.status_code == 200 and body.get("success") is True
    runtime_state = body.get("runtime_state", {})
    return passed, {
        "status_code": resp.status_code,
        "success": body.get("success"),
        "taint_epoch": runtime_state.get("taint_epoch"),
        "trust_state": runtime_state.get("trust_state"),
        "event": body.get("event"),
    }


def s7_taint_state_verify(api_base: str, runtime_id: str) -> tuple[bool, dict]:
    """Verify taint state changed. Retries to handle multi-worker deployments."""
    for attempt in range(4):
        resp = requests.get(
            f"{api_base}/api/demo/state",
            params={"runtime_id": runtime_id},
            timeout=10,
        )
        body = resp.json() if resp.content else {}
        state = body.get("runtime_state", body)
        taint_epoch = int(state.get("taint_epoch") or 0)
        trust_state = str(state.get("trust_state") or "")
        if resp.status_code == 200 and taint_epoch > 0:
            return True, {
                "status_code": resp.status_code,
                "taint_epoch": taint_epoch,
                "trust_state": trust_state,
                "verified": True,
                "attempts": attempt + 1,
            }
        if attempt < 3:
            time.sleep(1)
    return False, {
        "status_code": resp.status_code,
        "taint_epoch": taint_epoch,
        "trust_state": trust_state,
        "verified": False,
        "attempts": 4,
        "note": "Multi-worker deployment may serve state from different workers",
    }


def s8_final_health_taint_sync(firewall_url: str, runtime_id: str) -> tuple[bool, dict]:
    """Wait up to 15s for the firewall to pick up the taint epoch via background sync."""
    for attempt in range(6):
        resp = requests.get(f"{firewall_url}/aim/health", timeout=10)
        body = resp.json() if resp.content else {}
        sync = body.get("sync", {})
        taint_epochs = sync.get("runtime_taint_epochs", {})
        runtime_epoch = int(taint_epochs.get(runtime_id, 0))
        if runtime_epoch > 0:
            return True, {
                "status_code": resp.status_code,
                "runtime_taint_epoch_synced": runtime_epoch,
                "attempts": attempt + 1,
                "sync_confirmed": True,
            }
        if attempt < 5:
            time.sleep(3)
    return False, {
        "status_code": resp.status_code,
        "runtime_taint_epochs": taint_epochs,
        "attempts": 6,
        "sync_confirmed": False,
        "note": "Taint sync may need more time or taint sync endpoint may not be returning data",
    }


def _print_cost_profile(results: list[dict]) -> None:
    local_scenarios = ["allowed_request", "denied_wrong_path", "denied_wrong_method"]
    local_times = [r["elapsed_ms"] for r in results if r["scenario"] in local_scenarios]
    cp_scenarios = ["credential_issuance", "taint_epoch_bump", "taint_state_verify"]
    cp_times = [r["elapsed_ms"] for r in results if r["scenario"] in cp_scenarios]

    avg_local = round(sum(local_times) / len(local_times)) if local_times else 0
    avg_cp = round(sum(cp_times) / len(cp_times)) if cp_times else 0

    print("\n=== Cost Profile (based on measured latencies) ===")
    print(f"  Local firewall verify (per action):   ~{avg_local}ms  (no external API cost)")
    print(f"  Control plane round-trip (sync/auth):  ~{avg_cp}ms  (only for sync, not per-action)")
    print()
    print("  Estimated cost per 1,000 agent actions:")
    print("    Lemma Firewall (local-first):  $0.00  (local CPU only, sync is background)")
    print("    Centralized auth service:      $0.50-2.00  (1,000 API round-trips)")
    print("    Cloud IAM per-call:            $1.00-5.00  (metered API pricing)")
    print("    LLM-as-judge guardrail:        $0.10-0.50  (compute per evaluation)")


def main():
    parser = argparse.ArgumentParser(description="Lemma Firewall Containment Simulation")
    parser.add_argument("--api-base", default=os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/"))
    parser.add_argument("--firewall-url", default="http://localhost:8787")
    parser.add_argument("--token", default=None)
    parser.add_argument("--runtime-id", default=os.environ.get("LEMMA_FIREWALL_RUNTIME_ID", "lemma-firewall-demo-runtime"))
    parser.add_argument("--evidence-dir", default=str(Path(__file__).resolve().parent.parent / "docs" / "launch-evidence"))
    args = parser.parse_args()

    token = _resolve_token(args.token)
    has_token = bool(token)
    credential = None

    if has_token:
        auth_mode = "token (server verify)"
    else:
        credential = _resolve_credential(args.api_base, args.runtime_id)
        if credential:
            auth_mode = "credential (local verify)"
        else:
            token = "simulation_no_token_placeholder"
            auth_mode = "none"
            print("WARNING: No agent token and credential issuance failed.")
            print("  Firewall auth scenarios will test deny behavior.")
            print("  For full simulation, provide --token, set LEMMA_AGENT_TOKEN, or run: lemma login")
            print()

    print("=== Lemma Firewall Containment Simulation ===")
    print(f"  Control plane:  {args.api_base}")
    print(f"  Firewall:       {args.firewall_url}")
    print(f"  Runtime:        {args.runtime_id}")
    print(f"  Auth mode:      {auth_mode}")
    if has_token:
        print(f"  Token:          {token[:12]}...{token[-4:]}")
    elif credential:
        print(f"  Credential:     issued (local verify)")
    else:
        print(f"  Token:          (none -- testing deny behavior)")
    print()

    results: list[dict] = []
    all_pass = True

    all_pass &= _run_scenario("credential_issuance", lambda: s1_credential_issuance(args.api_base, args.runtime_id), results)
    all_pass &= _run_scenario("firewall_health", lambda: s2_firewall_health(args.firewall_url), results)
    all_pass &= _run_scenario("allowed_request", lambda: s3_allowed_request(args.firewall_url, token, has_token, credential), results)
    all_pass &= _run_scenario("denied_wrong_path", lambda: s4_denied_wrong_path(args.firewall_url, token, has_token, credential), results)
    all_pass &= _run_scenario("denied_wrong_method", lambda: s5_denied_wrong_method(args.firewall_url, token, has_token, credential), results)
    all_pass &= _run_scenario("taint_epoch_bump", lambda: s6_taint_epoch_bump(args.api_base, args.runtime_id), results)
    all_pass &= _run_scenario("taint_state_verify", lambda: s7_taint_state_verify(args.api_base, args.runtime_id), results)
    all_pass &= _run_scenario("final_health_taint_sync", lambda: s8_final_health_taint_sync(args.firewall_url, args.runtime_id), results)

    passed_count = sum(1 for r in results if r["status"] == "PASS")
    total_ms = sum(r["elapsed_ms"] for r in results)

    print(f"\nResult: {passed_count}/{len(results)} PASS")
    print(f"Total:  {total_ms}ms")

    _print_cost_profile(results)

    evidence = {
        "simulation": "containment_simulation",
        "timestamp": _ts(),
        "api_base": args.api_base,
        "firewall_url": args.firewall_url,
        "runtime_id": args.runtime_id,
        "auth_mode": auth_mode,
        "passed": passed_count,
        "total": len(results),
        "all_pass": all_pass,
        "total_ms": total_ms,
        "results": results,
    }

    evidence_dir = Path(args.evidence_dir)
    if evidence_dir.exists():
        ts_prefix = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        evidence_path = evidence_dir / f"{ts_prefix}-containment-simulation.json"
        evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(f"\nEvidence written to: {evidence_path.name}")

    print()
    if not all_pass:
        print("MANUAL VERIFICATION NEEDED for failed scenarios.")
        print("Common issues:")
        print("  - Firewall not running: python scripts/lemma_firewall.py")
        print("  - Token expired: lemma login --api-base https://lemma.id")
        print("  - Policy missing httpbin: save sample policy from run_firewall_integration_example.py")
        print()
        print("Scenarios NOT covered by this simulation (require interactive auth):")
        print("  - Revocation end-to-end (needs wallet unlock via passkey)")
        print("  - Proof chain crypto verification (needs wallet session for issuance)")
        print("  - Real agent framework integration (this tests HTTP-level containment)")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
