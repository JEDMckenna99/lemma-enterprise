#!/usr/bin/env python3
"""
Lemma Firewall – Integration Example

Demonstrates the containment loop by sending one ALLOWED and one DENIED
request through a locally-running Lemma Firewall (AIM gateway).

Auth: The script prefers Ed25519-signed credentials (issued via
/api/demo/issue-credential) for local firewall verification. Falls back
to legacy X-Agent-Token if credential issuance is unavailable.

Usage:
    python scripts/run_firewall_integration_example.py
    python scripts/run_firewall_integration_example.py --firewall-url http://localhost:8787
    python scripts/run_firewall_integration_example.py --token <agent-token>

Prerequisites:
    - Lemma Firewall running locally (see scripts/start_lemma_firewall.ps1)
    - Auth: credential issuance (preferred), agent token (env LEMMA_AGENT_TOKEN,
      --token flag, or ~/.lemma/cli_auth.json)
    - The firewall policy must include an "httpbin" API entry
      (save SAMPLE_POLICY below to your policy JSON file)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Sample policy – save this to your firewall policy JSON to run the example.
# The firewall validates requests using Ed25519-signed credentials (preferred)
# or legacy X-Agent-Token header.
# ---------------------------------------------------------------------------
SAMPLE_POLICY = {
    "apis": {
        "httpbin": {
            "base_url": "https://httpbin.org",
            "allowed_methods": ["GET", "POST"],
            "path_prefixes": ["/get", "/post", "/status/", "/headers"],
            "required_scope": "read",
            "risk_tier": "low",
        }
    }
}

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {_GREEN}✔{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_RED}✘{_RESET} {msg}")


def _info(msg: str) -> None:
    print(f"  {_CYAN}ℹ{_RESET} {msg}")


def _header(msg: str) -> None:
    print(f"\n{_BOLD}{msg}{_RESET}")


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
# Core requests
# ---------------------------------------------------------------------------

def check_health(firewall_url: str) -> bool:
    try:
        resp = requests.get(f"{firewall_url}/aim/health", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def make_allowed_request(firewall_url: str, token: str | None = None, credential: dict | None = None) -> requests.Response:
    """GET /firewall/httpbin/get – path IS in allowed prefixes."""
    return requests.get(
        f"{firewall_url}/firewall/httpbin/get",
        headers=_build_auth_headers(token, credential),
        timeout=10,
    )


def make_denied_request(firewall_url: str, token: str | None = None, credential: dict | None = None) -> requests.Response:
    """GET /firewall/httpbin/admin/secret – path NOT in allowed prefixes."""
    return requests.get(
        f"{firewall_url}/firewall/httpbin/admin/secret",
        headers=_build_auth_headers(token, credential),
        timeout=10,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lemma Firewall containment-loop integration example",
    )
    parser.add_argument(
        "--firewall-url",
        default="http://localhost:8787",
        help="Base URL of the local Lemma Firewall (default: http://localhost:8787)",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("LEMMA_BASE_URL", "https://lemma.id"),
        help="Lemma control-plane base URL (default: https://lemma.id)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Agent token fallback (reads LEMMA_AGENT_TOKEN or ~/.lemma/cli_auth.json if omitted)",
    )
    args = parser.parse_args()

    firewall_url: str = args.firewall_url.rstrip("/")
    api_base: str = args.api_base.rstrip("/")

    _header("Lemma Firewall – Integration Example")

    # 1. Health check ---------------------------------------------------
    _header("Step 1 · Firewall health check")
    if not check_health(firewall_url):
        _fail(f"Firewall not reachable at {firewall_url}/aim/health")
        print()
        print("  Start the firewall first:")
        print(f"    {_YELLOW}python scripts/lemma_firewall.py --policy policy.json{_RESET}")
        print()
        print("  Make sure your policy file includes the httpbin API entry.")
        print("  You can use the sample policy embedded in this script:")
        print(f"    {_YELLOW}python -c \"import scripts.run_firewall_integration_example as m; "
              f"import json; print(json.dumps(m.SAMPLE_POLICY, indent=2))\"{_RESET}")
        sys.exit(1)
    _ok(f"Firewall healthy at {firewall_url}")

    # 2. Environment check ------------------------------------------------
    _header("Step 2 · Environment check")
    _info(f"LEMMA_BASE_URL = {api_base}")

    # 3. Resolve auth (credential preferred, token fallback) ---------------
    _header("Step 3 · Resolve auth")
    credential = _resolve_credential(api_base)
    token = _resolve_token(args.token)

    if credential:
        auth_mode = "credential (local verify)"
        _ok(f"Credential issued via {api_base}/api/demo/issue-credential")
    elif token:
        auth_mode = "token (server verify)"
        _ok(f"Token resolved (…{token[-6:]})")
    else:
        _fail("No credential or agent token available. Provide --token, set "
              "LEMMA_AGENT_TOKEN, or ensure the control plane is reachable for "
              "credential issuance.")
        sys.exit(1)
    _info(f"Auth mode: {auth_mode}")

    # 4. Allowed request ------------------------------------------------
    allowed_ok = False
    denied_ok = False

    effective_token = token if not credential else None

    _header("Step 4 · ALLOWED request  →  GET /firewall/httpbin/get")
    try:
        resp = make_allowed_request(firewall_url, token=effective_token, credential=credential)
        if resp.status_code == 200:
            _ok(f"Status {resp.status_code} – request forwarded to upstream")
            allowed_ok = True
        else:
            _fail(f"Status {resp.status_code} – expected 200")
            _info(f"Body: {resp.text[:300]}")
    except requests.RequestException as exc:
        _fail(f"Request error: {exc}")

    # 5. Denied request -------------------------------------------------
    _header("Step 5 · DENIED request   →  GET /firewall/httpbin/admin/secret")
    try:
        resp = make_denied_request(firewall_url, token=effective_token, credential=credential)
        if resp.status_code == 403:
            _ok(f"Status {resp.status_code} – correctly denied by firewall policy")
            denied_ok = True
        elif resp.status_code == 200:
            _fail(f"Status {resp.status_code} – request was NOT blocked (policy misconfigured?)")
        else:
            _fail(f"Status {resp.status_code} – unexpected")
            _info(f"Body: {resp.text[:300]}")
    except requests.RequestException as exc:
        _fail(f"Request error: {exc}")

    # 6. Summary --------------------------------------------------------
    _header("Summary")
    print()
    print(f"  {'Result':<12} {'Request':<45} {'Reason'}")
    print(f"  {'------':<12} {'-------':<45} {'------'}")
    print(f"  {_GREEN + 'ALLOWED' + _RESET if allowed_ok else _RED + 'FAILED' + _RESET:<22} "
          f"{'GET /firewall/httpbin/get':<45} "
          f"Path /get is in allowed path_prefixes")
    print(f"  {_GREEN + 'DENIED' + _RESET if denied_ok else _RED + 'FAILED' + _RESET:<22}  "
          f"{'GET /firewall/httpbin/admin/secret':<45} "
          f"Path /admin/secret is NOT in allowed path_prefixes")
    print()
    _info(f"Auth mode: {auth_mode}")
    print()

    if allowed_ok and denied_ok:
        _ok("Containment loop verified – firewall enforced policy correctly.")
    else:
        _fail("One or more checks did not pass. Review output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
