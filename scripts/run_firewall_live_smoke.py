#!/usr/bin/env python3
"""
Lemma Firewall – Live Smoke Test

Validates the full containment loop against the deployed Lemma control plane
and a locally-running Lemma Firewall.  Exits 0 on all-pass, 1 on any failure.

Auth: Prefers Ed25519-signed credentials (issued via /api/demo/issue-credential)
for local firewall verification. Falls back to legacy X-Agent-Token when needed.

Usage:
    python scripts/run_firewall_live_smoke.py
    python scripts/run_firewall_live_smoke.py --api-base https://lemma.id --firewall-url http://localhost:8787
    python scripts/run_firewall_live_smoke.py --token <agent-token>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Token resolution (fallback)
# ---------------------------------------------------------------------------
CLI_AUTH_PATH = Path.home() / ".lemma" / "cli_auth.json"


def _resolve_token(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env_token = os.environ.get("LEMMA_AGENT_TOKEN")
    if env_token:
        return env_token
    if CLI_AUTH_PATH.exists():
        try:
            data = json.loads(CLI_AUTH_PATH.read_text(encoding="utf-8"))
            return data.get("agent_token") or data.get("token")
        except (json.JSONDecodeError, OSError):
            pass
    return None


# ---------------------------------------------------------------------------
# Credential issuance (preferred auth path)
# ---------------------------------------------------------------------------

def _resolve_credential(api_base: str, runtime_id: str = "lemma-demo-runtime") -> dict | None:
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


def _build_auth_headers(token: str | None, credential: dict | None) -> dict:
    """Build auth headers: credential preferred, token fallback."""
    if credential:
        return {"X-Lemma-Credential": json.dumps(credential)}
    if token:
        return {"X-Agent-Token": token}
    return {}


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    name: str
    passed: bool
    status_code: int | None = None
    elapsed_ms: float = 0.0
    detail: str = ""
    error: str = ""


@dataclass
class SmokeReport:
    all_passed: bool = True
    steps: list[dict[str, Any]] = field(default_factory=list)

    def record(self, result: StepResult) -> None:
        if not result.passed:
            self.all_passed = False
        self.steps.append(asdict(result))


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _pass(msg: str) -> None:
    print(f"  {_GREEN}PASS{_RESET}  {msg}")


def _fail_msg(msg: str) -> None:
    print(f"  {_RED}FAIL{_RESET}  {msg}")


def _info(msg: str) -> None:
    print(f"  {_CYAN}INFO{_RESET}  {msg}")


# ---------------------------------------------------------------------------
# Individual test steps
# ---------------------------------------------------------------------------

def step_issue_credential(api_base: str) -> StepResult:
    """POST /api/demo/issue-credential – issue a signed credential."""
    name = "credential_issuance"
    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{api_base}/api/demo/issue-credential",
            json={"runtime_id": "lemma-demo-runtime", "scope": ["read", "write"]},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        elapsed = (time.monotonic() - t0) * 1000
        body = resp.json() if resp.content else {}
        credential = body.get("credential") or body
        passed = resp.status_code == 200 and bool(credential)
        detail = "credential issued" if passed else f"unexpected status {resp.status_code}"
        return StepResult(
            name=name,
            passed=passed,
            status_code=resp.status_code,
            elapsed_ms=round(elapsed, 1),
            detail=detail,
            error="" if passed else resp.text[:300],
        )
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return StepResult(name=name, passed=False, elapsed_ms=round(elapsed, 1), error=str(exc))


def step_firewall_health(firewall_url: str) -> StepResult:
    """GET /aim/health – firewall reachable."""
    name = "firewall_health"
    t0 = time.monotonic()
    try:
        resp = requests.get(f"{firewall_url}/aim/health", timeout=5)
        elapsed = (time.monotonic() - t0) * 1000
        passed = resp.status_code == 200
        return StepResult(
            name=name,
            passed=passed,
            status_code=resp.status_code,
            elapsed_ms=round(elapsed, 1),
            detail="healthy" if passed else f"status {resp.status_code}",
        )
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return StepResult(name=name, passed=False, elapsed_ms=round(elapsed, 1), error=str(exc))


def step_allowed_request(firewall_url: str, token: str | None, credential: dict | None) -> StepResult:
    """GET /firewall/httpbin/get – should be forwarded (200)."""
    name = "allowed_request"
    t0 = time.monotonic()
    try:
        resp = requests.get(
            f"{firewall_url}/firewall/httpbin/get",
            headers=_build_auth_headers(token, credential),
            timeout=10,
        )
        elapsed = (time.monotonic() - t0) * 1000
        passed = resp.status_code == 200
        return StepResult(
            name=name,
            passed=passed,
            status_code=resp.status_code,
            elapsed_ms=round(elapsed, 1),
            detail="forwarded" if passed else f"status {resp.status_code}",
            error="" if passed else resp.text[:300],
        )
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return StepResult(name=name, passed=False, elapsed_ms=round(elapsed, 1), error=str(exc))


def step_denied_request(firewall_url: str, token: str | None, credential: dict | None) -> StepResult:
    """GET /firewall/httpbin/admin/secret – should be blocked (403)."""
    name = "denied_request"
    t0 = time.monotonic()
    try:
        resp = requests.get(
            f"{firewall_url}/firewall/httpbin/admin/secret",
            headers=_build_auth_headers(token, credential),
            timeout=10,
        )
        elapsed = (time.monotonic() - t0) * 1000
        passed = resp.status_code == 403
        detail = "correctly denied" if passed else f"expected 403, got {resp.status_code}"
        return StepResult(
            name=name,
            passed=passed,
            status_code=resp.status_code,
            elapsed_ms=round(elapsed, 1),
            detail=detail,
            error="" if passed else resp.text[:300],
        )
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return StepResult(name=name, passed=False, elapsed_ms=round(elapsed, 1), error=str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lemma Firewall live smoke test – validates the full containment loop",
    )
    parser.add_argument(
        "--api-base",
        default="https://lemma.id",
        help="Lemma control-plane base URL (default: https://lemma.id)",
    )
    parser.add_argument(
        "--firewall-url",
        default="http://localhost:8787",
        help="Base URL of the local Lemma Firewall (default: http://localhost:8787)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Agent token fallback (reads LEMMA_AGENT_TOKEN or ~/.lemma/cli_auth.json if omitted)",
    )
    args = parser.parse_args()

    api_base: str = args.api_base.rstrip("/")
    firewall_url: str = args.firewall_url.rstrip("/")

    print(f"\n{_BOLD}Lemma Firewall – Live Smoke Test{_RESET}")
    print(f"  control plane : {api_base}")
    print(f"  firewall      : {firewall_url}\n")

    credential = _resolve_credential(api_base)
    token = _resolve_token(args.token)

    if credential:
        auth_mode = "credential (local verify)"
        _info(f"Credential issued via {api_base}/api/demo/issue-credential")
    elif token:
        auth_mode = "token (server verify)"
        _info(f"Token resolved (…{token[-6:]})")
    else:
        _fail_msg("No credential or agent token found. Provide --token, set "
                   "LEMMA_AGENT_TOKEN, or ensure the control plane is reachable "
                   "for credential issuance.")
        sys.exit(1)
    _info(f"Auth mode: {auth_mode}")
    print()

    effective_token = token if not credential else None

    report = SmokeReport()

    steps = [
        ("1. Issue credential from control plane",   lambda: step_issue_credential(api_base)),
        ("2. Firewall health check",                 lambda: step_firewall_health(firewall_url)),
        ("3. Allowed request (GET /get)",             lambda: step_allowed_request(firewall_url, effective_token, credential)),
        ("4. Denied request (GET /admin/secret)",     lambda: step_denied_request(firewall_url, effective_token, credential)),
    ]

    for label, run_step in steps:
        print(f"  {_BOLD}{label}{_RESET}")
        result = run_step()
        report.record(result)
        if result.passed:
            _pass(f"{result.detail}  ({result.elapsed_ms:.0f} ms)")
        else:
            _fail_msg(f"{result.detail or result.error}  ({result.elapsed_ms:.0f} ms)")
        print()

    # JSON report -------------------------------------------------------
    print(f"{_BOLD}JSON Report{_RESET}")
    print(json.dumps(asdict(report), indent=2))
    print()

    # Summary -----------------------------------------------------------
    total = len(report.steps)
    passed = sum(1 for s in report.steps if s["passed"])
    failed = total - passed

    if report.all_passed:
        print(f"  {_GREEN}{_BOLD}ALL {total} CHECKS PASSED{_RESET}")
        sys.exit(0)
    else:
        print(f"  {_RED}{_BOLD}{failed}/{total} CHECKS FAILED{_RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
