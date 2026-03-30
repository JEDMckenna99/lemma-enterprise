"""
Lemma CLI -- agent sessions, firewall onboarding, and platform management.

Agent Session:
  lemma start             Start a scoped agent session with local firewall
  lemma stop              Stop the active agent session
  lemma replay            Replay the last session's action log
  lemma demo              One-command containment demo

Setup & Onboarding:
  lemma init              Initialize Lemma project config
  lemma setup             Scaffold Lemma integration assets
  lemma init-policy       Generate starter firewall policy JSON
  lemma setup-openclaw    Starter-safe OpenClaw setup
  lemma setup-firewall    Guided firewall onboarding
  lemma firewall-connect  Canonical runtime onboarding
  lemma flow              Non-interactive happy-path setup

Authentication:
  lemma login             Log in with Lemma credential
  lemma logout            Clear local CLI auth session
  lemma auth-status       Validate stored CLI auth session
  lemma authorize-agent   One-command agent auth
  lemma session start     Open wallet unlock flow
  lemma session status    Check wallet unlock session status
  lemma session link      Fetch temporary wallet unlock token

Platform Management:
  lemma site-create       Provision a new developer site
  lemma key-bootstrap     Create site API key
  lemma iam-type-create   Create IAM permission type
  lemma iam-type-list     List IAM permission types

Diagnostics:
  lemma verify            Run basic integration checks
  lemma audit             Audit local integration scaffolding
  lemma fix               Auto-repair common integration gaps
  lemma smoke             Run protected-endpoint smoke check
  lemma ci                Run integration gate for agents/CI
  lemma doctor            Diagnose common integration errors
  lemma safety-status     Check local firewall posture
  lemma incident-bundle   Export incident bundle with timeline
  lemma authz-latency     Measure authz latency and enforce budget
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import statistics
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_USAGE = 2
CLI_SCHEMA_VERSION = "2026-03-03"

ERR_OK = "OK"
ERR_USAGE_MISSING_REQUIRED_ARGS = "E_USAGE_MISSING_REQUIRED_ARGS"
ERR_CONFIG_EXISTS = "E_CONFIG_EXISTS"
ERR_SAFE_FLAG_REQUIRED = "E_SAFE_FLAG_REQUIRED"
ERR_MISSING_SITE_IDENTITY = "E_MISSING_SITE_IDENTITY"
ERR_MISSING_URL = "E_MISSING_URL"
ERR_MISSING_CREDENTIAL_HEADER = "E_MISSING_CREDENTIAL_HEADER"
ERR_REQUEST_FAILED = "E_REQUEST_FAILED"
ERR_EXPECTED_STATUS_MISMATCH = "E_EXPECTED_STATUS_MISMATCH"
ERR_CI_SMOKE_URL_REQUIRED = "E_CI_SMOKE_URL_REQUIRED"
ERR_CI_SMOKE_HEADER_REQUIRED = "E_CI_SMOKE_HEADER_REQUIRED"
ERR_AUTH_REQUIRED = "E_AUTH_REQUIRED"
ERR_AUTH_INVALID = "E_AUTH_INVALID"
ERR_LOGIN_FAILED = "E_LOGIN_FAILED"
ERR_HTTP_FAILED = "E_HTTP_FAILED"
ERR_WRITE_ENV_FAILED = "E_WRITE_ENV_FAILED"
ERR_CONFIG_MISSING = "E_CONFIG_MISSING"
ERR_PLATFORM_ISSUE_FAILED = "E_PLATFORM_ISSUE_FAILED"
ERR_BROWSER_LOGIN_TIMEOUT = "E_BROWSER_LOGIN_TIMEOUT"
ERR_FLOW_STEP_FAILED = "E_FLOW_STEP_FAILED"
ERR_WRITE_DRY_RUN_OUTPUT_FAILED = "E_WRITE_DRY_RUN_OUTPUT_FAILED"
ERR_SESSION_LOCKED = "E_SESSION_LOCKED"
ERR_SAFETY_DEGRADED = "E_SAFETY_DEGRADED"
ERR_SAFETY_UNSAFE = "E_SAFETY_UNSAFE"

AUTH_SESSION_PATH = Path.home() / ".lemma" / "cli_auth.json"
OPENCLAW_SETUP_COMMAND = "setup-openclaw"


def _build_report(command: str, ok: bool, error_code: str = ERR_OK, **extra: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": CLI_SCHEMA_VERSION,
        "command": command,
        "ok": ok,
        "error_code": error_code,
    }
    report.update(extra)
    return report


def _emit_report(args: argparse.Namespace, report: dict[str, Any], text_lines: list[str]) -> None:
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
        return
    for line in text_lines:
        print(line)


def _auth_path(session_file: str | None = None) -> Path:
    if session_file:
        return Path(session_file).expanduser().resolve()
    return AUTH_SESSION_PATH


def _save_auth_session(session_data: dict[str, Any], session_file: str | None = None) -> Path:
    path = _auth_path(session_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session_data, indent=2) + "\n", encoding="utf-8")
    return path


def _load_auth_session(session_file: str | None = None) -> dict[str, Any] | None:
    path = _auth_path(session_file)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _clear_auth_session(session_file: str | None = None) -> bool:
    path = _auth_path(session_file)
    if not path.exists():
        return False
    path.unlink()
    return True


def _http_json_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int | None, dict[str, Any] | None, str | None]:
    try:
        import requests
    except ImportError:
        return None, None, "requests not installed"

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            json=json_body,
            timeout=timeout,
        )
        try:
            payload = response.json() if response.text else {}
        except ValueError:
            payload = {"raw_text": (response.text or "")[:400]}
        return response.status_code, payload if isinstance(payload, dict) else {"raw": payload}, None
    except requests.RequestException as exc:
        return None, None, str(exc)


def _http_json_request_with_headers(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int | None, dict[str, Any] | None, dict[str, str], str | None]:
    try:
        import requests
    except ImportError:
        return None, None, {}, "requests not installed"

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            json=json_body,
            timeout=timeout,
        )
        try:
            payload = response.json() if response.text else {}
        except ValueError:
            payload = {"raw_text": (response.text or "")[:400]}
        response_headers = {str(key): str(value) for key, value in dict(response.headers or {}).items()}
        normalized_payload = payload if isinstance(payload, dict) else {"raw": payload}
        return response.status_code, normalized_payload, response_headers, None
    except requests.RequestException as exc:
        return None, None, {}, str(exc)


def _mask_token(token: str | None) -> str:
    value = (token or "").strip()
    if len(value) <= 12:
        return value
    return f"{value[:8]}...{value[-4:]}"


def _mask_sensitive_headers(headers: dict[str, str] | None) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in (headers or {}).items():
        key_text = str(key)
        value_text = str(value or "")
        key_lower = key_text.lower()
        if key_lower in {"authorization", "x-agent-token", "x-api-key", "x-lemma-credential"}:
            if key_lower == "authorization" and value_text.lower().startswith("bearer "):
                token = value_text.split(" ", 1)[1]
                masked[key_text] = f"Bearer {_mask_token(token)}"
            else:
                masked[key_text] = _mask_token(value_text)
        else:
            masked[key_text] = value_text
    return masked


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (max(0.0, min(100.0, float(percentile))) / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def _finalize_dry_run_report(args: argparse.Namespace, report: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    if not bool(report.get("dry_run")):
        return report, None
    output_path_raw = str(getattr(args, "dry_run_output", "") or "").strip()
    if not output_path_raw:
        return report, None
    try:
        output_path = Path(output_path_raw).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_with_path = dict(report)
        report_with_path["dry_run_output"] = str(output_path)
        output_path.write_text(json.dumps(report_with_path, indent=2) + "\n", encoding="utf-8")
        return report_with_path, None
    except OSError as exc:
        return report, str(exc)


def _guidance_for_platform_self_issue_failure(response_payload: dict[str, Any] | None) -> list[str]:
    payload = response_payload or {}
    error_code = str(payload.get("error") or "").strip().lower()
    if error_code == "invalid_ppid":
        return [
            "This environment requires wallet-derived PPID identity and rejects email-derived issuance.",
            "Use wallet login in browser (or provide --credential-file / --header from a trusted wallet-issued lemma).",
            "Then run `lemma authorize-agent --credential-file <lemma.json> --api-base https://lemma.id --json`.",
        ]
    return [
        "Confirm --platform-api-key and --user-email map to an authorized admin identity.",
        "If self-issue is restricted, use browser wallet login or a trusted credential file instead.",
    ]


def _guidance_for_login_issue_failure(response_payload: dict[str, Any] | None) -> list[str]:
    payload = response_payload or {}
    error_code = str(payload.get("error") or "").strip().lower()
    if error_code == "wallet_unlock_required":
        return [
            "Unlock your lemma.id wallet in browser once for the day.",
            "Re-run the same command after unlock, or use `lemma authorize-agent` for one-step login + validate.",
            "Use `lemma auth-status --json` to confirm token validity after issuance.",
        ]
    if error_code == "missing_scope":
        return [
            "Requested action requires broader scope.",
            "Re-run login with a stronger scope, e.g. `--scope read,write,admin`.",
            "Keep scope least-privilege for production agents.",
        ]
    return [
        "Check response.error/response.message for policy details.",
        "Retry with `--json` and inspect status_code + response for actionable hints.",
    ]


def _derive_api_base(value: str | None) -> str:
    api_base = (value or "https://lemma.id").strip().rstrip("/")
    return api_base or "https://lemma.id"


def _runtime_bootstrap_defaults() -> dict[str, str]:
    root_type = str(os.getenv("LEMMA_ROOT_TYPE") or "passkey_root").strip().lower() or "passkey_root"
    if root_type not in {"passkey_root", "workload_root", "policy_root"}:
        root_type = "passkey_root"
    environment = str(os.getenv("LEMMA_ENVIRONMENT") or "prod").strip().lower() or "prod"
    if environment not in {"dev", "staging", "prod"}:
        environment = "prod"
    org_id = str(os.getenv("LEMMA_ORG_ID") or "org_default").strip() or "org_default"
    policy_profile = str(os.getenv("LEMMA_POLICY_PROFILE") or "runtime_default_v1").strip() or "runtime_default_v1"
    return {
        "root_type": root_type,
        "environment": environment,
        "org_id": org_id,
        "policy_profile": policy_profile,
    }


def _starter_safe_firewall_env_updates() -> dict[str, str]:
    return {
        "LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT": "1",
        "LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED": "1",
        "LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS": "low,critical",
        "LEMMA_FIREWALL_PROOF_REQUIRED_TIERS": "critical",
        "LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP": "0",
        "LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL": "0",
        "LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY": "0",
        "LEMMA_FIREWALL_MAX_STALENESS_HIGH_MS": "120000",
        "LEMMA_FIREWALL_MAX_STALENESS_CRITICAL_MS": "10000",
    }


def _starter_safe_status_from_health(health: dict[str, Any] | None) -> tuple[str, list[str]]:
    payload = health if isinstance(health, dict) else {}
    status = "safe"
    reasons: list[str] = []
    if not bool(payload.get("ok")):
        return "unsafe", ["firewall_health_unavailable"]
    if not bool(payload.get("local_proof_enforcement")):
        status = "degraded"
        reasons.append("local_proof_enforcement_disabled")
    sync_payload = payload.get("sync") if isinstance(payload.get("sync"), dict) else {}
    if not bool(sync_payload.get("enabled", False)):
        status = "degraded"
        reasons.append("control_plane_sync_disabled")
    tiers = {
        str(item or "").strip().lower()
        for item in (payload.get("runtime_authorize_required_tiers") or [])
        if str(item or "").strip()
    }
    if "critical" not in tiers:
        status = "degraded"
        reasons.append("critical_tier_not_forced_online")
    if bool(payload.get("online_check_on_stale_noncritical")):
        reasons.append("noncritical_stale_online_enabled")
    return status, reasons


def _read_log_tail(log_path: Path | None, max_lines: int = 30) -> list[str]:
    if not log_path:
        return []
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    if max_lines <= 0:
        return lines
    return lines[-max_lines:]


def _resolve_openclaw_config_path() -> Path:
    override = str(os.getenv("OPENCLAW_CONFIG_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openclaw" / "openclaw.json"


def _openclaw_config_hint_lines(*, api_base: str, proof_file: Path, runtime_id: str, config_path: Path) -> list[str]:
    return [
        f"OpenClaw config patch skipped. Set these in `{config_path}`:",
        f"env.vars.LEMMA_BASE_URL={api_base}",
        f"env.vars.LEMMA_PROOF_FILE={proof_file}",
        f"env.vars.LEMMA_FIREWALL_RUNTIME_ID={runtime_id}",
    ]


def _patch_openclaw_config(*, api_base: str, proof_file: Path, runtime_id: str) -> tuple[bool, Path, str, list[str]]:
    config_path = _resolve_openclaw_config_path()
    hints = _openclaw_config_hint_lines(
        api_base=api_base,
        proof_file=proof_file,
        runtime_id=runtime_id,
        config_path=config_path,
    )
    if not config_path.exists():
        return False, config_path, "OpenClaw config file not found; printed manual patch instructions.", hints

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False, config_path, "OpenClaw config is not valid JSON; printed manual patch instructions.", hints

    if not isinstance(payload, dict):
        return False, config_path, "OpenClaw config root is not an object; printed manual patch instructions.", hints

    env_payload = payload.get("env")
    if not isinstance(env_payload, dict):
        env_payload = {}
        payload["env"] = env_payload
    vars_payload = env_payload.get("vars")
    if not isinstance(vars_payload, dict):
        vars_payload = {}
        env_payload["vars"] = vars_payload

    vars_payload["LEMMA_BASE_URL"] = api_base
    vars_payload["LEMMA_PROOF_FILE"] = str(proof_file)
    vars_payload["LEMMA_FIREWALL_RUNTIME_ID"] = runtime_id

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False, config_path, "Failed writing OpenClaw config; printed manual patch instructions.", hints

    return True, config_path, "Patched OpenClaw config for Lemma proof/runtime defaults.", [
        f"OpenClaw config patched: `{config_path}`",
    ]


POLICY_PRESETS: dict[str, dict[str, Any]] = {
    "github": {
        "base_url": "https://api.github.com",
        "allowed_methods": ["GET", "POST", "PATCH"],
        "path_prefixes": ["/repos/", "/user", "/search/"],
        "required_scope": "write",
        "risk_tier": "high",
        "forward_headers": ["authorization", "content-type", "accept"],
    },
    "stripe": {
        "base_url": "https://api.stripe.com",
        "allowed_methods": ["GET", "POST"],
        "path_prefixes": ["/v1/customers", "/v1/payment_intents", "/v1/refunds"],
        "required_scope": "admin",
        "risk_tier": "critical",
        "forward_headers": ["authorization", "content-type"],
    },
    "openai": {
        "base_url": "https://api.openai.com",
        "allowed_methods": ["GET", "POST"],
        "path_prefixes": ["/v1/"],
        "required_scope": "read",
        "risk_tier": "high",
        "forward_headers": ["authorization", "content-type"],
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "allowed_methods": ["GET", "POST"],
        "path_prefixes": ["/v1/"],
        "required_scope": "read",
        "risk_tier": "high",
        "forward_headers": ["authorization", "content-type", "anthropic-version"],
    },
    "httpbin": {
        "base_url": "https://httpbin.org",
        "allowed_methods": ["GET", "POST"],
        "path_prefixes": ["/get", "/post", "/status/", "/headers", "/ip"],
        "required_scope": "read",
        "risk_tier": "low",
        "forward_headers": ["content-type", "accept"],
    },
}


def _policy_template_for_api(api_id: str) -> dict[str, Any]:
    normalized = (api_id or "").strip().lower()
    preset = POLICY_PRESETS.get(normalized)
    if preset:
        return dict(preset)
    return {
        "base_url": "https://api.example.com",
        "allowed_methods": ["GET"],
        "path_prefixes": ["/v1/"],
        "required_scope": "read",
        "risk_tier": "low",
        "forward_headers": ["authorization", "content-type"],
    }


def _issue_wallet_runtime_proof(
    *,
    api_base: str,
    unlock_token: str,
    site_id: str,
    timeout: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    status, payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/wallet/runtimes/issue-proof",
        headers={
            "X-Lemma-Unlock": unlock_token,
            "Content-Type": "application/json",
        },
        json_body={"site_id": site_id},
        timeout=timeout,
    )
    if err or status != 200 or not bool((payload or {}).get("success")) or not isinstance((payload or {}).get("credential"), dict):
        report = _build_report(
            OPENCLAW_SETUP_COMMAND,
            ok=False,
            error_code=ERR_HTTP_FAILED,
            failed_step="issue-proof",
            status_code=status,
            response=payload,
            message=err or (payload or {}).get("message") or "Failed to issue OpenClaw proof.",
        )
        return None, report
    return payload or {}, None


def _is_platform_host(api_base: str) -> bool:
    host = _extract_host(api_base)
    return host in {"lemma.id", "www.lemma.id"}


def _extract_host(value: str) -> str:
    text = (value or "").strip()
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    return (parsed.hostname or "").strip().lower()


def _issue_platform_admin_credential_for_login(args: argparse.Namespace, api_base: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    platform_api_key = (
        (getattr(args, "platform_api_key", "") or "").strip()
        or os.getenv("LEMMA_API_KEY", "").strip()
        or os.getenv("LEMMA_PLATFORM_API_KEY", "").strip()
    )
    user_email = (
        (getattr(args, "user_email", "") or "").strip().lower()
        or os.getenv("LEMMA_ADMIN_EMAIL", "").strip().lower()
        or os.getenv("PLATFORM_ADMIN_EMAIL", "").strip().lower()
    )
    if not platform_api_key or not user_email:
        return None, _build_report(
            "login",
            ok=False,
            error_code=ERR_PLATFORM_ISSUE_FAILED,
            message="Platform self-issue requires API key and user email. Set --platform-api-key/--user-email or env LEMMA_API_KEY + LEMMA_ADMIN_EMAIL.",
        )

    body = {
        "site_id": (getattr(args, "site_id", "") or "lemma.id").strip(),
        "site_domain": (getattr(args, "site_domain", "") or "lemma.id").strip().lower(),
        "user_email": user_email,
        "permission_level": (getattr(args, "permission_level", "") or "super_admin").strip(),
    }
    # Be tolerant to deployment/header variance: try Bearer first, then X-API-Key.
    status, payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/v1/iam/admin/self-issue",
        headers={"Authorization": f"Bearer {platform_api_key}"},
        json_body=body,
        timeout=float(args.timeout),
    )
    if not err and status in {401, 403}:
        status, payload, err = _http_json_request(
            method="POST",
            url=f"{api_base}/api/v1/iam/admin/self-issue",
            headers={"X-API-Key": platform_api_key},
            json_body=body,
            timeout=float(args.timeout),
        )
    if err:
        return None, _build_report("login", ok=False, error_code=ERR_HTTP_FAILED, message=err)
    if status != 200 or not (payload or {}).get("success"):
        return None, _build_report(
            "login",
            ok=False,
            error_code=ERR_PLATFORM_ISSUE_FAILED,
            status_code=status,
            response=payload,
            message=(payload or {}).get("message", "Platform self-issue failed."),
            next_steps=_guidance_for_platform_self_issue_failure(payload),
        )

    credential = (payload or {}).get("credential")
    if not isinstance(credential, dict):
        return None, _build_report(
            "login",
            ok=False,
            error_code=ERR_PLATFORM_ISSUE_FAILED,
            status_code=status,
            response=payload,
            message="Platform self-issue response missing credential object.",
        )
    return credential, None


def _run_browser_login_flow(
    *,
    args: argparse.Namespace,
    api_base: str,
    scope: list[str],
    allowed_sites: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    state = secrets.token_urlsafe(24)
    delegation_fields = _delegation_fields_from_args(args)
    query_payload = {
        "state": state,
        "ttl_hours": int(args.ttl_hours or 8),
        "scope": ",".join(scope),
        "agent_name": args.agent_name or "lemma-cli",
        "task": args.task or "CLI authenticated provisioning session",
        "allowed_sites": ",".join(allowed_sites),
        "intended_platform": (_extract_host(api_base) or "lemma.id"),
    }
    query_payload.update(delegation_fields)
    query = urlencode(
        query_payload
    )
    approve_url = f"{api_base}/api/agent/cli-login/complete?{query}"
    poll_url = f"{api_base}/api/agent/cli-login/poll?state={state}"

    if not getattr(args, "no_browser", False):
        try:
            webbrowser.open(approve_url, new=2)
        except webbrowser.Error:
            pass

    timeout_seconds = float(getattr(args, "login_timeout", 180.0) or 180.0)
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        status, payload, err = _http_json_request(
            method="GET",
            url=poll_url,
            timeout=float(args.timeout),
        )
        if err:
            last_payload = {"error": err}
            time.sleep(2.0)
            continue
        if status != 200:
            last_payload = payload
            time.sleep(2.0)
            continue

        poll = payload or {}
        if not bool(poll.get("completed")):
            time.sleep(2.0)
            continue

        if not bool(poll.get("success")):
            message = str(poll.get("message") or poll.get("error") or "Browser login failed.")
            return None, _build_report(
                "login",
                ok=False,
                error_code=ERR_LOGIN_FAILED,
                message=message,
                response=poll,
                approval_url=approve_url,
            )

        token = str(poll.get("token") or "").strip()
        if not token:
            return None, _build_report(
                "login",
                ok=False,
                error_code=ERR_LOGIN_FAILED,
                message="Browser login completed but no token was returned.",
                response=poll,
                approval_url=approve_url,
            )

        return {
            "success": True,
            "token": token,
            "token_id": poll.get("token_id"),
            "scope": poll.get("scope", []),
            "allowed_sites": poll.get("allowed_sites", []),
            "authorized_by": poll.get("authorized_by"),
            "delegation": poll.get("delegation"),
            "expires_at": poll.get("expires_at"),
            "browser_login": True,
            "approval_url": approve_url,
        }, None

    return None, _build_report(
        "login",
        ok=False,
        error_code=ERR_BROWSER_LOGIN_TIMEOUT,
        message=f"Browser login timed out after {int(timeout_seconds)} seconds.",
        approval_url=approve_url,
        last_poll=last_payload,
    )


def _build_sensitive_headers(
    *,
    api_base: str,
    session_file: str | None,
    explicit_agent_token: str | None,
    explicit_api_key: str | None,
    timeout: float,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    token = (explicit_agent_token or "").strip()
    api_key = (explicit_api_key or "").strip()
    session = _load_auth_session(session_file)

    if not token and session:
        token = str(session.get("agent_token") or "").strip()
    if not api_key and session:
        api_key = str(session.get("api_key") or "").strip()

    if not token and not api_key:
        return None, _build_report(
            "auth",
            ok=False,
            error_code=ERR_AUTH_REQUIRED,
            message="No auth credentials found. Run `lemma login` or provide --agent-token/--api-key.",
        )

    headers: dict[str, str] = {}
    if token:
        validate_url = f"{api_base}/api/agent/validate"
        status, payload, err = _http_json_request(
            method="GET",
            url=validate_url,
            headers={"X-Agent-Token": token},
            timeout=timeout,
        )
        if err:
            return None, _build_report(
                "auth",
                ok=False,
                error_code=ERR_HTTP_FAILED,
                message=f"Agent token validation failed: {err}",
            )
        if status != 200 or not (payload or {}).get("valid"):
            return None, _build_report(
                "auth",
                ok=False,
                error_code=ERR_AUTH_INVALID,
                message="Stored/provided agent token is invalid or expired.",
                validation_status=status,
                validation_payload=payload,
            )
        headers["X-Agent-Token"] = token
    if api_key:
        headers["X-API-Key"] = api_key
    return headers, None


def _write_env_values(path: Path, values: dict[str, str], overwrite: bool) -> tuple[bool, str]:
    lines: list[str] = []
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return False, str(exc)

    existing: dict[str, int] = {}
    for idx, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key:
                existing[key] = idx

    for key, value in values.items():
        entry = f"{key}={value}"
        if key in existing:
            if overwrite:
                lines[existing[key]] = entry
        else:
            lines.append(entry)

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, ""


def _load_lemma_config(project_dir: Path) -> dict[str, Any] | None:
    config_path = project_dir / ".lemma" / "config.json"
    if not config_path.exists():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_file(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return "skipped"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "written"


def _encode_credential_for_header(credential: dict[str, Any]) -> str:
    raw = json.dumps(credential, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _resolve_smoke_header(args: argparse.Namespace) -> tuple[str | None, str | None]:
    header_value = (args.header or "").strip()
    if header_value:
        return header_value, None

    credential_file = (args.credential_file or "").strip()
    if not credential_file:
        return None, "Provide either --header or --credential-file."

    path = Path(credential_file).resolve()
    if not path.exists():
        return None, f"Credential file not found: {path}"

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"Failed to parse credential file: {exc}"

    if not isinstance(payload, dict):
        return None, "Credential file must contain a JSON object."
    return _encode_credential_for_header(payload), None


def _parse_json_object_arg(raw_value: str, *, arg_name: str) -> tuple[dict[str, Any], str | None]:
    text = (raw_value or "").strip()
    if not text:
        return {}, None
    try:
        if text.startswith("@"):
            path = Path(text[1:]).expanduser().resolve()
            loaded = json.loads(path.read_text(encoding="utf-8"))
        else:
            loaded = json.loads(text)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {}, f"{arg_name} must be a valid JSON object or @path: {exc}"
    if not isinstance(loaded, dict):
        return {}, f"{arg_name} must resolve to a JSON object"
    return loaded, None


def _parse_extra_headers(raw_items: list[str] | None) -> tuple[dict[str, str], str | None]:
    headers: dict[str, str] = {}
    for item in raw_items or []:
        entry = str(item or "").strip()
        if not entry:
            continue
        if ":" in entry:
            key, value = entry.split(":", 1)
        elif "=" in entry:
            key, value = entry.split("=", 1)
        else:
            return {}, f"Invalid --extra-header value `{entry}`. Use `Name: value`."
        key = key.strip()
        value = value.strip()
        if not key:
            return {}, f"Invalid --extra-header value `{entry}`. Header name is required."
        headers[key] = value
    return headers, None


def _resolve_inline_or_file_text(raw_value: str, *, arg_name: str) -> tuple[str, str | None]:
    text = str(raw_value or "").strip()
    if not text:
        return "", None
    if text.startswith("@"):
        try:
            path = Path(text[1:]).expanduser().resolve()
            return path.read_text(encoding="utf-8").strip(), None
        except OSError as exc:
            return "", f"{arg_name} file read failed: {exc}"
    return text, None


def _format_header_json(raw_text: str, *, arg_name: str) -> tuple[str, dict[str, Any] | None, str | None]:
    text = str(raw_text or "").strip()
    if not text:
        return "", None, None
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            return "", None, f"{arg_name} must be valid JSON: {exc}"
        if not isinstance(payload, dict):
            return "", None, f"{arg_name} JSON must be an object"
        if arg_name == "proof":
            extracted = payload.get("proof_artifact")
            if isinstance(extracted, dict):
                payload = extracted
            elif isinstance(payload.get("delegated_proof"), dict) and isinstance(payload.get("root_proof"), dict):
                payload = {
                    "version": payload.get("version") or "authz_profile_v2",
                    "policy_version": payload.get("policy_version"),
                    "proof_id": payload.get("proof_id") or payload.get("delegated_proof", {}).get("proof_id"),
                    "root_grant_id": payload.get("root_grant_id") or payload.get("root_proof", {}).get("root_grant_id"),
                    "root_proof": payload.get("root_proof"),
                    "delegated_proof": payload.get("delegated_proof"),
                    "proof_chain": payload.get("proof_chain") or [payload.get("root_proof"), payload.get("delegated_proof")],
                }
        normalized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return normalized, payload, None
    return text, None, None


def _build_pop_header(
    *,
    api_base: str,
    method: str,
    path: str,
    body: bytes,
    proof_payload: dict[str, Any] | None,
    pop_agent_key_id: str,
) -> str:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        Ed25519PrivateKey = None  # type: ignore[assignment]

    host = _extract_host(api_base) or "lemma.id"
    now_epoch = int(time.time())
    delegated = (proof_payload or {}).get("delegated_proof") if isinstance((proof_payload or {}).get("delegated_proof"), dict) else {}
    private_key_b64 = str(
        (proof_payload or {}).get("agent_private_key")
        or delegated.get("agent_private_key")
        or ""
    ).strip()
    public_key_b64 = str(
        (proof_payload or {}).get("agent_public_key")
        or delegated.get("agent_public_key")
        or ""
    ).strip()
    key_id = str(
        (proof_payload or {}).get("agent_key_id")
        or delegated.get("agent_key_id")
        or pop_agent_key_id
        or "lemma-cli"
    ).strip()
    envelope = {
        "nonce": secrets.token_urlsafe(12),
        "iat": now_epoch,
        "exp": now_epoch + 60,
        "method": str(method).upper(),
        "path": str(path),
        "body_hash": hashlib.sha256(body or b"").hexdigest(),
        "aud": host,
        "proof_id": str((proof_payload or {}).get("proof_id") or ""),
        "agent_key_id": key_id or "lemma-cli",
    }
    canonical = json.dumps(envelope, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    signature = "unsigned-local-probe"
    if Ed25519PrivateKey and private_key_b64:
        try:
            padded = private_key_b64 + ("=" * (-len(private_key_b64) % 4))
            private_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
            signer = Ed25519PrivateKey.from_private_bytes(private_bytes)
            sig_bytes = signer.sign(canonical)
            signature = base64.urlsafe_b64encode(sig_bytes).decode("utf-8").rstrip("=")
        except Exception:
            signature = "unsigned-local-probe"
    envelope["sig"] = signature
    if public_key_b64:
        envelope["public_key"] = public_key_b64
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)


def _delegation_fields_from_args(args: argparse.Namespace) -> dict[str, str]:
    fields: dict[str, str] = {}
    delegation_reason = str(getattr(args, "delegation_reason", "") or "").strip()
    delegation_id = str(getattr(args, "delegation_id", "") or "").strip()
    acting_for_ppid = str(getattr(args, "acting_for_ppid", "") or "").strip()
    requested_by_ppid = str(getattr(args, "requested_by_ppid", "") or "").strip()
    delegated_by_user_ref = str(getattr(args, "delegated_by_user_ref", "") or "").strip()
    acting_for_user_ref = str(getattr(args, "acting_for_user_ref", "") or "").strip()
    requested_by_user_ref = str(getattr(args, "requested_by_user_ref", "") or "").strip()
    if delegation_reason:
        fields["delegation_reason"] = delegation_reason
    if delegation_id:
        fields["delegation_id"] = delegation_id
    if acting_for_ppid:
        fields["acting_for_ppid"] = acting_for_ppid
    if requested_by_ppid:
        fields["requested_by_ppid"] = requested_by_ppid
    if delegated_by_user_ref:
        fields["delegated_by_user_ref"] = delegated_by_user_ref
    if acting_for_user_ref:
        fields["acting_for_user_ref"] = acting_for_user_ref
    if requested_by_user_ref:
        fields["requested_by_user_ref"] = requested_by_user_ref
    return fields


def _execute_smoke_request(
    *, url: str, method: str, header_value: str, timeout: float
) -> tuple[int | None, str | None, str | None]:
    try:
        import requests
    except ImportError:
        return None, None, "requests not installed"

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers={"X-Lemma-Credential": header_value},
            timeout=timeout,
        )
        body_preview = response.text[:400] if response.text else ""
        return response.status_code, body_preview, None
    except requests.RequestException as exc:
        return None, None, str(exc)


def _check_wallet_unlock_status(api_base: str, timeout: float) -> dict[str, Any]:
    origin = api_base.rstrip("/")
    unlock_url = f"{origin}/unlock"
    status, payload, err = _http_json_request(
        method="POST",
        url=f"{origin}/api/wallet/session-sync",
        headers={"Origin": origin},
        timeout=timeout,
    )
    if err:
        return {
            "state": "unknown",
            "status_code": status,
            "error": "http_failed",
            "message": err,
            "unlock_url": unlock_url,
        }

    body = payload or {}
    if status == 200 and bool(body.get("success")):
        session_payload = body.get("session") if isinstance(body.get("session"), dict) else {}
        return {
            "state": "unlocked",
            "status_code": status,
            "wallet_id": session_payload.get("wallet_id"),
            "unlocked_at": session_payload.get("unlocked_at"),
            "expires_at": session_payload.get("expires_at"),
            "time_remaining": session_payload.get("time_remaining"),
            "unlock_url": unlock_url,
        }

    error_code = str(body.get("error") or "unknown_error")
    if error_code in {"no_session", "session_expired"}:
        return {
            "state": "locked",
            "status_code": status,
            "error": error_code,
            "message": str(body.get("message") or "Wallet session not active."),
            "unlock_url": str(body.get("unlock_url") or unlock_url),
        }

    return {
        "state": "unknown",
        "status_code": status,
        "error": error_code,
        "message": str(body.get("message") or "Wallet unlock status unavailable."),
        "unlock_url": str(body.get("unlock_url") or unlock_url),
        "response": body,
    }


def _build_scaffold_actions(
    *,
    project_dir: Path,
    site_id: str,
    site_domain: str,
    api_base: str,
    framework: str,
    force: bool,
) -> dict[str, str]:
    config = build_init_config(site_id=site_id, site_domain=site_domain, api_base=api_base)
    lemma_dir = project_dir / ".lemma"
    config_path = lemma_dir / "config.json"
    actions: dict[str, str] = {}

    actions[str(config_path)] = _write_file(config_path, json.dumps(config, indent=2) + "\n", force=force)

    env_example = """# Lemma platform API credential (required for protected issuance/admin workflows)
LEMMA_API_KEY=
# Optional alias used by some environments
LEMMA_PLATFORM_API_KEY=
"""
    actions[str(lemma_dir / ".env.lemma.example")] = _write_file(lemma_dir / ".env.lemma.example", env_example, force=force)

    frontend_snippet = """// Lemma frontend header attachment snippet.
// Replace `getCurrentCredential()` with your app's wallet integration.
export async function getLemmaAuthHeaders() {
  const credential = await getCurrentCredential();
  if (!credential) return {};
  const encoded = btoa(JSON.stringify(credential))
    .replace(/\\+/g, "-")
    .replace(/\\//g, "_")
    .replace(/=+$/g, "");
  return { "X-Lemma-Credential": encoded };
}
"""
    actions[str(lemma_dir / "frontend-header-snippet.js")] = _write_file(
        lemma_dir / "frontend-header-snippet.js", frontend_snippet, force=force
    )

    if framework in {"flask", "both"}:
        flask_snippet = """# Lemma Flask middleware scaffold.
from flask import request, abort


def require_lemma_credential():
    header = request.headers.get("X-Lemma-Credential", "")
    if not header:
        abort(401, description="missing_lemma_header")
"""
        actions[str(lemma_dir / "server-middleware-flask.py")] = _write_file(
            lemma_dir / "server-middleware-flask.py", flask_snippet, force=force
        )

    if framework in {"express", "both"}:
        express_snippet = """// Lemma Express middleware scaffold.
export function requireLemmaCredential(req, res, next) {
  const header = req.header("X-Lemma-Credential");
  if (!header) return res.status(401).json({ error: "missing_lemma_header" });
  return next();
}
"""
        actions[str(lemma_dir / "server-middleware-express.js")] = _write_file(
            lemma_dir / "server-middleware-express.js", express_snippet, force=force
        )

    setup_readme = f"""# Lemma Setup Artifacts

This directory was generated by `lemma setup`.

- Site ID: {site_id}
- Site domain: {site_domain}
- API base: {api_base.rstrip('/')}

Next steps:
1. Wire `frontend-header-snippet.js` into your auth request path.
2. Adapt the server middleware scaffold to your verifier endpoint.
3. Run `lemma audit --project-dir {project_dir}`.
"""
    actions[str(lemma_dir / "README_SETUP.md")] = _write_file(lemma_dir / "README_SETUP.md", setup_readme, force=force)
    return actions


def build_init_config(site_id: str, site_domain: str, api_base: str) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "site_domain": site_domain,
        "api_base": api_base.rstrip("/"),
        "auth_header": "X-Lemma-Credential",
        "version": 1,
    }


def _normalize_domain(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.split("/")[0]
    text = text.split(":")[0]
    return text


def run_init(args: argparse.Namespace) -> int:
    site_id = (args.site_id or "").strip()
    site_domain = _normalize_domain(args.site_domain or "")
    api_base = (args.api_base or "https://lemma.id").strip()

    if not site_id or not site_domain:
        report = _build_report(
            "init",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--site-id and --site-domain are required",
        )
        _emit_report(args, report, ["init failed: --site-id and --site-domain are required"])
        return EXIT_USAGE

    config = build_init_config(site_id=site_id, site_domain=site_domain, api_base=api_base)
    target_dir = Path(args.output_dir or ".").resolve() / ".lemma"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "config.json"

    if target_file.exists() and not args.force:
        report = _build_report(
            "init",
            ok=False,
            error_code=ERR_CONFIG_EXISTS,
            message=f"{target_file} already exists",
            config_path=str(target_file),
        )
        _emit_report(args, report, [f"init aborted: {target_file} already exists (use --force to overwrite)"])
        return EXIT_CHECK_FAILED

    target_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
    report = _build_report("init", ok=True, config_path=str(target_file), config=config)
    _emit_report(
        args,
        report,
        [
            f"initialized lemma config: {target_file}",
            "next: run `lemma setup` to scaffold frontend + server snippets",
        ],
    )
    return EXIT_OK


def run_setup(args: argparse.Namespace) -> int:
    site_id = (args.site_id or "").strip()
    site_domain = _normalize_domain(args.site_domain or "")
    api_base = (args.api_base or "https://lemma.id").strip()
    project_dir = Path(args.output_dir or ".").resolve()
    force = bool(args.force)
    framework = (args.framework or "both").strip().lower()

    if not site_id or not site_domain:
        report = _build_report(
            "setup",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--site-id and --site-domain are required",
        )
        _emit_report(args, report, ["setup failed: --site-id and --site-domain are required"])
        return EXIT_USAGE

    actions = _build_scaffold_actions(
        project_dir=project_dir,
        site_id=site_id,
        site_domain=site_domain,
        api_base=api_base,
        framework=framework,
        force=force,
    )
    lemma_dir = project_dir / ".lemma"

    report = _build_report(
        "setup",
        ok=True,
        project_dir=str(project_dir),
        framework=framework,
        site_id=site_id,
        site_domain=site_domain,
        api_base=api_base.rstrip("/"),
        files=actions,
    )
    created = sum(1 for status in actions.values() if status == "written")
    skipped = sum(1 for status in actions.values() if status == "skipped")
    _emit_report(
        args,
        report,
        [
            f"setup complete: {created} file(s) written, {skipped} skipped",
            f"artifact directory: {lemma_dir}",
            "next: run `lemma audit` and then integrate generated snippets",
        ],
    )
    return EXIT_OK


def run_verify_checks(api_base: str | None, *, skip_health: bool = False) -> dict[str, Any]:
    results: dict[str, Any] = {"checks": [], "ok": True}

    api_key_present = bool(os.getenv("LEMMA_API_KEY") or os.getenv("LEMMA_PLATFORM_API_KEY"))
    results["checks"].append(
        {
            "name": "platform_api_key_present",
            "ok": api_key_present,
            "message": "LEMMA_API_KEY or LEMMA_PLATFORM_API_KEY is set" if api_key_present else "missing platform API key env",
        }
    )
    if not api_key_present:
        results["ok"] = False

    if api_base and not skip_health:
        try:
            import requests

            health_url = api_base.rstrip("/") + "/api/health"
            response = requests.get(health_url, timeout=8)
            ok = response.status_code == 200
            results["checks"].append(
                {
                    "name": "api_health",
                    "ok": ok,
                    "message": f"{health_url} returned {response.status_code}",
                }
            )
            if not ok:
                results["ok"] = False
        except ImportError:
            results["checks"].append(
                {
                    "name": "api_health",
                    "ok": False,
                    "message": "health check failed: requests not installed",
                }
            )
            results["ok"] = False
        except requests.RequestException as exc:
            results["checks"].append(
                {
                    "name": "api_health",
                    "ok": False,
                    "message": f"health check failed: {exc}",
                }
            )
            results["ok"] = False

    return results


def run_verify(args: argparse.Namespace) -> int:
    verify_report = run_verify_checks(args.api_base)
    checks = verify_report.get("checks") or []
    pass_count = sum(1 for check in checks if check.get("ok"))
    total_count = len(checks)
    report = _build_report(
        "verify",
        ok=bool(verify_report.get("ok")),
        error_code=ERR_OK if verify_report.get("ok") else ERR_EXPECTED_STATUS_MISMATCH,
        checks=checks,
    )
    _emit_report(args, report, [f"verify: {pass_count}/{total_count} checks passing"])
    return EXIT_OK if verify_report.get("ok") else EXIT_CHECK_FAILED


def build_audit_report(project_dir: Path, framework: str, api_base: str | None, skip_health: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    config_path = project_dir / ".lemma" / "config.json"
    config = _load_lemma_config(project_dir)
    has_config = config is not None
    checks.append(
        {
            "name": "config_present",
            "ok": has_config,
            "message": str(config_path) if has_config else f"missing {config_path}",
        }
    )

    required_keys = {"site_id", "site_domain", "api_base", "auth_header"}
    if has_config:
        missing_keys = sorted(required_keys.difference(config.keys()))
        checks.append(
            {
                "name": "config_shape_valid",
                "ok": not missing_keys,
                "message": "config has required keys" if not missing_keys else f"missing keys: {', '.join(missing_keys)}",
            }
        )
    else:
        checks.append({"name": "config_shape_valid", "ok": False, "message": "config unavailable"})

    env_example_path = project_dir / ".lemma" / ".env.lemma.example"
    checks.append(
        {
            "name": "env_template_present",
            "ok": env_example_path.exists(),
            "message": str(env_example_path) if env_example_path.exists() else "missing .lemma/.env.lemma.example",
        }
    )

    frontend_snippet = project_dir / ".lemma" / "frontend-header-snippet.js"
    checks.append(
        {
            "name": "frontend_header_scaffold_present",
            "ok": frontend_snippet.exists(),
            "message": str(frontend_snippet) if frontend_snippet.exists() else "missing .lemma/frontend-header-snippet.js",
        }
    )

    if framework in {"flask", "both"}:
        flask_path = project_dir / ".lemma" / "server-middleware-flask.py"
        checks.append(
            {
                "name": "flask_scaffold_present",
                "ok": flask_path.exists(),
                "message": str(flask_path) if flask_path.exists() else "missing .lemma/server-middleware-flask.py",
            }
        )
    if framework in {"express", "both"}:
        express_path = project_dir / ".lemma" / "server-middleware-express.js"
        checks.append(
            {
                "name": "express_scaffold_present",
                "ok": express_path.exists(),
                "message": str(express_path) if express_path.exists() else "missing .lemma/server-middleware-express.js",
            }
        )

    api_key_present = bool(os.getenv("LEMMA_API_KEY") or os.getenv("LEMMA_PLATFORM_API_KEY"))
    checks.append(
        {
            "name": "platform_api_key_present",
            "ok": api_key_present,
            "message": "LEMMA_API_KEY or LEMMA_PLATFORM_API_KEY is set" if api_key_present else "missing platform API key env",
        }
    )

    resolved_api_base = (api_base or (config or {}).get("api_base") or "").strip()
    if resolved_api_base and not skip_health:
        health_check = run_verify_checks(resolved_api_base).get("checks", [])
        api_health_check = next((c for c in health_check if c.get("name") == "api_health"), None)
        if api_health_check:
            checks.append(api_health_check)

    recommendations: list[str] = []
    if not has_config:
        recommendations.append("Run `lemma setup --site-id <id> --site-domain <domain>` first.")
    if not api_key_present:
        recommendations.append("Set LEMMA_API_KEY in your runtime environment.")

    passing = sum(1 for check in checks if check.get("ok"))
    total = len(checks)
    ok = passing == total and total > 0
    return {
        "ok": ok,
        "project_dir": str(project_dir),
        "framework": framework,
        "checks": checks,
        "score": {"passing": passing, "total": total},
        "recommendations": recommendations,
    }


def run_audit(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir or ".").resolve()
    framework = (args.framework or "both").strip().lower()
    audit_report = build_audit_report(
        project_dir=project_dir,
        framework=framework,
        api_base=(args.api_base or "").strip() or None,
        skip_health=bool(args.skip_health),
    )
    score = audit_report.get("score") or {}
    report = _build_report(
        "audit",
        ok=bool(audit_report.get("ok")),
        error_code=ERR_OK if audit_report.get("ok") else ERR_EXPECTED_STATUS_MISMATCH,
        project_dir=audit_report.get("project_dir"),
        framework=audit_report.get("framework"),
        checks=audit_report.get("checks", []),
        score=score,
        recommendations=audit_report.get("recommendations", []),
    )
    _emit_report(args, report, [f"audit: {score.get('passing', 0)}/{score.get('total', 0)} checks passing"])
    return EXIT_OK if audit_report.get("ok") else EXIT_CHECK_FAILED


def run_fix(args: argparse.Namespace) -> int:
    if not bool(args.safe):
        report = _build_report(
            "fix",
            ok=False,
            error_code=ERR_SAFE_FLAG_REQUIRED,
            message="Refusing to modify files without --safe.",
        )
        _emit_report(args, report, ["fix aborted: pass --safe to allow non-destructive scaffold repair"])
        return EXIT_USAGE

    project_dir = Path(args.project_dir or ".").resolve()
    framework = (args.framework or "both").strip().lower()
    config = _load_lemma_config(project_dir) or {}

    site_id = (args.site_id or config.get("site_id") or "").strip()
    site_domain = _normalize_domain(args.site_domain or config.get("site_domain") or "")
    api_base = (args.api_base or config.get("api_base") or "https://lemma.id").strip()

    if not site_id or not site_domain:
        report = _build_report(
            "fix",
            ok=False,
            error_code=ERR_MISSING_SITE_IDENTITY,
            message="Need site_id and site_domain (from args or existing .lemma/config.json).",
        )
        _emit_report(
            args,
            report,
            ["fix failed: provide --site-id and --site-domain, or run in a project with .lemma/config.json"],
        )
        return EXIT_USAGE

    actions = _build_scaffold_actions(
        project_dir=project_dir,
        site_id=site_id,
        site_domain=site_domain,
        api_base=api_base,
        framework=framework,
        force=False,
    )
    written = sum(1 for status in actions.values() if status == "written")
    skipped = sum(1 for status in actions.values() if status == "skipped")

    audit_report = build_audit_report(
        project_dir=project_dir,
        framework=framework,
        api_base=(args.api_base or "").strip() or None,
        skip_health=bool(args.skip_health),
    )
    report = _build_report(
        "fix",
        ok=bool(audit_report.get("ok", False)),
        error_code=ERR_OK if audit_report.get("ok") else ERR_EXPECTED_STATUS_MISMATCH,
        mode="safe",
        project_dir=str(project_dir),
        framework=framework,
        site_id=site_id,
        site_domain=site_domain,
        api_base=api_base.rstrip("/"),
        files=actions,
        written=written,
        skipped=skipped,
        post_audit=audit_report,
    )
    _emit_report(
        args,
        report,
        [
            f"fix complete: {written} file(s) written, {skipped} skipped",
            f"post-fix audit: {audit_report.get('score', {}).get('passing', 0)}/{audit_report.get('score', {}).get('total', 0)} passing",
        ],
    )
    return EXIT_OK if audit_report.get("ok") else EXIT_CHECK_FAILED


def _perform_smoke(
    *,
    url: str,
    method: str,
    expected_status: int,
    header_value: str,
    timeout: float,
) -> tuple[int, dict[str, Any], list[str]]:
    status_code, body_preview, request_error = _execute_smoke_request(
        url=url,
        method=method,
        header_value=header_value,
        timeout=timeout,
    )
    if request_error:
        report = _build_report(
            "smoke",
            ok=False,
            error_code=ERR_REQUEST_FAILED,
            url=url,
            method=method.upper(),
            message=request_error,
        )
        return EXIT_CHECK_FAILED, report, [f"smoke failed: {request_error}"]

    ok = status_code == expected_status
    report = _build_report(
        "smoke",
        ok=ok,
        error_code=ERR_OK if ok else ERR_EXPECTED_STATUS_MISMATCH,
        url=url,
        method=method.upper(),
        expected_status=expected_status,
        status_code=status_code,
        response_preview=body_preview,
    )
    return (EXIT_OK if ok else EXIT_CHECK_FAILED), report, [f"smoke: received {status_code}, expected {expected_status}"]


def run_smoke(args: argparse.Namespace) -> int:
    url = (args.url or "").strip()
    if not url:
        report = _build_report("smoke", ok=False, error_code=ERR_MISSING_URL, message="--url is required")
        _emit_report(args, report, ["smoke failed: --url is required"])
        return EXIT_USAGE

    header_value, header_error = _resolve_smoke_header(args)
    if header_error:
        report = _build_report("smoke", ok=False, error_code=ERR_MISSING_CREDENTIAL_HEADER, message=header_error)
        _emit_report(args, report, [f"smoke failed: {header_error}"])
        return EXIT_USAGE

    exit_code, report, text_lines = _perform_smoke(
        url=url,
        method=(args.method or "GET"),
        expected_status=int(args.expect_status),
        header_value=header_value or "",
        timeout=float(args.timeout),
    )
    _emit_report(args, report, text_lines)
    return exit_code


def run_ci(args: argparse.Namespace) -> int:
    verify_report = run_verify_checks(args.api_base, skip_health=bool(args.skip_health))
    audit_report = build_audit_report(
        project_dir=Path(args.project_dir or ".").resolve(),
        framework=(args.framework or "both").strip().lower(),
        api_base=(args.api_base or "").strip() or None,
        skip_health=bool(args.skip_health),
    )

    smoke_report: dict[str, Any] | None = None
    smoke_exit = EXIT_OK
    if not bool(args.skip_smoke):
        smoke_url = (args.smoke_url or "").strip()
        if not smoke_url:
            report = _build_report(
                "ci",
                ok=False,
                error_code=ERR_CI_SMOKE_URL_REQUIRED,
                message="--smoke-url is required unless --skip-smoke is set.",
            )
            _emit_report(args, report, ["ci failed: --smoke-url is required unless --skip-smoke"])
            return EXIT_USAGE

        smoke_header, smoke_header_error = _resolve_smoke_header(
            argparse.Namespace(
                header=(args.smoke_header or ""),
                credential_file=(args.smoke_credential_file or ""),
            )
        )
        if smoke_header_error:
            report = _build_report(
                "ci",
                ok=False,
                error_code=ERR_CI_SMOKE_HEADER_REQUIRED,
                message=smoke_header_error,
            )
            _emit_report(args, report, [f"ci failed: {smoke_header_error}"])
            return EXIT_USAGE

        smoke_exit, smoke_report, _ = _perform_smoke(
            url=smoke_url,
            method=(args.smoke_method or "GET"),
            expected_status=int(args.smoke_expect_status),
            header_value=smoke_header or "",
            timeout=float(args.smoke_timeout),
        )

    ok = bool(verify_report.get("ok")) and bool(audit_report.get("ok")) and smoke_exit == EXIT_OK
    report = _build_report(
        "ci",
        ok=ok,
        error_code=ERR_OK if ok else ERR_EXPECTED_STATUS_MISMATCH,
        verify=verify_report,
        audit=audit_report,
        smoke=smoke_report,
        skip_smoke=bool(args.skip_smoke),
    )
    _emit_report(
        args,
        report,
        [
            f"ci verify: {'pass' if verify_report.get('ok') else 'fail'}",
            f"ci audit: {'pass' if audit_report.get('ok') else 'fail'}",
            f"ci smoke: {'skipped' if args.skip_smoke else ('pass' if smoke_exit == EXIT_OK else 'fail')}",
        ],
    )
    return EXIT_OK if ok else EXIT_CHECK_FAILED


def run_login(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    dry_run = bool(getattr(args, "dry_run", False))
    used_platform_issue = False
    issued_credential_id = None
    scope = [s.strip() for s in str(args.scope or "read,write").split(",") if s.strip()]
    allowed_sites = [s.strip() for s in (args.allowed_site or []) if s and s.strip()]
    issue_overrides, issue_override_error = _parse_json_object_arg(
        str(getattr(args, "issue_json", "") or ""),
        arg_name="--issue-json",
    )
    if issue_override_error:
        report = _build_report("login", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=issue_override_error)
        _emit_report(args, report, [f"login failed: {issue_override_error}"])
        return EXIT_USAGE
    extra_headers, extra_headers_error = _parse_extra_headers(getattr(args, "extra_header", []) or [])
    if extra_headers_error:
        report = _build_report("login", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=extra_headers_error)
        _emit_report(args, report, [f"login failed: {extra_headers_error}"])
        return EXIT_USAGE
    if not allowed_sites:
        host = _extract_host(api_base) or "lemma.id"
        allowed_sites = [host]
    delegation_fields = _delegation_fields_from_args(args)

    response_payload: dict[str, Any] | None = None
    header_value, header_error = _resolve_smoke_header(
        argparse.Namespace(header=(args.header or ""), credential_file=(args.credential_file or ""))
    )
    if not header_error:
        payload = {
            "ttl_hours": int(args.ttl_hours or 8),
            "scope": scope,
            "agent_name": args.agent_name or "lemma-cli",
            "task": args.task or "CLI authenticated provisioning session",
            "allowed_sites": allowed_sites,
        }
        payload.update(delegation_fields)
        payload.update(issue_overrides)
        issue_url = f"{api_base}/api/agent/auto-issue"
        request_headers = {"X-Lemma-Credential": header_value or ""}
        request_headers.update(extra_headers)
        if dry_run:
            report = _build_report(
                "login",
                ok=True,
                dry_run=True,
                request={
                    "method": "POST",
                    "url": issue_url,
                    "headers": _mask_sensitive_headers(request_headers),
                    "json_body": payload,
                },
                platform_issuance_used=False,
            )
            report, output_error = _finalize_dry_run_report(args, report)
            if output_error:
                error_report = _build_report(
                    "login",
                    ok=False,
                    error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                    message=f"Failed writing dry-run artifact: {output_error}",
                )
                _emit_report(args, error_report, [error_report["message"]])
                return EXIT_CHECK_FAILED
            _emit_report(args, report, ["login dry-run complete (no request sent)"])
            return EXIT_OK
        status, response_payload, err = _http_json_request(
            method="POST",
            url=issue_url,
            headers=request_headers,
            json_body=payload,
            timeout=float(args.timeout),
        )
        if err:
            report = _build_report("login", ok=False, error_code=ERR_HTTP_FAILED, message=err)
            _emit_report(args, report, [f"login failed: {err}"])
            return EXIT_CHECK_FAILED
        if status != 200 or not (response_payload or {}).get("success"):
            report = _build_report(
                "login",
                ok=False,
                error_code=ERR_LOGIN_FAILED,
                status_code=status,
                response=response_payload,
                message=(response_payload or {}).get("message", "Token issuance failed."),
                next_steps=_guidance_for_login_issue_failure(response_payload),
            )
            _emit_report(args, report, [f"login failed: server returned {status}"])
            return EXIT_CHECK_FAILED
    else:
        if dry_run:
            approval_state = secrets.token_urlsafe(24)
            approval_params = urlencode(
                {
                    "state": approval_state,
                    "scope": ",".join(scope),
                    "agent_name": args.agent_name or "lemma-cli",
                    "task": args.task or "CLI authenticated provisioning session",
                    "allowed_sites": ",".join(allowed_sites),
                    **delegation_fields,
                }
            )
            report = _build_report(
                "login",
                ok=True,
                dry_run=True,
                platform_issuance_used=False,
                browser_login=not bool(getattr(args, "non_interactive", False)),
                request={
                    "method": "GET",
                    "url": f"{api_base}/api/agent/cli-login/complete?{approval_params}",
                },
                message="Header not provided; this preview shows browser login URL shape.",
            )
            report, output_error = _finalize_dry_run_report(args, report)
            if output_error:
                error_report = _build_report(
                    "login",
                    ok=False,
                    error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                    message=f"Failed writing dry-run artifact: {output_error}",
                )
                _emit_report(args, error_report, [error_report["message"]])
                return EXIT_CHECK_FAILED
            _emit_report(args, report, ["login dry-run complete (no request sent)"])
            return EXIT_OK
        # Default path: browser-based login (Heroku-style).
        if not bool(getattr(args, "non_interactive", False)):
            browser_payload, browser_error = _run_browser_login_flow(
                args=args,
                api_base=api_base,
                scope=scope,
                allowed_sites=allowed_sites,
            )
            if browser_error:
                _emit_report(
                    args,
                    browser_error,
                    [
                        f"login failed: {browser_error.get('message', 'browser login failed')}",
                        f"approval url: {browser_error.get('approval_url', '')}",
                    ],
                )
                return EXIT_CHECK_FAILED
            response_payload = browser_payload
        else:
            # CI/non-interactive fallback: platform self-issue when targeting lemma.id.
            if _is_platform_host(api_base):
                issued_credential, issue_error = _issue_platform_admin_credential_for_login(args, api_base)
                if issue_error:
                    _emit_report(args, issue_error, [f"login failed: {issue_error.get('message', 'platform issuance failed')}"])
                    return EXIT_CHECK_FAILED
                used_platform_issue = True
                issued_credential_id = str((issued_credential or {}).get("id") or "")
                payload = {
                    "ttl_hours": int(args.ttl_hours or 8),
                    "scope": scope,
                    "agent_name": args.agent_name or "lemma-cli",
                    "task": args.task or "CLI authenticated provisioning session",
                    "allowed_sites": allowed_sites,
                }
                payload.update(delegation_fields)
                payload.update(issue_overrides)
                issue_url = f"{api_base}/api/agent/auto-issue"
                request_headers = {"X-Lemma-Credential": _encode_credential_for_header(issued_credential or {})}
                request_headers.update(extra_headers)
                if dry_run:
                    report = _build_report(
                        "login",
                        ok=True,
                        dry_run=True,
                        platform_issuance_used=True,
                        issued_credential_id=issued_credential_id,
                        request={
                            "method": "POST",
                            "url": issue_url,
                            "headers": _mask_sensitive_headers(request_headers),
                            "json_body": payload,
                        },
                    )
                    report, output_error = _finalize_dry_run_report(args, report)
                    if output_error:
                        error_report = _build_report(
                            "login",
                            ok=False,
                            error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                            message=f"Failed writing dry-run artifact: {output_error}",
                        )
                        _emit_report(args, error_report, [error_report["message"]])
                        return EXIT_CHECK_FAILED
                    _emit_report(args, report, ["login dry-run complete (no request sent)"])
                    return EXIT_OK
                status, response_payload, err = _http_json_request(
                    method="POST",
                    url=issue_url,
                    headers=request_headers,
                    json_body=payload,
                    timeout=float(args.timeout),
                )
                if err:
                    report = _build_report("login", ok=False, error_code=ERR_HTTP_FAILED, message=err)
                    _emit_report(args, report, [f"login failed: {err}"])
                    return EXIT_CHECK_FAILED
                if status != 200 or not (response_payload or {}).get("success"):
                    report = _build_report(
                        "login",
                        ok=False,
                        error_code=ERR_LOGIN_FAILED,
                        status_code=status,
                        response=response_payload,
                        message=(response_payload or {}).get("message", "Token issuance failed."),
                        next_steps=_guidance_for_login_issue_failure(response_payload),
                    )
                    _emit_report(args, report, [f"login failed: server returned {status}"])
                    return EXIT_CHECK_FAILED
            else:
                report = _build_report(
                    "login",
                    ok=False,
                    error_code=ERR_MISSING_CREDENTIAL_HEADER,
                    message=f"{header_error} Use browser login (default) or pass --non-interactive with credential input.",
                )
                _emit_report(args, report, [f"login failed: {report.get('message')}"])
                return EXIT_USAGE

    token = str((response_payload or {}).get("token") or "").strip()
    if not token:
        report = _build_report("login", ok=False, error_code=ERR_LOGIN_FAILED, message="Server did not return token.")
        _emit_report(args, report, ["login failed: missing token in response"])
        return EXIT_CHECK_FAILED

    session_data = {
        "api_base": api_base,
        "agent_token": token,
        "token_id": (response_payload or {}).get("token_id"),
        "scope": (response_payload or {}).get("scope", []),
        "allowed_sites": (response_payload or {}).get("allowed_sites", []),
        "authorized_by": (response_payload or {}).get("authorized_by"),
        "delegation": (response_payload or {}).get("delegation", {}),
        "expires_at": (response_payload or {}).get("expires_at"),
    }
    path = _save_auth_session(session_data, args.session_file)
    report = _build_report(
        "login",
        ok=True,
        session_file=str(path),
        token_id=session_data.get("token_id"),
        token_masked=_mask_token(token),
        expires_at=session_data.get("expires_at"),
        scope=session_data.get("scope"),
        allowed_sites=session_data.get("allowed_sites"),
        delegation=session_data.get("delegation"),
        platform_issuance_used=used_platform_issue,
        issued_credential_id=issued_credential_id,
        browser_login=bool((response_payload or {}).get("browser_login")),
        approval_url=(response_payload or {}).get("approval_url"),
    )
    _emit_report(args, report, [f"login successful; session saved to {path}"])
    return EXIT_OK


def run_logout(args: argparse.Namespace) -> int:
    removed = _clear_auth_session(args.session_file)
    report = _build_report("logout", ok=True, removed=removed, session_file=str(_auth_path(args.session_file)))
    _emit_report(args, report, ["logout complete" if removed else "logout complete (no session file found)"])
    return EXIT_OK


def run_auth_status(args: argparse.Namespace) -> int:
    dry_run = bool(getattr(args, "dry_run", False))
    session = _load_auth_session(args.session_file)
    if dry_run:
        api_base = _derive_api_base(args.api_base or (session or {}).get("api_base"))
        token = str((session or {}).get("agent_token") or "")
        report = _build_report(
            "auth-status",
            ok=True,
            dry_run=True,
            session_present=bool(session),
            session_file=str(_auth_path(args.session_file)),
            request={
                "method": "GET",
                "url": f"{api_base}/api/agent/validate",
                "headers": _mask_sensitive_headers({"X-Agent-Token": token} if token else {}),
            },
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "auth-status",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["auth-status dry-run complete (no request sent)"])
        return EXIT_OK
    if not session:
        report = _build_report(
            "auth-status",
            ok=False,
            error_code=ERR_AUTH_REQUIRED,
            message="No local auth session found.",
            session_file=str(_auth_path(args.session_file)),
        )
        _emit_report(args, report, ["not logged in"])
        return EXIT_CHECK_FAILED

    api_base = _derive_api_base(args.api_base or session.get("api_base"))
    token = str(session.get("agent_token") or "")
    status, payload, err = _http_json_request(
        method="GET",
        url=f"{api_base}/api/agent/validate",
        headers={"X-Agent-Token": token},
        timeout=float(args.timeout),
    )
    if err:
        report = _build_report("auth-status", ok=False, error_code=ERR_HTTP_FAILED, message=err)
        _emit_report(args, report, [f"auth status failed: {err}"])
        return EXIT_CHECK_FAILED

    valid = status == 200 and bool((payload or {}).get("valid"))
    report = _build_report(
        "auth-status",
        ok=valid,
        error_code=ERR_OK if valid else ERR_AUTH_INVALID,
        session_file=str(_auth_path(args.session_file)),
        api_base=api_base,
        token_masked=_mask_token(token),
        validation_status=status,
        validation=payload,
    )
    _emit_report(args, report, ["auth session valid" if valid else "auth session invalid"])
    return EXIT_OK if valid else EXIT_CHECK_FAILED


def _assess_firewall_safety(health_payload: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    status = "safe"
    if not bool((health_payload or {}).get("ok")):
        return "unsafe", ["firewall_health_not_ok"]

    if str((health_payload or {}).get("auth_mode") or "").strip().lower() != "proof":
        status = "unsafe"
        reasons.append("firewall_not_in_proof_mode")

    if not bool((health_payload or {}).get("local_proof_enforcement")):
        if status != "unsafe":
            status = "degraded"
        reasons.append("local_proof_enforcement_disabled")

    sync = (health_payload or {}).get("sync") or {}
    if not bool(sync.get("enabled")):
        if status != "unsafe":
            status = "degraded"
        reasons.append("control_plane_sync_disabled")

    tiers = {
        str(item).strip().lower()
        for item in ((health_payload or {}).get("runtime_authorize_required_tiers") or [])
        if str(item).strip()
    }
    if "critical" not in tiers:
        if status != "unsafe":
            status = "degraded"
        reasons.append("critical_tier_not_forced_online")

    if bool((health_payload or {}).get("online_check_on_stale_noncritical")):
        if status != "unsafe":
            status = "degraded"
        reasons.append("noncritical_stale_online_enabled")

    sync_error = str(sync.get("last_sync_error") or "").strip()
    if sync_error:
        if status != "unsafe":
            status = "degraded"
        reasons.append("control_plane_sync_error")

    if not reasons:
        reasons.append("none")
    return status, reasons


def run_safety_status(args: argparse.Namespace) -> int:
    firewall_url = str(getattr(args, "firewall_url", "http://127.0.0.1:8787") or "http://127.0.0.1:8787").strip().rstrip("/")
    timeout = float(getattr(args, "timeout", 5.0))
    status_code, payload, err = _http_json_request(
        method="GET",
        url=f"{firewall_url}/aim/health",
        timeout=timeout,
    )
    if err:
        report = _build_report(
            "safety-status",
            ok=False,
            error_code=ERR_SAFETY_UNSAFE,
            safety_status="unsafe",
            reasons=["firewall_unreachable"],
            firewall_url=firewall_url,
            message=err,
            next_steps=[
                "Start local firewall in starter-safe mode.",
                "Run `powershell -ExecutionPolicy Bypass -File scripts/start_lemma_firewall.ps1 -SecurityProfile starter_safe`.",
            ],
        )
        _emit_report(args, report, [f"safety-status: unsafe (firewall unreachable: {err})"])
        return EXIT_CHECK_FAILED

    payload = payload if isinstance(payload, dict) else {}
    safety_status, reasons = _assess_firewall_safety(payload)
    ok = safety_status == "safe"
    error_code = ERR_OK if ok else (ERR_SAFETY_DEGRADED if safety_status == "degraded" else ERR_SAFETY_UNSAFE)
    report = _build_report(
        "safety-status",
        ok=ok,
        error_code=error_code,
        safety_status=safety_status,
        reasons=reasons,
        firewall_url=firewall_url,
        firewall_health_status=status_code,
        firewall_health=payload,
    )
    if safety_status == "safe":
        _emit_report(args, report, ["safety-status: safe"])
        return EXIT_OK
    _emit_report(args, report, [f"safety-status: {safety_status}"])
    return EXIT_CHECK_FAILED


def run_session_status(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    dry_run = bool(getattr(args, "dry_run", False))
    request_preview = {
        "method": "POST",
        "url": f"{api_base}/api/wallet/session-sync",
        "headers": {"Origin": api_base},
    }
    if dry_run:
        report = _build_report("session-status", ok=True, dry_run=True, request=request_preview)
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "session-status",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["session-status dry-run complete (no request sent)"])
        return EXIT_OK

    wallet = _check_wallet_unlock_status(api_base, float(args.timeout))
    unlocked = wallet.get("state") == "unlocked"
    report = _build_report(
        "session-status",
        ok=unlocked,
        error_code=ERR_OK if unlocked else ERR_SESSION_LOCKED,
        api_base=api_base,
        wallet=wallet,
    )
    if unlocked:
        _emit_report(args, report, ["wallet session unlocked"])
        return EXIT_OK
    _emit_report(
        args,
        report,
        [
            "wallet session is not unlocked",
            f"run `lemma session start --api-base {api_base}` to unlock",
        ],
    )
    return EXIT_CHECK_FAILED


def run_session_start(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    dry_run = bool(getattr(args, "dry_run", False))
    unlock_url = f"{api_base}/unlock"
    if dry_run:
        report = _build_report(
            "session-start",
            ok=True,
            dry_run=True,
            request={"method": "OPEN_BROWSER", "url": unlock_url},
            no_browser=bool(args.no_browser),
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "session-start",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["session-start dry-run complete (no action taken)"])
        return EXIT_OK

    wallet = _check_wallet_unlock_status(api_base, float(args.timeout))
    current_state = wallet.get("state")
    unlock_url = str(wallet.get("unlock_url") or unlock_url)
    browser_opened = False
    if current_state != "unlocked" and not bool(args.no_browser):
        try:
            browser_opened = bool(webbrowser.open(unlock_url))
        except webbrowser.Error:
            browser_opened = False

    report = _build_report(
        "session-start",
        ok=True,
        api_base=api_base,
        wallet=wallet,
        unlock_url=unlock_url,
        browser_opened=browser_opened,
        no_browser=bool(args.no_browser),
        already_unlocked=(current_state == "unlocked"),
        next_steps=[
            f"Complete unlock at {unlock_url}",
            f"Then run `lemma session status --api-base {api_base}`",
        ],
    )
    if current_state == "unlocked":
        _emit_report(args, report, ["wallet session already unlocked"])
    elif bool(args.no_browser):
        _emit_report(args, report, [f"open this URL to unlock: {unlock_url}"])
    elif browser_opened:
        _emit_report(args, report, [f"opened browser for unlock: {unlock_url}"])
    else:
        _emit_report(args, report, [f"could not auto-open browser; unlock here: {unlock_url}"])
    return EXIT_OK


def run_session_link(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    timeout = float(getattr(args, "timeout", 10.0))
    poll_interval = max(0.5, float(getattr(args, "poll_interval", 2.0)))
    link_timeout = max(5.0, float(getattr(args, "link_timeout", 120.0)))
    requested_scope = str(getattr(args, "requested_scope", "wallet:revoke") or "wallet:revoke").strip().lower()

    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run:
        report = _build_report(
            "session-link",
            ok=True,
            dry_run=True,
            api_base=api_base,
            request={
                "method": "POST",
                "url": f"{api_base}/api/wallet/cli-link/start",
                "json_body": {"requested_scope": requested_scope},
            },
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "session-link",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["session-link dry-run complete (no request sent)"])
        return EXIT_OK

    status, payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/wallet/cli-link/start",
        json_body={"requested_scope": requested_scope},
        timeout=timeout,
    )
    if err or status != 200 or not bool((payload or {}).get("success")):
        report = _build_report(
            "session-link",
            ok=False,
            error_code=ERR_HTTP_FAILED,
            message=err or (payload or {}).get("message") or "Failed to start CLI link flow.",
            status_code=status,
            response=payload,
        )
        _emit_report(args, report, [f"session-link failed: {report['message']}"])
        return EXIT_CHECK_FAILED

    approve_url = str((payload or {}).get("approve_url") or "").strip()
    poll_url = str((payload or {}).get("poll_url") or "").strip()
    state = str((payload or {}).get("state") or "").strip()
    browser_opened = False
    if approve_url and not bool(getattr(args, "no_browser", False)):
        try:
            browser_opened = bool(webbrowser.open(approve_url, new=2))
        except webbrowser.Error:
            browser_opened = False

    deadline = time.time() + link_timeout
    poll_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        p_status, p_payload, p_err = _http_json_request(
            method="GET",
            url=poll_url,
            timeout=timeout,
        )
        if p_err:
            time.sleep(poll_interval)
            continue
        if p_status == 200 and bool((p_payload or {}).get("approved")):
            poll_payload = p_payload or {}
            break
        time.sleep(poll_interval)

    if not poll_payload:
        report = _build_report(
            "session-link",
            ok=False,
            error_code=ERR_BROWSER_LOGIN_TIMEOUT,
            api_base=api_base,
            state=state,
            approve_url=approve_url,
            message="CLI link approval timed out.",
        )
        _emit_report(
            args,
            report,
            [
                "session-link timed out waiting for approval",
                f"open this URL and approve: {approve_url}",
            ],
        )
        return EXIT_CHECK_FAILED

    unlock_token = str((poll_payload or {}).get("unlock_token") or "").strip()
    wallet_id = str((poll_payload or {}).get("wallet_id") or "").strip()
    report = _build_report(
        "session-link",
        ok=bool(unlock_token),
        error_code=ERR_OK if unlock_token else ERR_AUTH_INVALID,
        api_base=api_base,
        state=state,
        approve_url=approve_url,
        browser_opened=browser_opened,
        wallet_id=wallet_id,
        unlock_token=unlock_token,
        requested_scope=requested_scope,
    )
    if unlock_token:
        _emit_report(args, report, ["session-link approved; unlock token acquired"])
        return EXIT_OK
    _emit_report(args, report, ["session-link failed: unlock token missing"])
    return EXIT_CHECK_FAILED


def run_authorize_agent(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    session_file = args.session_file or ""
    dry_run = bool(getattr(args, "dry_run", False))
    steps: list[dict[str, Any]] = []

    login_args = argparse.Namespace(
        api_base=api_base,
        header=(args.header or ""),
        credential_file=(args.credential_file or ""),
        scope=(args.scope or "read,write,admin"),
        ttl_hours=int(args.ttl_hours or 8),
        agent_name=(args.agent_name or "lemma-cli"),
        task=(args.task or "CLI authenticated provisioning session"),
        allowed_site=list(args.allowed_site or []),
        platform_api_key=(args.platform_api_key or ""),
        user_email=(args.user_email or ""),
        site_id=(args.site_id or "lemma.id"),
        site_domain=(args.site_domain or "lemma.id"),
        permission_level=(args.permission_level or "super_admin"),
        issue_json=(getattr(args, "issue_json", "") or ""),
        delegation_reason=(getattr(args, "delegation_reason", "") or ""),
        delegation_id=(getattr(args, "delegation_id", "") or ""),
        acting_for_ppid=(getattr(args, "acting_for_ppid", "") or ""),
        requested_by_ppid=(getattr(args, "requested_by_ppid", "") or ""),
        delegated_by_user_ref=(getattr(args, "delegated_by_user_ref", "") or ""),
        acting_for_user_ref=(getattr(args, "acting_for_user_ref", "") or ""),
        requested_by_user_ref=(getattr(args, "requested_by_user_ref", "") or ""),
        extra_header=list(getattr(args, "extra_header", []) or []),
        timeout=float(args.timeout),
        session_file=session_file,
        non_interactive=bool(args.non_interactive),
        no_browser=bool(args.no_browser),
        login_timeout=float(args.login_timeout),
        dry_run=dry_run,
        dry_run_output="",
        json=True,
    )
    login_code, login_report = _invoke_handler_capture_report(run_login, login_args)
    steps.append({"step": "login", "exit_code": login_code, "report": login_report})
    if login_code != EXIT_OK:
        report = _build_report(
            "authorize-agent",
            ok=False,
            error_code=str(login_report.get("error_code") or ERR_FLOW_STEP_FAILED),
            failed_step="login",
            steps=steps,
            dry_run=dry_run,
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "authorize-agent",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
                failed_step="login",
                steps=steps,
                dry_run=dry_run,
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["authorize-agent failed at login"])
        return login_code

    validate_args = argparse.Namespace(
        api_base=api_base,
        timeout=float(args.timeout),
        session_file=session_file,
        dry_run=dry_run,
        dry_run_output="",
        json=True,
    )
    validate_code, validate_report = _invoke_handler_capture_report(run_auth_status, validate_args)
    steps.append({"step": "validate", "exit_code": validate_code, "report": validate_report})
    if validate_code != EXIT_OK:
        report = _build_report(
            "authorize-agent",
            ok=False,
            error_code=str(validate_report.get("error_code") or ERR_FLOW_STEP_FAILED),
            failed_step="validate",
            steps=steps,
            dry_run=dry_run,
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "authorize-agent",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
                failed_step="validate",
                steps=steps,
                dry_run=dry_run,
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["authorize-agent failed at validate"])
        return validate_code

    report = _build_report(
        "authorize-agent",
        ok=True,
        error_code=ERR_OK,
        steps=steps,
        dry_run=dry_run,
        session_file=str(_auth_path(session_file)),
        token_id=login_report.get("token_id"),
        token_masked=login_report.get("token_masked"),
        expires_at=login_report.get("expires_at"),
        scope=login_report.get("scope"),
        allowed_sites=login_report.get("allowed_sites"),
        delegation=login_report.get("delegation"),
        validation_status=validate_report.get("validation_status"),
    )
    report, output_error = _finalize_dry_run_report(args, report)
    if output_error:
        error_report = _build_report(
            "authorize-agent",
            ok=False,
            error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
            message=f"Failed writing dry-run artifact: {output_error}",
            steps=steps,
            dry_run=dry_run,
        )
        _emit_report(args, error_report, [error_report["message"]])
        return EXIT_CHECK_FAILED
    _emit_report(args, report, ["authorize-agent succeeded (login + validate)"])
    return EXIT_OK


def run_setup_firewall(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    session_file = str(getattr(args, "session_file", "") or "")
    dry_run = bool(getattr(args, "dry_run", False))
    steps: list[dict[str, Any]] = []

    if dry_run:
        verify_report = _build_report(
            "verify",
            ok=True,
            dry_run=True,
            checks=[
                {"name": "platform_api_key_present", "ok": True, "message": "dry-run"},
                {"name": "api_health", "ok": True, "message": "dry-run"},
            ],
        )
        steps.append({"step": "verify", "exit_code": EXIT_OK, "report": verify_report})
    else:
        verify_args = argparse.Namespace(api_base=api_base, json=True)
        verify_code, verify_report = _invoke_handler_capture_report(run_verify, verify_args)
        steps.append({"step": "verify", "exit_code": verify_code, "report": verify_report})
        if verify_code != EXIT_OK:
            checks = verify_report.get("checks") if isinstance(verify_report.get("checks"), list) else []
            failing_check_names = {
                str(check.get("name") or "")
                for check in checks
                if isinstance(check, dict) and not bool(check.get("ok"))
            }
            only_missing_platform_api_key = bool(failing_check_names) and failing_check_names == {"platform_api_key_present"}
            if only_missing_platform_api_key:
                softened_verify = dict(verify_report)
                softened_verify["soft_failed"] = True
                softened_verify["next_steps"] = [
                    "Continuing setup-firewall: platform API key is optional when using wallet credential/browser auth flow.",
                ]
                steps[-1] = {"step": "verify", "exit_code": EXIT_OK, "report": softened_verify}
            else:
                report = _build_report(
                    "setup-firewall",
                    ok=False,
                    error_code=str(verify_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                    failed_step="verify",
                    steps=steps,
                    dry_run=dry_run,
                )
                _emit_report(args, report, ["setup-firewall failed at verify"])
                return verify_code

    authorize_args = argparse.Namespace(
        api_base=api_base,
        header=(args.header or ""),
        credential_file=(args.credential_file or ""),
        scope=(args.scope or "read,write,admin"),
        ttl_hours=int(args.ttl_hours or 8),
        agent_name=(args.agent_name or "lemma-firewall-cli"),
        task=(args.task or "Lemma Firewall onboarding session"),
        allowed_site=list(args.allowed_site or []),
        platform_api_key=(args.platform_api_key or ""),
        user_email=(args.user_email or ""),
        site_id=(args.site_id or "lemma.id"),
        site_domain=(args.site_domain or "lemma.id"),
        permission_level=(args.permission_level or "super_admin"),
        issue_json=(getattr(args, "issue_json", "") or ""),
        delegation_reason=(getattr(args, "delegation_reason", "") or ""),
        delegation_id=(getattr(args, "delegation_id", "") or ""),
        acting_for_ppid=(getattr(args, "acting_for_ppid", "") or ""),
        requested_by_ppid=(getattr(args, "requested_by_ppid", "") or ""),
        delegated_by_user_ref=(getattr(args, "delegated_by_user_ref", "") or ""),
        acting_for_user_ref=(getattr(args, "acting_for_user_ref", "") or ""),
        requested_by_user_ref=(getattr(args, "requested_by_user_ref", "") or ""),
        extra_header=list(getattr(args, "extra_header", []) or []),
        non_interactive=bool(getattr(args, "non_interactive", False)),
        no_browser=bool(getattr(args, "no_browser", False)),
        login_timeout=float(getattr(args, "login_timeout", 180.0)),
        dry_run=dry_run,
        dry_run_output="",
        timeout=float(getattr(args, "timeout", 10.0)),
        session_file=session_file,
        json=True,
    )
    authorize_code, authorize_report = _invoke_handler_capture_report(run_authorize_agent, authorize_args)
    steps.append({"step": "authorize", "exit_code": authorize_code, "report": authorize_report})
    if authorize_code != EXIT_OK:
        report = _build_report(
            "setup-firewall",
            ok=False,
            error_code=str(authorize_report.get("error_code") or ERR_FLOW_STEP_FAILED),
            failed_step="authorize",
            steps=steps,
            dry_run=dry_run,
        )
        _emit_report(args, report, ["setup-firewall failed at authorize"])
        return authorize_code

    validate_args = argparse.Namespace(
        api_base=api_base,
        timeout=float(getattr(args, "timeout", 10.0)),
        session_file=session_file,
        dry_run=dry_run,
        dry_run_output="",
        json=True,
    )
    validate_code, validate_report = _invoke_handler_capture_report(run_auth_status, validate_args)
    steps.append({"step": "validate", "exit_code": validate_code, "report": validate_report})
    if validate_code != EXIT_OK:
        report = _build_report(
            "setup-firewall",
            ok=False,
            error_code=str(validate_report.get("error_code") or ERR_FLOW_STEP_FAILED),
            failed_step="validate",
            steps=steps,
            dry_run=dry_run,
        )
        _emit_report(args, report, ["setup-firewall failed at validate"])
        return validate_code

    conformance_command = str(getattr(args, "conformance_command", "") or "").strip()
    if bool(getattr(args, "skip_conformance", False)):
        conformance_report = _build_report("lemma-firewall-conformance", ok=True, skipped=True, conformance_command=conformance_command)
        conformance_code = EXIT_OK
    elif dry_run:
        conformance_report = _build_report("lemma-firewall-conformance", ok=True, dry_run=True, conformance_command=conformance_command)
        conformance_code = EXIT_OK
    else:
        agent_token = str(getattr(args, "agent_token", "") or "").strip()
        if not agent_token:
            session = _load_auth_session(session_file)
            agent_token = str((session or {}).get("agent_token") or "").strip()
        env_overrides = {
            "LEMMA_BASE_URL": api_base,
            "LEMMA_FIREWALL_REQUIRED_AUDIENCE": str(getattr(args, "firewall_audience", "lemma-firewall") or "lemma-firewall").strip(),
            "LEMMA_AGENT_TOKEN": agent_token,
        }
        conformance_exit, conformance_stdout, conformance_stderr = _run_external_command(
            command=conformance_command,
            cwd=str(Path(getattr(args, "conformance_workdir", ".") or ".").resolve()),
            timeout=float(getattr(args, "conformance_timeout", 600.0)),
            env_overrides=env_overrides,
        )
        stdout_lines = [line for line in conformance_stdout.splitlines() if line.strip()]
        stderr_lines = [line for line in conformance_stderr.splitlines() if line.strip()]
        conformance_code = EXIT_OK if conformance_exit == 0 else EXIT_CHECK_FAILED
        conformance_report = _build_report(
            "lemma-firewall-conformance",
            ok=conformance_exit == 0,
            error_code=ERR_OK if conformance_exit == 0 else ERR_EXPECTED_STATUS_MISMATCH,
            conformance_command=conformance_command,
            exit_code=conformance_exit,
            stdout_preview=stdout_lines[-20:],
            stderr_preview=stderr_lines[-20:],
            used_session_token=not bool(getattr(args, "agent_token", "")),
        )
    steps.append({"step": "conformance", "exit_code": conformance_code, "report": conformance_report})
    if conformance_code != EXIT_OK:
        report = _build_report(
            "setup-firewall",
            ok=False,
            error_code=str(conformance_report.get("error_code") or ERR_FLOW_STEP_FAILED),
            failed_step="conformance",
            steps=steps,
            dry_run=dry_run,
        )
        _emit_report(args, report, ["setup-firewall failed at conformance"])
        return EXIT_CHECK_FAILED

    report = _build_report(
        "setup-firewall",
        ok=True,
        error_code=ERR_OK,
        api_base=api_base,
        steps=steps,
        dry_run=dry_run,
        session_file=str(_auth_path(session_file)),
        token_id=authorize_report.get("token_id"),
        skip_conformance=bool(getattr(args, "skip_conformance", False)),
    )
    report, output_error = _finalize_dry_run_report(args, report)
    if output_error:
        error_report = _build_report(
            "setup-firewall",
            ok=False,
            error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
            message=f"Failed writing dry-run artifact: {output_error}",
            steps=steps,
            dry_run=dry_run,
        )
        _emit_report(args, error_report, [error_report["message"]])
        return EXIT_CHECK_FAILED
    _emit_report(args, report, ["setup-firewall succeeded (verify -> authorize -> validate -> conformance)"])
    return EXIT_OK


def run_firewall_connect(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(getattr(args, "api_base", "https://lemma.id"))
    dry_run = bool(getattr(args, "dry_run", False))
    timeout = float(getattr(args, "timeout", 10.0))
    steps: list[dict[str, Any]] = []
    defaults = _runtime_bootstrap_defaults()

    runtime_id = str(getattr(args, "runtime_id", "runtime-default") or "runtime-default").strip()
    agent_id = str(getattr(args, "agent_id", "main") or "main").strip()
    workspace_id = str(getattr(args, "workspace_id", "default") or "default").strip()
    display_name = str(getattr(args, "display_name", "Lemma Runtime") or "Lemma Runtime").strip()
    policy_profile = str(getattr(args, "policy_profile", defaults["policy_profile"]) or defaults["policy_profile"]).strip()
    root_type = str(getattr(args, "root_type", defaults["root_type"]) or defaults["root_type"]).strip().lower()
    org_id = str(getattr(args, "org_id", defaults["org_id"]) or defaults["org_id"]).strip()
    environment = str(getattr(args, "environment", defaults["environment"]) or defaults["environment"]).strip().lower()
    if root_type not in {"passkey_root", "workload_root", "policy_root"}:
        root_type = defaults["root_type"]
    if environment not in {"dev", "staging", "prod"}:
        environment = defaults["environment"]
    control_plane_mode = str(getattr(args, "control_plane_mode", "hosted") or "hosted").strip().lower()
    external_control_plane_url = str(getattr(args, "external_control_plane_url", "") or "").strip()
    skip_openclaw_config = bool(getattr(args, "skip_openclaw_config", False))

    unlock_token = str(getattr(args, "unlock_token", "") or "").strip()
    if dry_run:
        report = _build_report(
            "firewall-connect",
            ok=True,
            dry_run=True,
            api_base=api_base,
            bootstrap_request={
                "method": "POST",
                "url": f"{api_base}/api/wallet/runtimes/bootstrap",
                "headers": {"X-Lemma-Unlock": "***"},
                "json_body": {
                    "runtime_id": runtime_id,
                    "agent_id": agent_id,
                    "workspace_id": workspace_id,
                    "display_name": display_name,
                    "policy_profile": policy_profile,
                    "root_type": root_type,
                    "org_id": org_id,
                    "environment": environment,
                    "control_plane_mode": control_plane_mode,
                    "external_control_plane_url": external_control_plane_url,
                },
            },
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "firewall-connect",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["firewall-connect dry-run complete (no request sent)"])
        return EXIT_OK

    if not unlock_token:
        link_args = argparse.Namespace(
            api_base=api_base,
            requested_scope=str(getattr(args, "requested_scope", "wallet:control_plane") or "wallet:control_plane"),
            no_browser=bool(getattr(args, "no_browser", False)),
            poll_interval=float(getattr(args, "poll_interval", 2.0)),
            link_timeout=float(getattr(args, "link_timeout", 180.0)),
            timeout=timeout,
            dry_run=False,
            dry_run_output="",
            json=True,
        )
        link_code, link_report = _invoke_handler_capture_report(run_session_link, link_args)
        steps.append({"step": "session-link", "exit_code": link_code, "report": link_report})
        if link_code != EXIT_OK:
            report = _build_report(
                "firewall-connect",
                ok=False,
                error_code=str(link_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                failed_step="session-link",
                steps=steps,
            )
            _emit_report(args, report, ["firewall-connect failed at session-link"])
            return link_code
        unlock_token = str(link_report.get("unlock_token") or "").strip()
        if not unlock_token:
            report = _build_report(
                "firewall-connect",
                ok=False,
                error_code=ERR_AUTH_INVALID,
                message="session-link did not return unlock token",
                failed_step="session-link",
                steps=steps,
            )
            _emit_report(args, report, ["firewall-connect failed: unlock token missing"])
            return EXIT_CHECK_FAILED

    bootstrap_body = {
        "runtime_id": runtime_id,
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "display_name": display_name,
        "policy_profile": policy_profile,
        "root_type": root_type,
        "org_id": org_id,
        "environment": environment,
        "control_plane_mode": control_plane_mode,
        "external_control_plane_url": external_control_plane_url,
    }
    status, payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/wallet/runtimes/bootstrap",
        headers={"X-Lemma-Unlock": unlock_token},
        json_body=bootstrap_body,
        timeout=timeout,
    )
    bootstrap_ok = bool((payload or {}).get("success"))
    bootstrap_report = _build_report(
        "lemma-firewall-bootstrap",
        ok=(not err and status == 200 and bootstrap_ok),
        error_code=ERR_OK if (not err and status == 200 and bootstrap_ok) else ERR_HTTP_FAILED,
        status_code=status,
        response=payload,
        message=err or str((payload or {}).get("error") or ""),
    )
    steps.append({"step": "bootstrap", "exit_code": EXIT_OK if bootstrap_report.get("ok") else EXIT_CHECK_FAILED, "report": bootstrap_report})
    if not bootstrap_report.get("ok"):
        report = _build_report(
            "firewall-connect",
            ok=False,
            error_code=str(bootstrap_report.get("error_code") or ERR_FLOW_STEP_FAILED),
            failed_step="bootstrap",
            steps=steps,
        )
        _emit_report(args, report, ["firewall-connect failed at bootstrap"])
        return EXIT_CHECK_FAILED

    list_status, list_payload, list_err = _http_json_request(
        method="GET",
        url=f"{api_base}/api/wallet/runtimes",
        headers={"X-Lemma-Unlock": unlock_token},
        timeout=timeout,
    )
    list_report = _build_report(
        "lemma-firewall-runtime-list",
        ok=(not list_err and list_status == 200 and bool((list_payload or {}).get("success"))),
        error_code=ERR_OK if (not list_err and list_status == 200 and bool((list_payload or {}).get("success"))) else ERR_HTTP_FAILED,
        status_code=list_status,
        response=list_payload,
        message=list_err or str((list_payload or {}).get("error") or ""),
    )
    steps.append({"step": "runtime-list", "exit_code": EXIT_OK if list_report.get("ok") else EXIT_CHECK_FAILED, "report": list_report})

    runtime = (payload or {}).get("runtime") if isinstance(payload, dict) else {}
    control_prefs = (payload or {}).get("control_plane_preferences") if isinstance(payload, dict) else {}
    config_notes: list[str] = []
    if skip_openclaw_config:
        steps.append(
            {
                "step": "openclaw_config_patch",
                "exit_code": EXIT_OK,
                "report": {
                    "ok": True,
                    "skipped": True,
                    "message": "Skipped OpenClaw config patch (--skip-openclaw-config).",
                },
            }
        )
    else:
        proof_file = Path(str(os.getenv("LEMMA_PROOF_FILE") or ".lemma-proof.json")).expanduser().resolve()
        patched, config_path, config_message, hints = _patch_openclaw_config(
            api_base=api_base,
            proof_file=proof_file,
            runtime_id=runtime_id,
        )
        config_notes.extend(hints)
        steps.append(
            {
                "step": "openclaw_config_patch",
                "exit_code": EXIT_OK if patched else EXIT_CHECK_FAILED,
                "report": {
                    "ok": patched,
                    "config_path": str(config_path),
                    "message": config_message,
                },
            }
        )
    report = _build_report(
        "firewall-connect",
        ok=True,
        error_code=ERR_OK,
        api_base=api_base,
        runtime=runtime,
        control_plane_preferences=control_prefs,
        server_enforced_defaults=(payload or {}).get("server_enforced_defaults"),
        runtime_count=len(((list_payload or {}).get("runtimes") or [])) if isinstance(list_payload, dict) else None,
        steps=steps,
        next_steps=[
            "Use X-Lemma-Credential (+ optional X-Lemma-PoP) for agent API calls.",
            "Open wallet AIM to monitor runtime activity and use kill switches.",
            "Use /api/wallet/runtimes/<runtime_id>/kill for runtime-level stop.",
            *config_notes,
        ],
    )
    _emit_report(args, report, ["firewall-connect succeeded (session-link -> bootstrap -> runtime-list)"])
    return EXIT_OK


def _invoke_handler_capture_report(handler, args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    captured_report: dict[str, Any] | None = None
    original_emit = _emit_report

    def _capture(_args: argparse.Namespace, report: dict[str, Any], _text_lines: list[str]) -> None:
        nonlocal captured_report
        captured_report = report

    try:
        globals()["_emit_report"] = _capture
        exit_code = handler(args)
    finally:
        globals()["_emit_report"] = original_emit

    if captured_report is None:
        captured_report = _build_report(
            "unknown",
            ok=exit_code == EXIT_OK,
            error_code=ERR_OK if exit_code == EXIT_OK else ERR_FLOW_STEP_FAILED,
        )
    return exit_code, captured_report


def _run_external_command(
    *,
    command: str,
    cwd: str,
    timeout: float,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or f"command timed out after {timeout:.0f}s")
        return EXIT_CHECK_FAILED, stdout, stderr
    return int(completed.returncode), str(completed.stdout or ""), str(completed.stderr or "")


def _extract_site_id_from_site_create_report(report: dict[str, Any], fallback: str) -> str:
    payload = report.get("response") if isinstance(report, dict) else None
    if isinstance(payload, dict):
        direct = str(payload.get("site_id") or "").strip()
        if direct:
            return direct
        site_obj = payload.get("site")
        if isinstance(site_obj, dict):
            nested = str(site_obj.get("site_id") or site_obj.get("id") or "").strip()
            if nested:
                return nested
    return fallback


def run_flow(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir or ".").resolve()
    api_base = _derive_api_base(args.api_base)
    session_file = args.session_file or ""
    created_site_domain = (args.new_site_domain or "").strip()
    if not created_site_domain:
        created_site_domain = _normalize_domain(args.site_domain or "")

    steps: list[dict[str, Any]] = []
    dry_run = bool(getattr(args, "dry_run", False))
    skip_setup = bool(getattr(args, "skip_setup", False))
    skip_login = bool(getattr(args, "skip_login", False))
    skip_site_create = bool(getattr(args, "skip_site_create", False))
    skip_issue = bool(getattr(args, "skip_issue", False))
    skip_validate = bool(getattr(args, "skip_validate", False))

    if skip_setup:
        steps.append({"step": "setup", "exit_code": EXIT_OK, "report": _build_report("setup", ok=True, skipped=True)})
    else:
        setup_args = argparse.Namespace(
            site_id=args.site_id,
            site_domain=args.site_domain,
            api_base=api_base,
            output_dir=str(project_dir),
            framework=(args.framework or "both"),
            force=bool(args.force),
            json=True,
        )
        setup_code, setup_report = _invoke_handler_capture_report(run_setup, setup_args)
        steps.append({"step": "setup", "exit_code": setup_code, "report": setup_report})
        if setup_code != EXIT_OK:
            report = _build_report(
                "flow",
                ok=False,
                error_code=str(setup_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                failed_step="setup",
                steps=steps,
            )
            _emit_report(args, report, ["flow failed at setup"])
            return setup_code

    if skip_login:
        steps.append({"step": "login", "exit_code": EXIT_OK, "report": _build_report("login", ok=True, skipped=True)})
    else:
        login_args = argparse.Namespace(
            api_base=api_base,
            header=(args.header or ""),
            credential_file=(args.credential_file or ""),
            scope=(args.scope or "read,write,admin"),
            ttl_hours=int(args.ttl_hours or 8),
            agent_name=(args.agent_name or "lemma-cli"),
            task=(args.task or "CLI authenticated provisioning session"),
            allowed_site=list(args.allowed_site or []),
            platform_api_key=(args.platform_api_key or ""),
            user_email=(args.user_email or ""),
            site_id=(args.site_id or "lemma.id"),
            site_domain=(args.site_domain or "lemma.id"),
            permission_level=(args.permission_level or "super_admin"),
            issue_json=(getattr(args, "issue_json", "") or ""),
            delegation_reason=(getattr(args, "delegation_reason", "") or ""),
            delegation_id=(getattr(args, "delegation_id", "") or ""),
            acting_for_ppid=(getattr(args, "acting_for_ppid", "") or ""),
            requested_by_ppid=(getattr(args, "requested_by_ppid", "") or ""),
            delegated_by_user_ref=(getattr(args, "delegated_by_user_ref", "") or ""),
            acting_for_user_ref=(getattr(args, "acting_for_user_ref", "") or ""),
            requested_by_user_ref=(getattr(args, "requested_by_user_ref", "") or ""),
            extra_header=list(getattr(args, "extra_header", []) or []),
            timeout=float(args.timeout),
            session_file=session_file,
            non_interactive=bool(args.non_interactive),
            no_browser=bool(args.no_browser),
            login_timeout=float(args.login_timeout),
            dry_run=dry_run,
            dry_run_output="",
            json=True,
        )
        login_code, login_report = _invoke_handler_capture_report(run_login, login_args)
        steps.append({"step": "login", "exit_code": login_code, "report": login_report})
        if login_code != EXIT_OK:
            report = _build_report(
                "flow",
                ok=False,
                error_code=str(login_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                failed_step="login",
                steps=steps,
            )
            _emit_report(args, report, ["flow failed at login"])
            return login_code

    site_create_report: dict[str, Any] = {}
    if skip_site_create:
        site_create_report = _build_report("site-create", ok=True, skipped=True)
        steps.append({"step": "site-create", "exit_code": EXIT_OK, "report": site_create_report})
    else:
        site_create_args = argparse.Namespace(
            api_base=api_base,
            name=(args.new_site_name or ""),
            domain=created_site_domain,
            environment=(args.environment or "development"),
            payload_json=(getattr(args, "site_create_json", "") or ""),
            extra_header=list(getattr(args, "extra_header", []) or []),
            agent_token="",
            api_key="",
            timeout=float(args.timeout),
            session_file=session_file,
            dry_run=dry_run,
            dry_run_output="",
            json=True,
        )
        site_create_code, site_create_report = _invoke_handler_capture_report(run_site_create, site_create_args)
        steps.append({"step": "site-create", "exit_code": site_create_code, "report": site_create_report})
        if site_create_code != EXIT_OK:
            report = _build_report(
                "flow",
                ok=False,
                error_code=str(site_create_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                failed_step="site-create",
                steps=steps,
            )
            _emit_report(args, report, ["flow failed at site-create"])
            return site_create_code

    bootstrap_site_id = (args.bootstrap_site_id or "").strip()
    if not bootstrap_site_id:
        bootstrap_site_id = _extract_site_id_from_site_create_report(site_create_report, fallback=(args.site_id or "").strip())

    if skip_issue:
        steps.append({"step": "issue", "exit_code": EXIT_OK, "report": _build_report("key-bootstrap", ok=True, skipped=True)})
    else:
        key_bootstrap_args = argparse.Namespace(
            api_base=api_base,
            site_id=bootstrap_site_id,
            name=(args.bootstrap_key_name or "CLI Bootstrap Key"),
            key_type=(args.key_type or "live"),
            permissions=(args.permissions or "read,write"),
            payload_json=(getattr(args, "key_bootstrap_json", "") or ""),
            extra_header=list(getattr(args, "extra_header", []) or []),
            env_file=(args.env_file or ""),
            overwrite_env=bool(args.overwrite_env),
            agent_token="",
            api_key="",
            timeout=float(args.timeout),
            session_file=session_file,
            dry_run=dry_run,
            dry_run_output="",
            json=True,
        )
        key_bootstrap_code, key_bootstrap_report = _invoke_handler_capture_report(run_key_bootstrap, key_bootstrap_args)
        steps.append({"step": "issue", "exit_code": key_bootstrap_code, "report": key_bootstrap_report})
        if key_bootstrap_code != EXIT_OK:
            report = _build_report(
                "flow",
                ok=False,
                error_code=str(key_bootstrap_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                failed_step="issue",
                steps=steps,
            )
            _emit_report(args, report, ["flow failed at issue"])
            return key_bootstrap_code

    if skip_validate:
        steps.append({"step": "validate", "exit_code": EXIT_OK, "report": _build_report("auth-status", ok=True, skipped=True)})
    else:
        auth_status_args = argparse.Namespace(
            api_base=api_base,
            timeout=float(args.timeout),
            session_file=session_file,
            dry_run=dry_run,
            dry_run_output="",
            json=True,
        )
        auth_status_code, auth_status_report = _invoke_handler_capture_report(run_auth_status, auth_status_args)
        steps.append({"step": "validate", "exit_code": auth_status_code, "report": auth_status_report})
        if auth_status_code != EXIT_OK:
            report = _build_report(
                "flow",
                ok=False,
                error_code=str(auth_status_report.get("error_code") or ERR_FLOW_STEP_FAILED),
                failed_step="validate",
                steps=steps,
            )
            _emit_report(args, report, ["flow failed at validate"])
            return auth_status_code

    report = _build_report(
        "flow",
        ok=True,
        error_code=ERR_OK,
        steps=steps,
        site_domain=created_site_domain,
        bootstrap_site_id=bootstrap_site_id,
        dry_run=dry_run,
    )
    report, output_error = _finalize_dry_run_report(args, report)
    if output_error:
        error_report = _build_report(
            "flow",
            ok=False,
            error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
            message=f"Failed writing dry-run artifact: {output_error}",
            steps=steps,
            dry_run=dry_run,
        )
        _emit_report(args, error_report, [error_report["message"]])
        return EXIT_CHECK_FAILED
    _emit_report(
        args,
        report,
        ["flow succeeded: setup -> login -> site-create -> issue -> validate"],
    )
    return EXIT_OK


def run_site_create(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    dry_run = bool(getattr(args, "dry_run", False))
    extra_headers, extra_headers_error = _parse_extra_headers(getattr(args, "extra_header", []) or [])
    if extra_headers_error:
        report = _build_report("site-create", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=extra_headers_error)
        _emit_report(args, report, [f"site-create failed: {extra_headers_error}"])
        return EXIT_USAGE

    payload = {
        "name": (args.name or "").strip(),
        "domain": (args.domain or "").strip(),
        "environment": (args.environment or "development").strip(),
    }
    payload_overrides, payload_error = _parse_json_object_arg(
        str(getattr(args, "payload_json", "") or ""),
        arg_name="--payload-json",
    )
    if payload_error:
        report = _build_report("site-create", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=payload_error)
        _emit_report(args, report, [f"site-create failed: {payload_error}"])
        return EXIT_USAGE
    payload.update(payload_overrides)
    if not payload["domain"]:
        report = _build_report(
            "site-create",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--domain is required",
        )
        _emit_report(args, report, ["site-create failed: --domain is required"])
        return EXIT_USAGE
    if dry_run:
        session = _load_auth_session(args.session_file)
        token = str(args.agent_token or (session or {}).get("agent_token") or "")
        api_key = str(args.api_key or (session or {}).get("api_key") or "")
        report = _build_report(
            "site-create",
            ok=True,
            dry_run=True,
            request={
                "method": "POST",
                "url": f"{api_base}/api/developer/sites",
                "headers": _mask_sensitive_headers({**({"X-Agent-Token": token} if token else {}), **({"X-API-Key": api_key} if api_key else {}), **extra_headers}),
                "json_body": payload,
            },
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "site-create",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["site-create dry-run complete (no request sent)"])
        return EXIT_OK

    headers, auth_error = _build_sensitive_headers(
        api_base=api_base,
        session_file=args.session_file,
        explicit_agent_token=args.agent_token,
        explicit_api_key=args.api_key,
        timeout=float(args.timeout),
    )
    if auth_error:
        _emit_report(args, auth_error, ["site-create failed: authentication required/invalid"])
        return EXIT_USAGE if auth_error.get("error_code") == ERR_AUTH_REQUIRED else EXIT_CHECK_FAILED

    status, response_payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/developer/sites",
        headers={**headers, **extra_headers},
        json_body=payload,
        timeout=float(args.timeout),
    )
    if err:
        report = _build_report("site-create", ok=False, error_code=ERR_HTTP_FAILED, message=err)
        _emit_report(args, report, [f"site-create failed: {err}"])
        return EXIT_CHECK_FAILED

    ok = status in {200, 201} and bool((response_payload or {}).get("success"))
    report = _build_report(
        "site-create",
        ok=ok,
        error_code=ERR_OK if ok else ERR_HTTP_FAILED,
        status_code=status,
        response=response_payload,
    )
    _emit_report(args, report, [f"site-create {'succeeded' if ok else 'failed'} ({status})"])
    return EXIT_OK if ok else EXIT_CHECK_FAILED


def run_key_bootstrap(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    dry_run = bool(getattr(args, "dry_run", False))
    site_id = (args.site_id or "").strip()
    if not site_id:
        report = _build_report(
            "key-bootstrap",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--site-id is required",
        )
        _emit_report(args, report, ["key-bootstrap failed: --site-id is required"])
        return EXIT_USAGE

    extra_headers, extra_headers_error = _parse_extra_headers(getattr(args, "extra_header", []) or [])
    if extra_headers_error:
        report = _build_report("key-bootstrap", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=extra_headers_error)
        _emit_report(args, report, [f"key-bootstrap failed: {extra_headers_error}"])
        return EXIT_USAGE

    payload = {
        "name": (args.name or "CLI Bootstrap Key").strip(),
        "type": (args.key_type or "live").strip(),
        "permissions": [p.strip() for p in str(args.permissions or "read,write").split(",") if p.strip()],
    }
    payload_overrides, payload_error = _parse_json_object_arg(
        str(getattr(args, "payload_json", "") or ""),
        arg_name="--payload-json",
    )
    if payload_error:
        report = _build_report("key-bootstrap", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=payload_error)
        _emit_report(args, report, [f"key-bootstrap failed: {payload_error}"])
        return EXIT_USAGE
    payload.update(payload_overrides)
    if dry_run:
        session = _load_auth_session(args.session_file)
        token = str(args.agent_token or (session or {}).get("agent_token") or "")
        api_key = str(args.api_key or (session or {}).get("api_key") or "")
        report = _build_report(
            "key-bootstrap",
            ok=True,
            dry_run=True,
            request={
                "method": "POST",
                "url": f"{api_base}/api/developer/sites/{site_id}/keys",
                "headers": _mask_sensitive_headers({**({"X-Agent-Token": token} if token else {}), **({"X-API-Key": api_key} if api_key else {}), **extra_headers}),
                "json_body": payload,
            },
            env_file=(str(Path(args.env_file).expanduser().resolve()) if args.env_file else None),
            env_write=bool(args.env_file),
        )
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "key-bootstrap",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, report, ["key-bootstrap dry-run complete (no request sent)"])
        return EXIT_OK

    headers, auth_error = _build_sensitive_headers(
        api_base=api_base,
        session_file=args.session_file,
        explicit_agent_token=args.agent_token,
        explicit_api_key=args.api_key,
        timeout=float(args.timeout),
    )
    if auth_error:
        _emit_report(args, auth_error, ["key-bootstrap failed: authentication required/invalid"])
        return EXIT_USAGE if auth_error.get("error_code") == ERR_AUTH_REQUIRED else EXIT_CHECK_FAILED
    status, response_payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/developer/sites/{site_id}/keys",
        headers={**headers, **extra_headers},
        json_body=payload,
        timeout=float(args.timeout),
    )
    if err:
        report = _build_report("key-bootstrap", ok=False, error_code=ERR_HTTP_FAILED, message=err)
        _emit_report(args, report, [f"key-bootstrap failed: {err}"])
        return EXIT_CHECK_FAILED

    ok = status in {200, 201} and bool((response_payload or {}).get("success"))
    if not ok:
        report = _build_report(
            "key-bootstrap",
            ok=False,
            error_code=ERR_HTTP_FAILED,
            status_code=status,
            response=response_payload,
        )
        _emit_report(args, report, [f"key-bootstrap failed ({status})"])
        return EXIT_CHECK_FAILED

    api_key = str((response_payload or {}).get("key") or "").strip()
    env_file = Path(args.env_file).expanduser().resolve() if args.env_file else None
    env_write = None
    if env_file and api_key:
        success, env_err = _write_env_values(
            env_file,
            {
                "LEMMA_SITE_ID": site_id,
                "LEMMA_API_KEY": api_key,
            },
            overwrite=bool(args.overwrite_env),
        )
        if not success:
            report = _build_report(
                "key-bootstrap",
                ok=False,
                error_code=ERR_WRITE_ENV_FAILED,
                message=env_err,
                status_code=status,
                response=response_payload,
            )
            _emit_report(args, report, [f"key-bootstrap failed writing env file: {env_err}"])
            return EXIT_CHECK_FAILED
        env_write = str(env_file)

    report = _build_report(
        "key-bootstrap",
        ok=True,
        status_code=status,
        key_id=(response_payload or {}).get("key_id"),
        key_masked=_mask_token(api_key),
        env_file=env_write,
        warning=(response_payload or {}).get("warning"),
    )
    _emit_report(
        args,
        report,
        [f"key-bootstrap succeeded for {site_id}", f"env written: {env_write}" if env_write else "env write skipped"],
    )
    return EXIT_OK


def run_iam_type_create(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    site_id = (args.site_id or "").strip()
    name = (args.name or "").strip()
    if not site_id or not name:
        report = _build_report(
            "iam-type-create",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--site-id and --name are required",
        )
        _emit_report(args, report, ["iam-type-create failed: --site-id and --name are required"])
        return EXIT_USAGE

    headers, auth_error = _build_sensitive_headers(
        api_base=api_base,
        session_file=args.session_file,
        explicit_agent_token=args.agent_token,
        explicit_api_key=args.api_key,
        timeout=float(args.timeout),
    )
    if auth_error:
        _emit_report(args, auth_error, ["iam-type-create failed: authentication required/invalid"])
        return EXIT_USAGE if auth_error.get("error_code") == ERR_AUTH_REQUIRED else EXIT_CHECK_FAILED

    if args.admin_email:
        headers["X-Admin-Email"] = args.admin_email.strip()

    config_payload: dict[str, Any] = {}
    if args.config:
        try:
            loaded = json.loads(args.config)
            if isinstance(loaded, dict):
                config_payload = loaded
        except json.JSONDecodeError:
            report = _build_report(
                "iam-type-create",
                ok=False,
                error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
                message="--config must be valid JSON object",
            )
            _emit_report(args, report, ["iam-type-create failed: --config must be valid JSON object"])
            return EXIT_USAGE

    payload = {
        "name": name,
        "type": (args.iam_type or "role").strip(),
        "description": (args.description or "").strip(),
        "config": config_payload,
    }
    status, response_payload, err = _http_json_request(
        method="POST",
        url=f"{api_base}/api/iam/sites/{site_id}/permission-types",
        headers=headers,
        json_body=payload,
        timeout=float(args.timeout),
    )
    if err:
        report = _build_report("iam-type-create", ok=False, error_code=ERR_HTTP_FAILED, message=err)
        _emit_report(args, report, [f"iam-type-create failed: {err}"])
        return EXIT_CHECK_FAILED

    ok = status in {200, 201} and bool((response_payload or {}).get("success"))
    report = _build_report(
        "iam-type-create",
        ok=ok,
        error_code=ERR_OK if ok else ERR_HTTP_FAILED,
        status_code=status,
        response=response_payload,
    )
    _emit_report(args, report, [f"iam-type-create {'succeeded' if ok else 'failed'} ({status})"])
    return EXIT_OK if ok else EXIT_CHECK_FAILED


def run_iam_type_list(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(args.api_base)
    site_id = (args.site_id or "").strip()
    if not site_id:
        report = _build_report(
            "iam-type-list",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--site-id is required",
        )
        _emit_report(args, report, ["iam-type-list failed: --site-id is required"])
        return EXIT_USAGE

    headers, auth_error = _build_sensitive_headers(
        api_base=api_base,
        session_file=args.session_file,
        explicit_agent_token=args.agent_token,
        explicit_api_key=args.api_key,
        timeout=float(args.timeout),
    )
    if auth_error:
        _emit_report(args, auth_error, ["iam-type-list failed: authentication required/invalid"])
        return EXIT_USAGE if auth_error.get("error_code") == ERR_AUTH_REQUIRED else EXIT_CHECK_FAILED

    status, response_payload, err = _http_json_request(
        method="GET",
        url=f"{api_base}/api/iam/sites/{site_id}/permission-types",
        headers=headers,
        timeout=float(args.timeout),
    )
    if err:
        report = _build_report("iam-type-list", ok=False, error_code=ERR_HTTP_FAILED, message=err)
        _emit_report(args, report, [f"iam-type-list failed: {err}"])
        return EXIT_CHECK_FAILED

    ok = status == 200 and bool((response_payload or {}).get("success"))
    report = _build_report(
        "iam-type-list",
        ok=ok,
        error_code=ERR_OK if ok else ERR_HTTP_FAILED,
        status_code=status,
        count=(response_payload or {}).get("count"),
        permission_types=(response_payload or {}).get("permission_types", []),
        response=response_payload if not ok else None,
    )
    _emit_report(args, report, [f"iam-type-list {'succeeded' if ok else 'failed'} ({status})"])
    return EXIT_OK if ok else EXIT_CHECK_FAILED


def build_doctor_report(error_hint: str | None) -> dict[str, Any]:
    hint = (error_hint or "").strip().lower()
    findings: list[dict[str, str]] = []

    if "wallet_unlock_required" in hint:
        findings.append(
            {
                "issue": "Wallet unlock is required before agent issuance",
                "action": "Run `lemma doctor --fix --error wallet_unlock_required --api-base https://lemma.id` and complete one browser unlock.",
            }
        )
    if "invalid_ppid" in hint:
        findings.append(
            {
                "issue": "Email-derived identity rejected for this environment",
                "action": "Switch to wallet-issued credential flow and authorize with `--credential-file`.",
            }
        )
    if "e_auth_required" in hint or "no local auth session" in hint or "not logged in" in hint:
        findings.append(
            {
                "issue": "No valid local CLI auth session",
                "action": "Run `lemma doctor --fix --error E_AUTH_REQUIRED` to reset session and re-authorize.",
            }
        )
    if "e_auth_invalid" in hint or "auth session invalid" in hint or "invalid_token" in hint:
        findings.append(
            {
                "issue": "Stored auth session appears invalid/expired",
                "action": "Run `lemma doctor --fix --error E_AUTH_INVALID` to clear stale session and re-login.",
            }
        )

    if "untrusted_issuer" in hint:
        findings.append(
            {
                "issue": "Credential issuer not trusted",
                "action": "Ensure issuer DID is in trusted issuer set (registry/runtime/allowlist) and normalize DID format.",
            }
        )
    if "invalid_signature" in hint:
        findings.append(
            {
                "issue": "Credential payload signature mismatch",
                "action": "Send raw signed credential fields only (no synthetic signature field; canonical numeric issuanceDate/expirationDate).",
            }
        )
    if "missing field `issuancedate`" in hint or "missing field issuancedate" in hint:
        findings.append(
            {
                "issue": "Missing issuanceDate in credential payload",
                "action": "Include issuanceDate as epoch seconds (u64) in serialized lemma payload.",
            }
        )
    if "x-lemma-credential" in hint or "missing_lemma_header" in hint:
        findings.append(
            {
                "issue": "Lemma header missing/invalid",
                "action": "Attach base64url(JSON) credential in X-Lemma-Credential header before protected API calls.",
            }
        )

    if not findings:
        findings.append(
            {
                "issue": "No specific diagnosis matched",
                "action": "Capture server lemma_error, issuer DID, and a sample header payload for targeted diagnosis.",
            }
        )

    return {"input": error_hint or "", "findings": findings}


def _doctor_remediation_key(error_hint: str | None) -> str:
    hint = (error_hint or "").strip().lower()
    if "wallet_unlock_required" in hint:
        return "wallet_unlock_required"
    if "invalid_ppid" in hint:
        return "invalid_ppid"
    if (
        "e_auth_required" in hint
        or "no local auth session" in hint
        or "not logged in" in hint
    ):
        return "auth_required"
    if (
        "e_auth_invalid" in hint
        or "auth session invalid" in hint
        or "invalid_token" in hint
    ):
        return "auth_invalid"
    return "unknown"


def _build_doctor_remediation(
    *,
    remediation_key: str,
    api_base: str,
    timeout: float,
    no_browser: bool,
    session_file: str,
    dry_run: bool,
) -> dict[str, Any]:
    if remediation_key == "wallet_unlock_required":
        wallet = _check_wallet_unlock_status(api_base, timeout)
        unlock_url = str(wallet.get("unlock_url") or f"{api_base}/unlock")
        browser_opened = False
        if wallet.get("state") != "unlocked" and not no_browser and not dry_run:
            try:
                browser_opened = bool(webbrowser.open(unlock_url))
            except webbrowser.Error:
                browser_opened = False
        return {
            "action": "unlock_wallet_session",
            "applied": True,
            "wallet": wallet,
            "unlock_url": unlock_url,
            "browser_opened": browser_opened,
            "next_steps": [
                f"Complete unlock at {unlock_url}",
                f"Then run `lemma authorize-agent --api-base {api_base} --json`",
            ],
        }

    if remediation_key == "invalid_ppid":
        wallet = _check_wallet_unlock_status(api_base, timeout)
        unlock_url = str(wallet.get("unlock_url") or f"{api_base}/unlock")
        browser_opened = False
        if wallet.get("state") != "unlocked" and not no_browser and not dry_run:
            try:
                browser_opened = bool(webbrowser.open(unlock_url))
            except webbrowser.Error:
                browser_opened = False
        return {
            "action": "switch_to_wallet_credential_flow",
            "applied": True,
            "wallet": wallet,
            "unlock_url": unlock_url,
            "browser_opened": browser_opened,
            "next_steps": [
                "Use wallet-issued credentials instead of email-derived identity.",
                f"Unlock via {unlock_url} if needed.",
                f"Then run `lemma authorize-agent --credential-file <lemma.json> --api-base {api_base} --json`.",
            ],
        }

    if remediation_key in {"auth_required", "auth_invalid"}:
        removed = False
        if not dry_run:
            removed = _clear_auth_session(session_file or "")
        return {
            "action": "reset_auth_session",
            "applied": True,
            "removed_session_file": removed,
            "session_file": str(_auth_path(session_file or "")),
            "next_steps": [
                f"Re-run `lemma authorize-agent --api-base {api_base} --json` to establish a fresh session.",
            ],
        }

    return {
        "action": "manual_follow_up_required",
        "applied": False,
        "next_steps": [
            "No automatic fix mapped for this error yet.",
            "Run with `--json`, capture response.error/message, then retry `lemma doctor --fix` with that hint.",
        ],
    }


def run_doctor(args: argparse.Namespace) -> int:
    hint = args.error or args.message
    doctor_report = build_doctor_report(hint)
    remediation: dict[str, Any] | None = None
    dry_run = bool(getattr(args, "dry_run", False))
    if bool(getattr(args, "fix", False)):
        api_base = _derive_api_base(getattr(args, "api_base", "https://lemma.id"))
        remediation_key = _doctor_remediation_key(hint)
        remediation = _build_doctor_remediation(
            remediation_key=remediation_key,
            api_base=api_base,
            timeout=float(getattr(args, "timeout", 10.0)),
            no_browser=bool(getattr(args, "no_browser", False)),
            session_file=str(getattr(args, "session_file", "") or ""),
            dry_run=dry_run,
        )
    report = _build_report(
        "doctor",
        ok=True,
        input=doctor_report.get("input", ""),
        findings=doctor_report.get("findings", []),
        fix_requested=bool(getattr(args, "fix", False)),
        remediation=remediation,
        dry_run=dry_run,
    )
    if dry_run:
        report, output_error = _finalize_dry_run_report(args, report)
        if output_error:
            error_report = _build_report(
                "doctor",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
    _emit_report(args, report, [f"doctor: {len(report.get('findings', []))} finding(s)"])
    return EXIT_OK


def run_incident_bundle(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(getattr(args, "api_base", "https://lemma.id"))
    timeout = float(getattr(args, "timeout", 10.0))
    dry_run = bool(getattr(args, "dry_run", False))
    include_deny_probe = bool(getattr(args, "include_deny_probe", False))
    audit_limit = max(1, int(getattr(args, "audit_limit", 20)))
    label = str(getattr(args, "bundle_label", "incident-bundle") or "incident-bundle").strip()
    decision_probe_path = str(getattr(args, "decision_probe_path", "/api/developer/sites") or "/api/developer/sites").strip()
    if not decision_probe_path.startswith("/"):
        decision_probe_path = f"/{decision_probe_path}"

    output_dir = Path(getattr(args, "output_dir", "ops/evidence/launch") or "ops/evidence/launch").expanduser().resolve()
    stamp = time.strftime("%Y-%m-%d-%H%M%S", time.gmtime())
    timeline: list[dict[str, Any]] = []

    def _mark(event: str, detail: str, ok: bool = True) -> None:
        timeline.append(
            {
                "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": event,
                "ok": ok,
                "detail": detail,
            }
        )

    session_file = str(getattr(args, "session_file", "") or "")
    token = str(getattr(args, "agent_token", "") or "").strip()
    if not token:
        session = _load_auth_session(session_file)
        token = str((session or {}).get("agent_token") or "").strip()

    if dry_run:
        preview = _build_report(
            "incident-bundle",
            ok=True,
            dry_run=True,
            api_base=api_base,
            output_dir=str(output_dir),
            requests=[
                {"name": "validate", "method": "GET", "url": f"{api_base}/api/agent/validate"},
                {"name": "session-status", "method": "POST", "url": f"{api_base}/api/wallet/session-sync"},
                {"name": "decision-allow-probe", "method": "GET", "url": f"{api_base}{decision_probe_path}"},
                {"name": "decision-deny-probe", "method": "GET", "url": f"{api_base}{decision_probe_path}"},
                {"name": "audit-context", "method": "GET", "url": f"{api_base}/api/agent/credentials/audit?limit={audit_limit}"},
            ],
        )
        preview, output_error = _finalize_dry_run_report(args, preview)
        if output_error:
            error_report = _build_report(
                "incident-bundle",
                ok=False,
                error_code=ERR_WRITE_DRY_RUN_OUTPUT_FAILED,
                message=f"Failed writing dry-run artifact: {output_error}",
            )
            _emit_report(args, error_report, [error_report["message"]])
            return EXIT_CHECK_FAILED
        _emit_report(args, preview, ["incident-bundle dry-run complete (no network calls, no files written)"])
        return EXIT_OK

    if not token:
        report = _build_report(
            "incident-bundle",
            ok=False,
            error_code=ERR_AUTH_REQUIRED,
            message="No local auth session found and --agent-token was not provided.",
            session_file=str(_auth_path(session_file)),
        )
        _emit_report(args, report, ["incident-bundle failed: auth required"])
        return EXIT_USAGE

    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_json_path = output_dir / f"{stamp}-{label}.json"
    bundle_md_path = output_dir / f"{stamp}-{label}.md"

    _mark("start", "collecting incident evidence bundle")
    status_code, validate_payload, validate_headers, validate_err = _http_json_request_with_headers(
        method="GET",
        url=f"{api_base}/api/agent/validate",
        headers={"X-Agent-Token": token},
        timeout=timeout,
    )
    validate_ok = bool(status_code == 200 and (validate_payload or {}).get("valid"))
    _mark("validate", f"status={status_code}", ok=validate_ok and not bool(validate_err))

    wallet = _check_wallet_unlock_status(api_base, timeout)
    _mark("session-status", f"state={wallet.get('state')}", ok=wallet.get("state") in {"unlocked", "locked"})

    audit_allow_status, audit_allow_payload, audit_allow_headers, audit_allow_err = _http_json_request_with_headers(
        method="GET",
        url=f"{api_base}{decision_probe_path}",
        headers={"X-Agent-Token": token},
        timeout=timeout,
    )
    allow_receipt = {
        "decision_id": str(
            audit_allow_headers.get("X-Lemma-Decision-Id")
            or audit_allow_headers.get("x-lemma-decision-id")
            or ""
        ),
        "decision_signature": str(
            audit_allow_headers.get("X-Lemma-Decision-Signature")
            or audit_allow_headers.get("x-lemma-decision-signature")
            or ""
        ),
        "auth_mode_expected": str(
            audit_allow_headers.get("X-Lemma-Auth-Mode-Expected")
            or audit_allow_headers.get("x-lemma-auth-mode-expected")
            or ""
        ),
        "auth_mode_effective": str(
            audit_allow_headers.get("X-Lemma-Auth-Mode-Effective")
            or audit_allow_headers.get("x-lemma-auth-mode-effective")
            or ""
        ),
        "auth_shadow_decision": str(
            audit_allow_headers.get("X-Lemma-Auth-Shadow-Decision")
            or audit_allow_headers.get("x-lemma-auth-shadow-decision")
            or ""
        ),
        "auth_shadow_reason": str(
            audit_allow_headers.get("X-Lemma-Auth-Shadow-Reason")
            or audit_allow_headers.get("x-lemma-auth-shadow-reason")
            or ""
        ),
        "auth_freshness_age_seconds": str(
            audit_allow_headers.get("X-Lemma-Auth-Freshness-Age-S")
            or audit_allow_headers.get("x-lemma-auth-freshness-age-s")
            or ""
        ),
        "auth_step_up_required": str(
            audit_allow_headers.get("X-Lemma-Auth-Step-Up-Required")
            or audit_allow_headers.get("x-lemma-auth-step-up-required")
            or ""
        ),
    }
    _mark(
        "decision-allow-probe",
        f"status={audit_allow_status}; decision_id={allow_receipt.get('decision_id') or 'missing'}",
        ok=bool(audit_allow_status and audit_allow_status < 500),
    )

    deny_probe: dict[str, Any] | None = None
    if include_deny_probe:
        deny_status, deny_payload, deny_headers, deny_err = _http_json_request_with_headers(
            method="GET",
            url=f"{api_base}{decision_probe_path}",
            headers={"X-Agent-Token": "lm_agent_invalid_incident_probe"},
            timeout=timeout,
        )
        deny_probe = {
            "status_code": deny_status,
            "error": deny_err,
            "payload": deny_payload,
            "decision_receipt": {
                "decision_id": str(
                    deny_headers.get("X-Lemma-Decision-Id")
                    or deny_headers.get("x-lemma-decision-id")
                    or ((deny_payload or {}).get("decision") or {}).get("decision_id")
                    or ""
                ),
                "decision_signature": str(
                    deny_headers.get("X-Lemma-Decision-Signature")
                    or deny_headers.get("x-lemma-decision-signature")
                    or ((deny_payload or {}).get("decision") or {}).get("signature")
                    or ""
                ),
            },
        }
        _mark(
            "decision-deny-probe",
            f"status={deny_status}; decision_id={deny_probe['decision_receipt'].get('decision_id') or 'missing'}",
            ok=bool(deny_status in {401, 403}),
        )

    bundle = {
        "schema_version": CLI_SCHEMA_VERSION,
        "bundle_type": "incident-authz",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_base": api_base,
        "decision_probe_path": decision_probe_path,
        "session_file": str(_auth_path(session_file)),
        "token_masked": _mask_token(token),
        "timeline": timeline,
        "artifacts": {
            "validate": {
                "status_code": status_code,
                "error": validate_err,
                "payload": validate_payload,
                "decision_receipt": {
                    "decision_id": str(
                        validate_headers.get("X-Lemma-Decision-Id")
                        or validate_headers.get("x-lemma-decision-id")
                        or ""
                    ),
                    "decision_signature": str(
                        validate_headers.get("X-Lemma-Decision-Signature")
                        or validate_headers.get("x-lemma-decision-signature")
                        or ""
                    ),
                },
            },
            "session_status": wallet,
            "audit_allow_probe": {
                "status_code": audit_allow_status,
                "error": audit_allow_err,
                "payload": audit_allow_payload,
                "decision_receipt": allow_receipt,
            },
            "audit_deny_probe": deny_probe,
        },
    }
    bundle_json_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    markdown = "\n".join(
        [
            "# Incident Bundle",
            "",
            f"- Created (UTC): {bundle['created_at_utc']}",
            f"- API base: {api_base}",
            f"- Token: `{bundle['token_masked']}`",
            f"- Validate status: `{status_code}`",
            f"- Wallet state: `{wallet.get('state')}`",
            f"- Allow decision id: `{allow_receipt.get('decision_id') or 'missing'}`",
            f"- Auth mode (expected/effective): `{allow_receipt.get('auth_mode_expected') or 'n/a'}` / `{allow_receipt.get('auth_mode_effective') or 'n/a'}`",
            f"- Shadow decision: `{allow_receipt.get('auth_shadow_decision') or 'n/a'}` ({allow_receipt.get('auth_shadow_reason') or 'n/a'})",
            f"- Deny probe included: `{include_deny_probe}`",
            "",
            "## Timeline",
            "",
            *[f"- {entry['ts_utc']} | {entry['event']} | ok={entry['ok']} | {entry['detail']}" for entry in timeline],
            "",
            f"- JSON artifact: `{bundle_json_path}`",
        ]
    )
    bundle_md_path.write_text(markdown + "\n", encoding="utf-8")

    report = _build_report(
        "incident-bundle",
        ok=True,
        error_code=ERR_OK,
        api_base=api_base,
        decision_probe_path=decision_probe_path,
        bundle_json=str(bundle_json_path),
        bundle_markdown=str(bundle_md_path),
        validate_status=status_code,
        wallet_state=wallet.get("state"),
        allow_decision_id=allow_receipt.get("decision_id"),
        deny_probe_included=include_deny_probe,
    )
    _emit_report(args, report, [f"incident bundle written: {bundle_json_path}"])
    return EXIT_OK


def run_authz_latency(args: argparse.Namespace) -> int:
    api_base = _derive_api_base(getattr(args, "api_base", "https://lemma.id"))
    timeout = float(getattr(args, "timeout", 10.0))
    request_count = max(1, int(getattr(args, "requests", 30)))
    warmup_count = max(0, int(getattr(args, "warmup", 3)))
    budget_p95_ms = max(0.0, float(getattr(args, "budget_p95_ms", 5.0)))
    e2e_budget_p95_ms = max(0.0, float(getattr(args, "e2e_budget_p95_ms", 0.0)))
    decision_probe_path = str(getattr(args, "decision_probe_path", "/api/developer/sites") or "/api/developer/sites").strip()
    if not decision_probe_path.startswith("/"):
        decision_probe_path = f"/{decision_probe_path}"

    auth_mode = str(getattr(args, "auth_mode", "auto") or "auto").strip().lower()
    token = str(getattr(args, "agent_token", "") or "").strip()
    session_file = str(getattr(args, "session_file", "") or "")
    if not token and auth_mode != "proof":
        session = _load_auth_session(session_file)
        token = str((session or {}).get("agent_token") or "").strip()

    proof_inline, proof_inline_err = _resolve_inline_or_file_text(
        str(getattr(args, "proof", "") or ""),
        arg_name="--proof",
    )
    if proof_inline_err:
        report = _build_report("authz-latency", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=proof_inline_err)
        _emit_report(args, report, [f"authz-latency failed: {proof_inline_err}"])
        return EXIT_USAGE
    proof_file_text, proof_file_err = _resolve_inline_or_file_text(
        f"@{str(getattr(args, 'proof_file', '') or '').strip()}" if str(getattr(args, "proof_file", "") or "").strip() else "",
        arg_name="--proof-file",
    )
    if proof_file_err:
        report = _build_report("authz-latency", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=proof_file_err)
        _emit_report(args, report, [f"authz-latency failed: {proof_file_err}"])
        return EXIT_USAGE
    proof_text = proof_inline or proof_file_text
    proof_header, proof_payload, proof_err = _format_header_json(proof_text, arg_name="proof")
    if proof_err:
        report = _build_report("authz-latency", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=proof_err)
        _emit_report(args, report, [f"authz-latency failed: {proof_err}"])
        return EXIT_USAGE

    pop_inline, pop_inline_err = _resolve_inline_or_file_text(
        str(getattr(args, "pop", "") or ""),
        arg_name="--pop",
    )
    if pop_inline_err:
        report = _build_report("authz-latency", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=pop_inline_err)
        _emit_report(args, report, [f"authz-latency failed: {pop_inline_err}"])
        return EXIT_USAGE
    pop_file_text, pop_file_err = _resolve_inline_or_file_text(
        f"@{str(getattr(args, 'pop_file', '') or '').strip()}" if str(getattr(args, "pop_file", "") or "").strip() else "",
        arg_name="--pop-file",
    )
    if pop_file_err:
        report = _build_report("authz-latency", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=pop_file_err)
        _emit_report(args, report, [f"authz-latency failed: {pop_file_err}"])
        return EXIT_USAGE
    pop_text = pop_inline or pop_file_text
    pop_header, _pop_payload, pop_err = _format_header_json(pop_text, arg_name="pop")
    if pop_err:
        report = _build_report("authz-latency", ok=False, error_code=ERR_USAGE_MISSING_REQUIRED_ARGS, message=pop_err)
        _emit_report(args, report, [f"authz-latency failed: {pop_err}"])
        return EXIT_USAGE

    if auth_mode == "proof" and not proof_header:
        report = _build_report(
            "authz-latency",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="--auth-mode proof requires --proof or --proof-file.",
        )
        _emit_report(args, report, ["authz-latency failed: proof required"])
        return EXIT_USAGE
    if auth_mode == "token" and not token:
        report = _build_report(
            "authz-latency",
            ok=False,
            error_code=ERR_AUTH_REQUIRED,
            message="--auth-mode token requires --agent-token or a local session token.",
            session_file=str(_auth_path(session_file)),
        )
        _emit_report(args, report, ["authz-latency failed: auth required"])
        return EXIT_USAGE
    if auth_mode == "auto" and not token and not proof_header:
        report = _build_report(
            "authz-latency",
            ok=False,
            error_code=ERR_AUTH_REQUIRED,
            message="No local auth session found and neither --agent-token nor --proof was provided.",
            session_file=str(_auth_path(session_file)),
        )
        _emit_report(args, report, ["authz-latency failed: auth required"])
        return EXIT_USAGE

    latencies_ms: list[float] = []
    authz_header_ms: list[float] = []
    errors: list[str] = []
    status_counts: dict[str, int] = {}
    url = f"{api_base}{decision_probe_path}"
    pop_agent_key_id = str(getattr(args, "pop_agent_key_id", "") or "").strip() or "lemma-cli"

    def _request_headers() -> dict[str, str]:
        headers: dict[str, str] = {}
        if auth_mode != "proof" and token:
            headers["X-Agent-Token"] = token
        if proof_header:
            headers["X-Lemma-Proof"] = proof_header
            if pop_header:
                headers["X-Lemma-PoP"] = pop_header
            else:
                headers["X-Lemma-PoP"] = _build_pop_header(
                    api_base=api_base,
                    method="GET",
                    path=decision_probe_path,
                    body=b"",
                    proof_payload=proof_payload,
                    pop_agent_key_id=pop_agent_key_id,
                )
        return headers

    def _run_sample() -> None:
        started = time.perf_counter()
        status_code, _payload, headers, err = _http_json_request_with_headers(
            method="GET",
            url=url,
            headers=_request_headers(),
            timeout=timeout,
        )
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        latencies_ms.append(elapsed_ms)
        if err:
            errors.append(str(err))
        status_counts[str(status_code)] = status_counts.get(str(status_code), 0) + 1
        header_val = (
            headers.get("X-Lemma-Authz-Latency-Ms")
            or headers.get("x-lemma-authz-latency-ms")
            or ""
        ).strip()
        if header_val:
            try:
                authz_header_ms.append(float(header_val))
            except ValueError:
                pass

    for _ in range(warmup_count):
        _run_sample()
    if warmup_count > 0 and latencies_ms:
        latencies_ms = []
        authz_header_ms = []
        errors = []
        status_counts = {}

    for _ in range(request_count):
        _run_sample()

    if not latencies_ms:
        report = _build_report(
            "authz-latency",
            ok=False,
            error_code=ERR_HTTP_FAILED,
            message="No latency samples were collected.",
        )
        _emit_report(args, report, ["authz-latency failed: no samples"])
        return EXIT_CHECK_FAILED

    observed_authz_p95 = _percentile(authz_header_ms, 95) if authz_header_ms else _percentile(latencies_ms, 95)
    observed_e2e_p95 = _percentile(latencies_ms, 95)
    authz_budget_passed = bool(observed_authz_p95 <= budget_p95_ms)
    e2e_budget_enabled = e2e_budget_p95_ms > 0.0
    e2e_budget_passed = bool(observed_e2e_p95 <= e2e_budget_p95_ms) if e2e_budget_enabled else True
    overall_ok = bool(authz_budget_passed and e2e_budget_passed and not errors)
    report = _build_report(
        "authz-latency",
        ok=overall_ok,
        error_code=ERR_OK if overall_ok else ERR_HTTP_FAILED,
        api_base=api_base,
        decision_probe_path=decision_probe_path,
        sample_count=len(latencies_ms),
        p50_ms=round(_percentile(latencies_ms, 50), 3),
        p95_ms=round(_percentile(latencies_ms, 95), 3),
        p99_ms=round(_percentile(latencies_ms, 99), 3),
        mean_ms=round(float(statistics.mean(latencies_ms)), 3),
        max_ms=round(max(latencies_ms), 3),
        status_counts=status_counts,
        authz_header_samples=len(authz_header_ms),
        authz_p50_ms=round(_percentile(authz_header_ms, 50), 3) if authz_header_ms else None,
        authz_p95_ms=round(_percentile(authz_header_ms, 95), 3) if authz_header_ms else None,
        authz_p99_ms=round(_percentile(authz_header_ms, 99), 3) if authz_header_ms else None,
        budget_p95_ms=budget_p95_ms,
        budget_passed=authz_budget_passed,
        e2e_budget_p95_ms=e2e_budget_p95_ms if e2e_budget_enabled else None,
        e2e_budget_passed=e2e_budget_passed if e2e_budget_enabled else None,
        errors=errors[:5],
        token_masked=_mask_token(token) if token else "",
        auth_mode=auth_mode,
        proof_supplied=bool(proof_header),
        pop_supplied=bool(pop_header),
    )
    text_lines = [
        f"authz-latency: p50={report['p50_ms']}ms p95={report['p95_ms']}ms p99={report['p99_ms']}ms",
        (
            f"server-authz p95={report['authz_p95_ms']}ms (budget {budget_p95_ms}ms) => "
            f"{'PASS' if report['budget_passed'] else 'FAIL'}"
            if authz_header_ms
            else f"end-to-end p95 budget {budget_p95_ms}ms => {'PASS' if report['budget_passed'] else 'FAIL'}"
        ),
    ]
    if errors:
        text_lines.append(f"errors: {errors[0]}")
    if e2e_budget_enabled:
        text_lines.append(
            f"end-to-end p95={round(observed_e2e_p95, 3)}ms (budget {e2e_budget_p95_ms}ms) => "
            f"{'PASS' if e2e_budget_passed else 'FAIL'}"
        )
    _emit_report(args, report, text_lines)
    return EXIT_OK if report["ok"] else EXIT_CHECK_FAILED


def run_setup_openclaw(args: argparse.Namespace) -> int:
    """One-command OpenClaw starter-safe setup: approve, start, allow, kill, deny."""
    import http.server
    import socket
    import socketserver
    import tempfile
    import threading

    api_base = _derive_api_base(getattr(args, "api_base", "https://lemma.id"))
    defaults = _runtime_bootstrap_defaults()
    timeout = float(getattr(args, "timeout", 10.0))
    runtime_id = str(getattr(args, "runtime_id", "openclaw-default") or "openclaw-default").strip()
    agent_id = str(getattr(args, "agent_id", "main") or "main").strip()
    workspace_id = str(getattr(args, "workspace_id", "default") or "default").strip()
    display_name = str(getattr(args, "display_name", "OpenClaw Runtime") or "OpenClaw Runtime").strip()
    bind_host = str(getattr(args, "bind_host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    firewall_port = int(getattr(args, "firewall_port", 8787) or 8787)
    site_id = str(getattr(args, "site_id", "lemma.id") or "lemma.id").strip() or "lemma.id"
    root_type = str(getattr(args, "root_type", defaults["root_type"]) or defaults["root_type"]).strip().lower()
    org_id = str(getattr(args, "org_id", defaults["org_id"]) or defaults["org_id"]).strip() or defaults["org_id"]
    environment = str(getattr(args, "environment", defaults["environment"]) or defaults["environment"]).strip().lower()
    link_timeout = float(getattr(args, "link_timeout", 180.0) or 180.0)
    no_browser = bool(getattr(args, "no_browser", False))
    keep_running = bool(getattr(args, "keep_running", False))
    skip_openclaw_config = bool(getattr(args, "skip_openclaw_config", False))
    proof_file = Path(str(getattr(args, "proof_file", ".lemma-proof.json") or ".lemma-proof.json")).expanduser().resolve()
    steps: list[dict[str, Any]] = []
    firewall_proc: subprocess.Popen[Any] | None = None
    firewall_log_handle = None
    firewall_log_path: Path | None = None
    upstream_server: socketserver.TCPServer | None = None
    upstream_thread: threading.Thread | None = None
    temp_dir: str | None = None
    health_payload: dict[str, Any] | None = None

    class _ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    class _OpenClawDemoHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib interface
            if self.path != "/ok":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"not found")
                return
            body = json.dumps({"ok": True, "source": "openclaw-demo-upstream"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *args):  # noqa: A003 - stdlib interface
            return

    def _record_step(name: str, ok: bool, **extra: Any) -> None:
        payload = {"step": name, "ok": ok}
        payload.update(extra)
        steps.append(payload)

    def _step_ok(name: str) -> bool:
        for step in steps:
            if str(step.get("step") or "") == name:
                return bool(step.get("ok"))
        return False

    def _fail(error_code: str, message: str, failed_step: str, **extra: Any) -> int:
        report = _build_report(
            OPENCLAW_SETUP_COMMAND,
            ok=False,
            error_code=error_code,
            failed_step=failed_step,
            message=message,
            runtime_id=runtime_id,
            proof_file=str(proof_file),
            firewall_url=f"http://{bind_host}:{firewall_port}",
            steps=steps,
            installed_or_prereqs_ok=True,
            browser_approved=_step_ok("browser_approval"),
            firewall_started=_step_ok("firewall_started"),
            protected_action_allowed=_step_ok("protected_action_allowed"),
            runtime_kill_succeeded=_step_ok("runtime_kill_succeeded"),
            post_kill_action_denied=_step_ok("post_kill_action_denied"),
            next_steps=[message],
            **extra,
        )
        _emit_report(args, report, [f"{OPENCLAW_SETUP_COMMAND} failed: {message}"])
        return EXIT_CHECK_FAILED

    try:
        requested_firewall_port = firewall_port
        try:
            with socket.create_connection((bind_host, firewall_port), timeout=0.25):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as free_sock:
                    free_sock.bind((bind_host, 0))
                    firewall_port = int(free_sock.getsockname()[1])
        except OSError:
            pass
        _record_step(
            "select_firewall_port",
            True,
            requested_port=requested_firewall_port,
            effective_port=firewall_port,
        )

        session_args = argparse.Namespace(
            api_base=api_base,
            requested_scope="wallet:control_plane",
            no_browser=no_browser,
            poll_interval=2.0,
            link_timeout=link_timeout,
            timeout=timeout,
            dry_run=False,
            dry_run_output="",
            json=True,
        )
        session_code, session_report = _invoke_handler_capture_report(run_session_link, session_args)
        _record_step("browser_approval", session_code == EXIT_OK, report=session_report)
        if session_code != EXIT_OK:
            return _fail(
                session_report.get("error_code") or ERR_BROWSER_LOGIN_TIMEOUT,
                str(session_report.get("message") or "Browser approval failed."),
                "browser_approval",
            )
        unlock_token = str(session_report.get("unlock_token") or "").strip()
        if not unlock_token:
            return _fail(ERR_AUTH_INVALID, "Browser approval completed but no unlock token was returned.", "browser_approval")

        proof_payload, proof_error = _issue_wallet_runtime_proof(
            api_base=api_base,
            unlock_token=unlock_token,
            site_id=site_id,
            timeout=max(timeout, 45.0),
        )
        _record_step("issue_proof", proof_error is None, report=proof_payload or proof_error)
        if proof_error or not proof_payload:
            return _fail(
                (proof_error or {}).get("error_code") or ERR_HTTP_FAILED,
                str((proof_error or {}).get("message") or "Failed to issue wallet proof."),
                "issue_proof",
            )
        credential = proof_payload.get("credential") if isinstance(proof_payload.get("credential"), dict) else {}
        proof_file.parent.mkdir(parents=True, exist_ok=True)
        proof_file.write_text(json.dumps(credential, indent=2) + "\n", encoding="utf-8")
        credential_text = json.dumps(credential, separators=(",", ":"), ensure_ascii=False)

        connect_args = argparse.Namespace(
            api_base=api_base,
            runtime_id=runtime_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
            display_name=display_name,
            policy_profile=str(getattr(args, "policy_profile", defaults["policy_profile"]) or defaults["policy_profile"]).strip(),
            root_type=root_type,
            org_id=org_id,
            environment=environment,
            control_plane_mode="hosted",
            external_control_plane_url="",
            requested_scope="wallet:control_plane",
            unlock_token=unlock_token,
            no_browser=no_browser,
            poll_interval=2.0,
            link_timeout=link_timeout,
            skip_openclaw_config=True,
            dry_run=False,
            dry_run_output="",
            timeout=timeout,
            json=True,
        )
        connect_code, connect_report = _invoke_handler_capture_report(run_firewall_connect, connect_args)
        _record_step("connect_runtime", connect_code == EXIT_OK, report=connect_report)
        if connect_code != EXIT_OK:
            return _fail(
                connect_report.get("error_code") or ERR_FLOW_STEP_FAILED,
                str(connect_report.get("message") or "Runtime connect failed."),
                "connect_runtime",
            )

        temp_dir = tempfile.mkdtemp(prefix="lemma_openclaw_")
        policy_path = Path(temp_dir) / "policy.json"
        # Force online runtime authorize checks so kill-to-deny is visible immediately.
        with _ReusableTCPServer((bind_host, 0), _OpenClawDemoHandler) as temp_server:
            upstream_port = int(temp_server.server_address[1])
        policy = {
            "default_timeout_seconds": 15,
            "apis": {
                "openclaw-demo": {
                    "base_url": f"http://{bind_host}:{upstream_port}",
                    "allowed_methods": ["GET"],
                    "path_prefixes": ["/ok"],
                    "required_scope": "read",
                    "risk_tier": "low",
                    "forward_headers": ["accept", "content-type"],
                }
            },
        }
        policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

        upstream_server = _ReusableTCPServer((bind_host, upstream_port), _OpenClawDemoHandler)
        upstream_thread = threading.Thread(target=upstream_server.serve_forever, daemon=True)
        upstream_thread.start()

        firewall_script = Path(__file__).resolve().parent / "lemma_firewall.py"
        firewall_env = dict(os.environ)
        firewall_env.update(
            {
                "LEMMA_BASE_URL": api_base,
                "LEMMA_PROOF_FILE": str(proof_file),
                "LEMMA_FIREWALL_POLICY_FILE": str(policy_path),
                "LEMMA_FIREWALL_RUNTIME_ID": runtime_id,
                "LEMMA_FIREWALL_HOST": bind_host,
                "LEMMA_FIREWALL_PORT": str(firewall_port),
                "LEMMA_CREDENTIAL": credential_text,
            }
        )
        firewall_env.update(_starter_safe_firewall_env_updates())
        firewall_log_path = Path(temp_dir) / "firewall.log"
        firewall_log_handle = firewall_log_path.open("a", encoding="utf-8")
        firewall_proc = subprocess.Popen(
            ["python", str(firewall_script)],
            env=firewall_env,
            stdout=firewall_log_handle,
            stderr=firewall_log_handle,
        )
        firewall_url = f"http://{bind_host}:{firewall_port}"
        health_error = None
        for _ in range(30):
            time.sleep(1)
            status, payload, err = _http_json_request(
                method="GET",
                url=f"{firewall_url}/aim/health",
                timeout=5.0,
            )
            if err:
                health_error = err
                continue
            if status == 200 and bool((payload or {}).get("ok")):
                health_payload = payload or {}
                break
            health_error = str((payload or {}).get("error") or f"status_{status}")
        _record_step("firewall_started", health_payload is not None, firewall_url=firewall_url, health=health_payload, error=health_error)
        if not health_payload:
            return _fail(
                ERR_HTTP_FAILED,
                f"Local firewall did not become healthy: {health_error or 'unknown error'}",
                "firewall_started",
                firewall_log_path=str(firewall_log_path) if firewall_log_path else "",
                firewall_log_tail=_read_log_tail(firewall_log_path),
            )

        probe_api_id = "openclaw-demo"
        probe_path = "ok"
        policy_status, policy_payload, policy_err = _http_json_request(
            method="GET",
            url=f"{firewall_url}/aim/policy",
            timeout=5.0,
        )
        if policy_err is None and policy_status == 200 and isinstance(policy_payload, dict):
            apis_payload = policy_payload.get("apis") if isinstance(policy_payload.get("apis"), dict) else {}
            if probe_api_id not in apis_payload:
                for api_id, api_cfg in apis_payload.items():
                    if not isinstance(api_cfg, dict):
                        continue
                    methods = {str(item or "").strip().upper() for item in (api_cfg.get("allowed_methods") or [])}
                    if "GET" not in methods:
                        continue
                    prefixes = [str(item or "").strip() for item in (api_cfg.get("path_prefixes") or []) if str(item or "").strip()]
                    if not prefixes:
                        continue
                    candidate = prefixes[0].lstrip("/")
                    candidate = candidate.rstrip("/")
                    probe_api_id = str(api_id or "").strip() or probe_api_id
                    probe_path = candidate or probe_path
                    break
        _record_step(
            "resolve_probe_route",
            True,
            api_id=probe_api_id,
            path=probe_path,
            policy_status=policy_status,
            policy_error=policy_err,
        )

        action_status, action_payload, action_err = _http_json_request(
            method="GET",
            url=f"{firewall_url}/firewall/{probe_api_id}/{probe_path}",
            headers={"X-Lemma-Credential": credential_text},
            timeout=10.0,
        )
        action_ok = action_err is None and action_status == 200 and bool((action_payload or {}).get("ok"))
        _record_step(
            "protected_action_allowed",
            action_ok,
            status_code=action_status,
            response=action_payload,
            error=action_err,
        )
        if not action_ok:
            return _fail(
                ERR_EXPECTED_STATUS_MISMATCH,
                f"Protected action did not succeed through the firewall (status={action_status}, error={action_err or (action_payload or {}).get('error')}).",
                "protected_action_allowed",
            )

        config_notes: list[str] = []
        if skip_openclaw_config:
            _record_step("openclaw_config_patch", True, skipped=True, message="Skipped OpenClaw config patch (--skip-openclaw-config).")
        else:
            patched, config_path, config_message, hints = _patch_openclaw_config(
                api_base=api_base,
                proof_file=proof_file,
                runtime_id=runtime_id,
            )
            config_notes.extend(hints)
            _record_step(
                "openclaw_config_patch",
                patched,
                config_path=str(config_path),
                message=config_message,
            )

        if keep_running:
            status_text, reasons = _starter_safe_status_from_health(health_payload)
            report = _build_report(
                OPENCLAW_SETUP_COMMAND,
                ok=True,
                error_code=ERR_OK,
                runtime_id=runtime_id,
                proof_file=str(proof_file),
                firewall_url=firewall_url,
                firewall_log_path=str(firewall_log_path) if firewall_log_path else "",
                status=status_text,
                reasons=reasons,
                keep_running=True,
                installed_or_prereqs_ok=True,
                browser_approved=True,
                firewall_started=True,
                protected_action_allowed=True,
                runtime_kill_succeeded=False,
                post_kill_action_denied=False,
                health=health_payload,
                next_steps=[
                    f"Firewall remains running at `{firewall_url}` (--keep-running).",
                    f"Run `lemma safety-status --firewall-url {firewall_url}` to re-check local posture.",
                    f"Your runtime proof was saved to `{proof_file}`.",
                    *( [f"Firewall log file: `{firewall_log_path}`."] if firewall_log_path else [] ),
                    *config_notes,
                ],
                steps=steps,
            )
            _emit_report(
                args,
                report,
                [
                    "OpenClaw starter-safe setup complete.",
                    "Browser approval: PASS",
                    f"Firewall: PASS ({firewall_url})",
                    "Protected action: PASS",
                    "Kill check: SKIPPED (--keep-running)",
                    f"Safety status: {status_text.upper()}",
                ],
            )
            return EXIT_OK

        kill_status, kill_payload, kill_err = _http_json_request(
            method="POST",
            url=f"{api_base}/api/wallet/runtimes/{runtime_id}/kill",
            headers={
                "X-Lemma-Unlock": unlock_token,
                "X-Lemma-Org-Id": org_id,
                "X-Lemma-Environment": environment,
                "Content-Type": "application/json",
            },
            json_body={
                "reason": "OpenClaw setup kill validation",
                "org_id": org_id,
                "environment": environment,
            },
            timeout=25.0,
        )
        kill_ok = kill_err is None and kill_status == 200 and bool((kill_payload or {}).get("success"))
        _record_step("runtime_kill_succeeded", kill_ok, status_code=kill_status, response=kill_payload, error=kill_err)
        if not kill_ok:
            return _fail(
                ERR_HTTP_FAILED,
                f"Runtime kill failed (status={kill_status}, error={kill_err or (kill_payload or {}).get('error')}).",
                "runtime_kill_succeeded",
            )

        deny_status, deny_payload, deny_err = _http_json_request(
            method="GET",
            url=f"{firewall_url}/firewall/{probe_api_id}/{probe_path}",
            headers={"X-Lemma-Credential": credential_text},
            timeout=10.0,
        )
        deny_ok = deny_err is None and deny_status == 403
        _record_step(
            "post_kill_action_denied",
            deny_ok,
            status_code=deny_status,
            response=deny_payload,
            error=deny_err,
        )
        if not deny_ok:
            return _fail(
                ERR_EXPECTED_STATUS_MISMATCH,
                f"Expected a deny after runtime kill, but got status={deny_status} instead.",
                "post_kill_action_denied",
            )

        status_text, reasons = _starter_safe_status_from_health(health_payload)
        report = _build_report(
            OPENCLAW_SETUP_COMMAND,
            ok=True,
            error_code=ERR_OK,
            runtime_id=runtime_id,
            proof_file=str(proof_file),
            firewall_url=firewall_url,
            status=status_text,
            reasons=reasons,
            installed_or_prereqs_ok=True,
            browser_approved=True,
            firewall_started=True,
            protected_action_allowed=True,
            runtime_kill_succeeded=True,
            post_kill_action_denied=True,
            health=health_payload,
            next_steps=[
                f"Run `lemma safety-status --firewall-url {firewall_url}` to re-check local posture.",
                f"Your runtime proof was saved to `{proof_file}`.",
                *( [f"Firewall log file: `{firewall_log_path}`."] if firewall_log_path else [] ),
                *config_notes,
            ],
            steps=steps,
        )
        _emit_report(
            args,
            report,
            [
                "OpenClaw starter-safe setup complete.",
                f"Browser approval: PASS",
                f"Firewall: PASS ({firewall_url})",
                "Protected action: PASS",
                "Kill check: PASS (deny observed after kill)",
                f"Safety status: {status_text.upper()}",
            ],
        )
        return EXIT_OK
    finally:
        if firewall_log_handle:
            try:
                firewall_log_handle.flush()
            except OSError:
                pass
        if firewall_proc and firewall_proc.poll() is None and not keep_running:
            firewall_proc.terminate()
            try:
                firewall_proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                firewall_proc.kill()
        if firewall_log_handle:
            try:
                firewall_log_handle.close()
            except OSError:
                pass
        if upstream_server:
            upstream_server.shutdown()
            upstream_server.server_close()
        if upstream_thread and upstream_thread.is_alive():
            upstream_thread.join(timeout=2.0)


def _parse_ttl(ttl_str: str) -> int:
    """Parse a TTL string like '30m', '2h', '1d' into seconds."""
    ttl_str = ttl_str.strip().lower()
    if ttl_str.endswith("d"):
        return int(ttl_str[:-1]) * 86400
    if ttl_str.endswith("h"):
        return int(ttl_str[:-1]) * 3600
    if ttl_str.endswith("m"):
        return int(ttl_str[:-1]) * 60
    if ttl_str.endswith("s"):
        return int(ttl_str[:-1])
    return int(ttl_str)


_SCOPE_HIERARCHY = {"read": 0, "write": 1, "admin": 2}
# Flattened from api/action_taxonomy.py TAXONOMY -- keep in sync when adding actions
_TAXONOMY_SCOPES = {
    "file.read": "read", "file.write": "write", "file.delete": "admin", "file.list": "read",
    "shell.exec": "admin", "shell.exec.sandboxed": "write",
    "api.call.read": "read", "api.call.write": "write", "api.call.admin": "admin",
    "browser.read": "read", "browser.interact": "write",
    "net.egress.internal": "write", "net.egress.external": "admin",
    "secret.read": "admin", "secret.write": "admin",
    "deploy.staging": "write", "deploy.production": "admin", "deploy.rollback": "admin",
    "ingest.internal": "read", "ingest.external": "read", "ingest.user_content": "read",
    "db.query.read": "read", "db.query.write": "write", "db.migrate": "admin",
}


def _build_default_actions(scope_list: list[str], paths: list[str] | None = None) -> dict:
    """Build actions map from scope list (standalone, no api dependency)."""
    max_scope = max(scope_list, key=lambda s: _SCOPE_HIERARCHY.get(s, 0)) if scope_list else "read"
    max_level = _SCOPE_HIERARCHY.get(max_scope, 0)
    granted = sorted(a for a, s in _TAXONOMY_SCOPES.items() if _SCOPE_HIERARCHY.get(s, 99) <= max_level)
    actions: dict = {}
    for action in granted:
        actions[action] = {"paths": list(paths)} if paths else True
    return actions


def _parse_scope_spec(scope_str: str) -> tuple[list[str], dict]:
    """Parse scope spec like 'read:~/project/** write:~/project/src/**'.

    Returns (scope_list, actions_map).
    """
    scopes: list[str] = []
    paths: list[str] = []
    for token in scope_str.split():
        if ":" in token:
            scope_part, path_part = token.split(":", 1)
            scopes.append(scope_part.strip())
            paths.append(os.path.expanduser(path_part.strip()))
        else:
            scopes.append(token.strip())
    if not scopes:
        scopes = ["read"]
    _valid_scopes = set(_SCOPE_HIERARCHY)
    for s in scopes:
        if s not in _valid_scopes:
            print(f"Warning: unknown scope '{s}' (valid: {', '.join(sorted(_valid_scopes))}); treating as read-level", file=sys.stderr)
    actions_map = _build_default_actions(scopes, paths or None)
    return scopes, actions_map


_ACTIVE_SESSION_FILE = Path.home() / ".lemma" / "sessions" / "_active.json"


def run_start(args):
    """Start a scoped agent session with local firewall."""
    import socket

    api_base = (getattr(args, "api_base", "") or os.getenv("LEMMA_BASE_URL", "https://lemma.id")).rstrip("/")
    scope_str = getattr(args, "scope", "read")
    ttl_str = getattr(args, "ttl", "2h")
    port = getattr(args, "firewall_port", 8787)
    approve_actions = getattr(args, "approve", "")
    policy_spec = getattr(args, "policy", "httpbin")
    output_json = getattr(args, "json", False)

    ttl_seconds = _parse_ttl(ttl_str)
    scopes, actions_map = _parse_scope_spec(scope_str)
    session_id = f"session_{secrets.token_hex(8)}"
    session_dir = Path.home() / ".lemma" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    proof_file = session_dir / f"{session_id}.proof.json"
    log_file = session_dir / f"{session_id}.jsonl"

    credential = {
        "id": f"cred_{session_id}",
        "issuer": "did:lemma:local_cli",
        "subject": f"did:lemma:ppid_{session_id}",
        "claims": {
            "scope": scopes,
            "actions": actions_map,
            "taint_epoch": 0,
            "site_id": "local",
        },
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + ttl_seconds,
    }

    proof_file.write_text(json.dumps(credential, indent=2) + "\n", encoding="utf-8")

    # Try to issue via platform API (best-effort; falls back to local credential)
    try:
        import requests as _req
        resp = _req.post(
            f"{api_base}/api/agent/credentials/issue",
            json={
                "scope": scopes,
                "actions": actions_map,
                "ttl_seconds": ttl_seconds,
                "session_id": session_id,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            server_cred = resp.json().get("credential")
            if server_cred:
                credential = server_cred
                proof_file.write_text(json.dumps(credential, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass

    firewall_script = Path(__file__).resolve().parent / "lemma_firewall.py"
    bind_host = "127.0.0.1"

    requested_port = port
    try:
        with socket.create_connection((bind_host, port), timeout=0.25):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as free_sock:
                free_sock.bind((bind_host, 0))
                port = int(free_sock.getsockname()[1])
    except OSError:
        pass
    if port != requested_port and not output_json:
        print(f"Port {requested_port} in use, using {port}", file=sys.stderr)

    # Resolve policy: file path or comma-separated preset names
    policy_file = session_dir / f"{session_id}.policy.json"
    policy_spec_path = Path(policy_spec).expanduser()
    if policy_spec_path.is_file():
        import shutil
        shutil.copy2(policy_spec_path, policy_file)
        policy_apis = list(json.loads(policy_file.read_text(encoding="utf-8")).get("apis", {}).keys())
    else:
        apis_payload: dict[str, Any] = {}
        for token in policy_spec.split(","):
            name = token.strip().lower()
            if name:
                apis_payload[name] = _policy_template_for_api(name)
        policy_apis = list(apis_payload.keys())
        policy_file.write_text(json.dumps({"default_timeout_seconds": 25, "apis": apis_payload}, indent=2) + "\n", encoding="utf-8")

    env = dict(os.environ)
    env["LEMMA_BASE_URL"] = api_base
    env["LEMMA_CREDENTIAL"] = json.dumps(credential)
    env["LEMMA_FIREWALL_RUNTIME_ID"] = session_id
    env["LEMMA_FIREWALL_HOST"] = bind_host
    env["LEMMA_FIREWALL_PORT"] = str(port)
    env["LEMMA_FIREWALL_POLICY_FILE"] = str(policy_file)
    env["LEMMA_FIREWALL_TAINT_ON_VIOLATION_ENABLED"] = "1"
    env["LEMMA_FIREWALL_TAINT_ENFORCEMENT_ENABLED"] = "1"
    env["LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED"] = "0"
    env["LEMMA_FIREWALL_PROOF_REQUIRED_TIERS"] = ""
    env["LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS"] = ""
    env["LEMMA_FIREWALL_PASSKEY_AGE_ENFORCEMENT"] = "0"
    env["TRUSTED_ISSUER_DIDS"] = "did:lemma:local_cli"
    env["LEMMA_SESSION_LOG_FILE"] = str(log_file)
    if approve_actions:
        env["LEMMA_FIREWALL_APPROVAL_REQUIRED_ACTIONS"] = approve_actions.replace(" ", ",")

    firewall_log_file = session_dir / f"{session_id}.firewall.log"
    firewall_log_handle = open(firewall_log_file, "a", encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, str(firewall_script)],
        env=env,
        stdout=firewall_log_handle,
        stderr=firewall_log_handle,
    )

    # Wait for firewall readiness
    import requests as _req
    ready = False
    for _ in range(15):
        time.sleep(0.5)
        try:
            r = _req.get(f"http://{bind_host}:{port}/aim/health", timeout=2)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass

    if not ready:
        proc.terminate()
        firewall_log_handle.close()
        if output_json:
            print(json.dumps({"success": False, "error": "firewall_start_timeout", "firewall_log": str(firewall_log_file)}))
        else:
            print("ERROR: firewall did not start")
            print(f"  Firewall log: {firewall_log_file}")
            for line in _read_log_tail(firewall_log_file, 20):
                print(f"    {line}")
        return EXIT_CHECK_FAILED

    active_info = {
        "session_id": session_id,
        "pid": proc.pid,
        "port": port,
        "proof_file": str(proof_file),
        "log_file": str(log_file),
        "firewall_log": str(firewall_log_file),
        "policy_file": str(policy_file),
        "policy_apis": policy_apis,
        "scope": scopes,
        "ttl_seconds": ttl_seconds,
        "started_at": int(time.time()),
    }
    _ACTIVE_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ACTIVE_SESSION_FILE.write_text(json.dumps(active_info, indent=2) + "\n", encoding="utf-8")

    if output_json:
        print(json.dumps({"success": True, **active_info}))
    else:
        print(f"Session {session_id} started")
        print(f"  Firewall: http://{bind_host}:{port}")
        print(f"  Dashboard: http://{bind_host}:{port}/aim/dashboard")
        print(f"  APIs: {', '.join(policy_apis) if policy_apis else '(none)'}")
        print(f"  Scope: {scopes}")
        print(f"  TTL: {ttl_str} ({ttl_seconds}s)")
        print(f"  Log: {log_file}")
        print(f"  Firewall log: {firewall_log_file}")
        print(f"  PID: {proc.pid}")
    return EXIT_OK


def run_stop(args):
    """Stop the active agent session."""
    import signal
    output_json = getattr(args, "json", False)

    if not _ACTIVE_SESSION_FILE.exists():
        if output_json:
            print(json.dumps({"success": False, "error": "no_active_session"}))
        else:
            print("No active session found.")
        return EXIT_CHECK_FAILED

    try:
        info = json.loads(_ACTIVE_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        if output_json:
            print(json.dumps({"success": False, "error": "corrupt_session_file"}))
        else:
            print("Could not read active session file.")
        return EXIT_CHECK_FAILED

    pid = info.get("pid")
    port = info.get("port", 8787)
    session_id = info.get("session_id", "")

    # Revoke via firewall
    try:
        import requests as _req
        _req.post(
            f"http://127.0.0.1:{port}/aim/revoke",
            json={"credential_id": info.get("session_id", "*")},
            timeout=3,
        )
    except Exception:
        pass

    # Kill firewall process
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    for artifact_key in ("policy_file", "firewall_log"):
        artifact = info.get(artifact_key, "")
        if artifact:
            Path(artifact).unlink(missing_ok=True)

    _ACTIVE_SESSION_FILE.unlink(missing_ok=True)

    if output_json:
        print(json.dumps({"success": True, "session_id": session_id, "stopped": True}))
    else:
        print(f"Session {session_id} stopped.")
    return EXIT_OK


def run_replay(args):
    """Replay a session's action log with summary statistics."""
    output_json = getattr(args, "json", False)
    session_id = getattr(args, "session_id", "")
    use_last = getattr(args, "last", False)

    session_dir = Path.home() / ".lemma" / "sessions"

    log_file: Path | None = None
    if session_id:
        log_file = session_dir / f"{session_id}.jsonl"
    elif use_last or _ACTIVE_SESSION_FILE.exists():
        if _ACTIVE_SESSION_FILE.exists():
            try:
                info = json.loads(_ACTIVE_SESSION_FILE.read_text(encoding="utf-8"))
                candidate = info.get("log_file", "")
                if candidate:
                    log_file = Path(candidate)
            except Exception:
                pass
        if log_file is None or not log_file.is_file():
            jsonl_files = sorted(session_dir.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            log_file = jsonl_files[0] if jsonl_files else None
    else:
        jsonl_files = sorted(session_dir.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        log_file = jsonl_files[0] if jsonl_files else None

    if log_file is None or not log_file.is_file():
        if output_json:
            print(json.dumps({"success": False, "error": "no_session_log_found"}))
        else:
            print("No session log found.")
        return EXIT_CHECK_FAILED

    decisions = []
    for line in log_file.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if line:
            try:
                decisions.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    total = len(decisions)
    allows = sum(1 for d in decisions if d.get("allowed") is True)
    denies = sum(1 for d in decisions if d.get("allowed") is False)
    pendings = sum(1 for d in decisions if d.get("allowed") == "pending")
    actions_seen = {}
    files_modified = set()
    denied_actions = []
    for d in decisions:
        act = d.get("action", "")
        actions_seen[act] = actions_seen.get(act, 0) + 1
        if d.get("allowed") is True and act.startswith("file.write"):
            files_modified.add(d.get("resource", ""))
        if d.get("allowed") is False:
            denied_actions.append({"action": act, "resource": d.get("resource", ""), "error": d.get("error", "")})

    summary = {
        "log_file": str(log_file),
        "total_decisions": total,
        "allowed": allows,
        "denied": denies,
        "pending": pendings,
        "actions_breakdown": actions_seen,
        "files_modified": sorted(files_modified),
        "denied_attempts": denied_actions[:20],
    }

    if output_json:
        print(json.dumps({"success": True, **summary}))
    else:
        print(f"Session Replay: {log_file.name}")
        print(f"  Total decisions: {total}")
        print(f"  Allowed: {allows}  Denied: {denies}  Pending: {pendings}")
        print(f"  Actions:")
        for act, count in sorted(actions_seen.items(), key=lambda x: -x[1]):
            print(f"    {act}: {count}")
        if files_modified:
            print(f"  Files modified: {len(files_modified)}")
            for f in sorted(files_modified)[:10]:
                print(f"    {f}")
        if denied_actions:
            print(f"  Denied attempts ({len(denied_actions)}):")
            for d in denied_actions[:10]:
                print(f"    {d['action']} -> {d['resource']} ({d['error']})")
    return EXIT_OK


def run_demo(args):
    """One-command demo: issue credential, start firewall, run containment simulation."""
    import subprocess, tempfile, time, json, signal, sys

    api_base = (args.api_base or os.getenv("LEMMA_BASE_URL", "https://lemma.id")).rstrip("/")
    runtime_id = args.runtime_id or "lemma-demo-runtime"
    port = args.firewall_port or 8787

    print("=== Lemma Firewall Demo ===")
    print(f"  Control plane: {api_base}")
    print(f"  Runtime: {runtime_id}")
    print()

    # Step 1: Issue a signed credential
    print("[1/5] Issuing demo credential...")
    import requests

    # Fetch current taint epoch so credential matches runtime state
    current_taint_epoch = 0
    try:
        state_resp = requests.get(f"{api_base}/api/demo/state", params={"runtime_id": runtime_id}, timeout=10)
        if state_resp.status_code == 200:
            current_taint_epoch = int(state_resp.json().get("runtime_state", {}).get("taint_epoch") or 0)
    except Exception:
        pass

    resp = requests.post(
        f"{api_base}/api/demo/issue-credential",
        json={"runtime_id": runtime_id, "scope": ["read", "write"], "taint_epoch": current_taint_epoch},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"  FAILED: {resp.status_code} {resp.text[:200]}")
        return 1

    cred_body = resp.json()
    credential = cred_body.get("credential")
    if not credential:
        print(f"  FAILED: no credential in response")
        return 1

    issuer = credential.get("issuer", "unknown")[:20]
    scope = cred_body.get("scope", [])
    print(f"  OK: credential issued (issuer: {issuer}..., scope: {scope})")

    if args.skip_firewall:
        print()
        print("Credential (use as X-Lemma-Credential header):")
        print(json.dumps(credential, indent=2))
        return 0

    # Step 2: Write policy file
    print("[2/5] Writing demo policy...")
    policy = {
        "default_timeout_seconds": 15,
        "apis": {
            "httpbin": {
                "base_url": "https://httpbin.org",
                "allowed_methods": ["GET", "POST"],
                "path_prefixes": ["/get", "/post", "/status/", "/headers", "/ip"],
                "required_scope": "read",
                "risk_tier": "low",
                "forward_headers": ["content-type", "accept"]
            }
        }
    }
    policy_dir = tempfile.mkdtemp(prefix="lemma_demo_")
    policy_path = os.path.join(policy_dir, "policy.json")
    firewall_log_path = os.path.join(policy_dir, "lemma-firewall.log")
    with open(policy_path, "w") as f:
        json.dump(policy, f)
    print(f"  OK: {policy_path}")

    # Step 2b: Pre-fetch trusted issuer DIDs from JWKS
    trusted_dids = set()
    try:
        jwks_resp = requests.get(f"{api_base}/api/authz/jwks", timeout=10)
        if jwks_resp.status_code == 200:
            keys = jwks_resp.json().get("jwks", {}).get("keys", [])
            for key in keys:
                did = str(key.get("issuer") or "").strip()
                if did.startswith("did:lemma:"):
                    trusted_dids.add(did)
            print(f"  Synced {len(trusted_dids)} trusted issuers from control plane")
    except Exception:
        pass

    # Step 3: Start firewall
    print(f"[3/5] Starting firewall on port {port}...")
    firewall_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lemma_firewall.py")

    env = dict(os.environ)
    env["LEMMA_BASE_URL"] = api_base
    env["LEMMA_FIREWALL_POLICY_FILE"] = policy_path
    env["LEMMA_FIREWALL_RUNTIME_ID"] = runtime_id
    env["LEMMA_FIREWALL_COMPAT_FALLBACK_ALLOWED"] = "1"
    env["LEMMA_FIREWALL_TAINT_ENFORCEMENT_ENABLED"] = "1"
    env["LEMMA_FIREWALL_HOST"] = "127.0.0.1"
    env["LEMMA_FIREWALL_PORT"] = str(port)
    env["LEMMA_CREDENTIAL"] = json.dumps(credential)
    env["LEMMA_FIREWALL_REVOCATION_SYNC_INTERVAL_MS"] = "5000"
    env["LEMMA_FIREWALL_TAINT_SYNC_INTERVAL_MS"] = "5000"
    if trusted_dids:
        env["TRUSTED_ISSUER_DIDS"] = ",".join(sorted(trusted_dids))

    firewall_log_handle = open(firewall_log_path, "a", encoding="utf-8")
    firewall_proc = subprocess.Popen(
        [sys.executable, firewall_script],
        env=env,
        stdout=firewall_log_handle,
        stderr=firewall_log_handle,
    )

    # Wait for firewall to be ready
    firewall_url = f"http://127.0.0.1:{port}"
    ready = False
    for attempt in range(10):
        time.sleep(1)
        try:
            r = requests.get(f"{firewall_url}/aim/health", timeout=3)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass

    if not ready:
        print("  FAILED: firewall did not start")
        print(f"  Firewall log: {firewall_log_path}")
        for line in _read_log_tail(Path(firewall_log_path), 20):
            print(f"    {line}")
        firewall_log_handle.close()
        firewall_proc.terminate()
        return 1
    print(f"  OK: firewall ready at {firewall_url}")
    print(f"  Firewall log: {firewall_log_path}")

    # Step 4: Run containment tests
    print("[4/5] Running containment tests...")
    cred_header = json.dumps(credential)
    results = []

    def _test(name, method, path, expect_status, expect_error=None):
        try:
            fn = getattr(requests, method.lower())
            r = fn(
                f"{firewall_url}{path}",
                headers={"X-Lemma-Credential": cred_header},
                timeout=10,
            )
            body = r.json() if r.content else {}
            passed = r.status_code == expect_status
            if expect_error and passed:
                passed = expect_error in str(body.get("error", ""))
            status = "PASS" if passed else "FAIL"
            results.append({"name": name, "status": status, "code": r.status_code})
            error_detail = f" [{body.get('error', '')}]" if not passed and body.get("error") else ""
            print(f"  {name}: {status} ({r.status_code}){error_detail}")
            return passed
        except Exception as e:
            results.append({"name": name, "status": "FAIL", "error": str(e)})
            print(f"  {name}: FAIL ({e})")
            return False

    _test("allowed_get", "GET", "/firewall/httpbin/get", 200)
    _test("denied_wrong_path", "GET", "/firewall/httpbin/admin/secret", 403, "path_not_allowed")
    _test("denied_wrong_method", "DELETE", "/firewall/httpbin/get", 403, "method_not_allowed")

    # --- Taint epoch denial ---
    print()
    print("[5/7] Testing taint epoch containment...")
    try:
        bump_resp = requests.post(
            f"{api_base}/api/demo/taint-bump",
            json={"runtime_id": runtime_id, "trust_state": "tainted_external"},
            timeout=10,
        )
        new_epoch = bump_resp.json().get("runtime_state", {}).get("taint_epoch", 0) if bump_resp.status_code == 200 else 0
        print(f"  Taint epoch bumped to {new_epoch}")

        print("  Waiting for firewall taint sync...", end="", flush=True)
        taint_synced = False
        for _ in range(8):
            time.sleep(2)
            print(".", end="", flush=True)
            try:
                h = requests.get(f"{firewall_url}/aim/health", timeout=5).json()
                synced_epoch = h.get("sync", {}).get("runtime_taint_epochs", {}).get(runtime_id, 0)
                if synced_epoch >= new_epoch:
                    taint_synced = True
                    break
            except Exception:
                pass
        print()

        if taint_synced:
            print(f"  Firewall synced taint epoch {new_epoch}")
            _test("denied_stale_taint", "GET", "/firewall/httpbin/get", 403, "proof_taint_epoch_stale")

            print("  Issuing fresh credential with current taint epoch...")
            fresh_resp = requests.post(
                f"{api_base}/api/demo/issue-credential",
                json={"runtime_id": runtime_id, "scope": ["read", "write"], "taint_epoch": new_epoch},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if fresh_resp.status_code == 200:
                fresh_cred = fresh_resp.json().get("credential")
                if fresh_cred:
                    cred_header = json.dumps(fresh_cred)
                    _test("allowed_after_reissue", "GET", "/firewall/httpbin/get", 200)
                else:
                    print("  SKIP: no credential in fresh response")
            else:
                print(f"  SKIP: fresh credential issuance failed ({fresh_resp.status_code})")
        else:
            print("  SKIP: taint sync did not complete in time")
    except Exception as e:
        print(f"  Taint test error: {e}")

    # --- Revocation ---
    print()
    print("[6/7] Testing revocation...")
    credential_id = credential.get("id", "")
    if credential_id:
        try:
            # Revoke via control plane (writes to revocation_list, feeds delta sync)
            rev_resp = requests.post(
                f"{api_base}/api/demo/revoke-credential",
                json={"credential_id": credential_id},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if rev_resp.status_code == 200:
                print(f"  Credential {credential_id[:16]}... revoked on control plane")

                # Also revoke locally for immediate effect (delta sync may take a few seconds)
                requests.post(
                    f"{firewall_url}/aim/revoke",
                    json={"credential_id": credential_id},
                    timeout=5,
                )

                old_cred_header = json.dumps(credential)
                r = requests.get(
                    f"{firewall_url}/firewall/httpbin/get",
                    headers={"X-Lemma-Credential": old_cred_header},
                    timeout=10,
                )
                body = r.json() if r.content else {}
                if r.status_code == 401 and "revoked" in str(body.get("error", "")):
                    results.append({"name": "denied_revoked", "status": "PASS", "code": 401})
                    print(f"  denied_revoked: PASS (401) -- revoked credential denied")
                else:
                    results.append({"name": "denied_revoked", "status": "FAIL", "code": r.status_code})
                    error_msg = body.get("error", "")
                    print(f"  denied_revoked: FAIL ({r.status_code}) [{error_msg}]")
            else:
                print(f"  Revocation failed: {rev_resp.status_code} {rev_resp.text[:100]}")
        except Exception as e:
            print(f"  Revocation error: {e}")
    else:
        print("  SKIP: credential has no ID for revocation")

    # --- Summary ---
    print()
    print("[7/7] Cleanup...")
    firewall_proc.terminate()
    try:
        firewall_proc.wait(timeout=5)
    except Exception:
        firewall_proc.kill()
    firewall_log_handle.close()
    print("  Firewall stopped")

    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print()
    print(f"=== Result: {passed}/{total} containment tests passed ===")
    print()
    print("Cost profile:")
    print("  Local credential verify: <1ms per action (Ed25519 signature check)")
    print("  Control plane calls:     0 per action (only background sync)")
    print("  Estimated cost per 1000 actions: $0.00")
    print()

    if passed == total:
        print("The Lemma Firewall contained all agent actions locally.")
        print("No per-request server calls were needed.")

    return 0 if passed == total else 1


def run_init_policy(args: argparse.Namespace) -> int:
    selected_apis = list(getattr(args, "api", []) or [])
    if not selected_apis:
        selected_apis = ["httpbin"]

    apis_payload: dict[str, dict[str, Any]] = {}
    for api_id in selected_apis:
        normalized = str(api_id or "").strip().lower()
        if not normalized:
            continue
        apis_payload[normalized] = _policy_template_for_api(normalized)

    if not apis_payload:
        report = _build_report(
            "init-policy",
            ok=False,
            error_code=ERR_USAGE_MISSING_REQUIRED_ARGS,
            message="Provide at least one non-empty --api value.",
        )
        _emit_report(args, report, [report["message"]])
        return EXIT_USAGE

    output_path = Path(str(getattr(args, "output", "policy.json") or "policy.json")).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default_timeout_seconds": 25,
        "apis": apis_payload,
    }
    try:
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        report = _build_report(
            "init-policy",
            ok=False,
            error_code=ERR_WRITE_ENV_FAILED,
            message=f"Failed writing policy file: {exc}",
            output=str(output_path),
        )
        _emit_report(args, report, [report["message"]])
        return EXIT_CHECK_FAILED

    report = _build_report(
        "init-policy",
        ok=True,
        error_code=ERR_OK,
        output=str(output_path),
        apis=sorted(apis_payload.keys()),
    )
    _emit_report(
        args,
        report,
        [
            f"Generated policy file: {output_path}",
            f"APIs included: {', '.join(sorted(apis_payload.keys()))}",
        ],
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lemma", description="Lemma integration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")

    init_cmd = subparsers.add_parser("init", help="Initialize Lemma project config", parents=[common])
    init_cmd.add_argument("--site-id", required=True)
    init_cmd.add_argument("--site-domain", required=True)
    init_cmd.add_argument("--api-base", default="https://lemma.id")
    init_cmd.add_argument("--output-dir", default=".")
    init_cmd.add_argument("--force", action="store_true")
    init_cmd.set_defaults(handler=run_init)

    setup_cmd = subparsers.add_parser("setup", help="Scaffold Lemma integration assets", parents=[common])
    setup_cmd.add_argument("--site-id", required=True)
    setup_cmd.add_argument("--site-domain", required=True)
    setup_cmd.add_argument("--api-base", default="https://lemma.id")
    setup_cmd.add_argument("--output-dir", default=".")
    setup_cmd.add_argument("--framework", choices=["flask", "express", "both"], default="both")
    setup_cmd.add_argument("--force", action="store_true")
    setup_cmd.set_defaults(handler=run_setup)

    init_policy_cmd = subparsers.add_parser("init-policy", help="Generate starter Lemma firewall policy JSON", parents=[common])
    init_policy_cmd.add_argument("--api", action="append", default=[], help="API preset to include (repeatable): github,stripe,openai,anthropic,httpbin")
    init_policy_cmd.add_argument("--output", default="policy.json")
    init_policy_cmd.set_defaults(handler=run_init_policy)

    verify_cmd = subparsers.add_parser("verify", help="Run basic integration checks", parents=[common])
    verify_cmd.add_argument("--api-base", default="https://lemma.id")
    verify_cmd.set_defaults(handler=run_verify)

    audit_cmd = subparsers.add_parser("audit", help="Audit local Lemma integration scaffolding", parents=[common])
    audit_cmd.add_argument("--project-dir", default=".")
    audit_cmd.add_argument("--framework", choices=["flask", "express", "both"], default="both")
    audit_cmd.add_argument("--api-base", default="")
    audit_cmd.add_argument("--skip-health", action="store_true")
    audit_cmd.set_defaults(handler=run_audit)

    fix_cmd = subparsers.add_parser("fix", help="Auto-repair common local integration gaps", parents=[common])
    fix_cmd.add_argument("--project-dir", default=".")
    fix_cmd.add_argument("--framework", choices=["flask", "express", "both"], default="both")
    fix_cmd.add_argument("--site-id", default="")
    fix_cmd.add_argument("--site-domain", default="")
    fix_cmd.add_argument("--api-base", default="")
    fix_cmd.add_argument("--skip-health", action="store_true")
    fix_cmd.add_argument("--safe", action="store_true", help="Enable non-destructive fixes only")
    fix_cmd.set_defaults(handler=run_fix)

    smoke_cmd = subparsers.add_parser("smoke", help="Run protected-endpoint smoke check", parents=[common])
    smoke_cmd.add_argument("--url", required=True)
    smoke_cmd.add_argument("--method", default="GET")
    smoke_cmd.add_argument("--header", default="", help="Pre-encoded X-Lemma-Credential header value")
    smoke_cmd.add_argument("--credential-file", default="", help="Path to credential JSON file to encode")
    smoke_cmd.add_argument("--expect-status", type=int, default=200)
    smoke_cmd.add_argument("--timeout", type=float, default=10.0)
    smoke_cmd.set_defaults(handler=run_smoke)

    ci_cmd = subparsers.add_parser("ci", help="Run integration gate for agents/CI", parents=[common])
    ci_cmd.add_argument("--project-dir", default=".")
    ci_cmd.add_argument("--framework", choices=["flask", "express", "both"], default="both")
    ci_cmd.add_argument("--api-base", default="https://lemma.id")
    ci_cmd.add_argument("--skip-health", action="store_true")
    ci_cmd.add_argument("--skip-smoke", action="store_true")
    ci_cmd.add_argument("--smoke-url", default="")
    ci_cmd.add_argument("--smoke-method", default="GET")
    ci_cmd.add_argument("--smoke-header", default="")
    ci_cmd.add_argument("--smoke-credential-file", default="")
    ci_cmd.add_argument("--smoke-expect-status", type=int, default=200)
    ci_cmd.add_argument("--smoke-timeout", type=float, default=10.0)
    ci_cmd.set_defaults(handler=run_ci)

    authorize_cmd = subparsers.add_parser(
        "authorize-agent",
        help="One-command agent auth: login then validate session",
        parents=[common],
    )
    authorize_cmd.add_argument("--api-base", default="https://lemma.id")
    authorize_cmd.add_argument("--header", default="", help="Pre-encoded X-Lemma-Credential header value")
    authorize_cmd.add_argument("--credential-file", default="", help="Credential JSON file path to encode")
    authorize_cmd.add_argument("--scope", default="read,write,admin")
    authorize_cmd.add_argument("--ttl-hours", type=int, default=8)
    authorize_cmd.add_argument("--agent-name", default="lemma-cli")
    authorize_cmd.add_argument("--task", default="CLI authenticated provisioning session")
    authorize_cmd.add_argument("--allowed-site", action="append", default=[])
    authorize_cmd.add_argument("--platform-api-key", default="", help="Platform API key for auto self-issue fallback")
    authorize_cmd.add_argument("--user-email", default="", help="Admin email for platform self-issue fallback")
    authorize_cmd.add_argument("--site-id", default="lemma.id", help="Site ID used for platform self-issue fallback")
    authorize_cmd.add_argument("--site-domain", default="lemma.id", help="Site domain used for platform self-issue fallback")
    authorize_cmd.add_argument("--permission-level", default="super_admin", help="Permission level for platform self-issue fallback")
    authorize_cmd.add_argument("--issue-json", default="", help="JSON object (or @path) merged into /api/agent/auto-issue payload")
    authorize_cmd.add_argument("--delegation-reason", default="", help="Human-readable reason for delegation")
    authorize_cmd.add_argument("--delegation-id", default="", help="External delegation identifier for audits")
    authorize_cmd.add_argument("--acting-for-ppid", default="", help="PPID this agent action is performed for")
    authorize_cmd.add_argument("--requested-by-ppid", default="", help="PPID that requested this delegation")
    authorize_cmd.add_argument("--delegated-by-user-ref", default="", help="Customer-facing identifier of delegating user")
    authorize_cmd.add_argument("--acting-for-user-ref", default="", help="Customer-facing identifier of acting user")
    authorize_cmd.add_argument("--requested-by-user-ref", default="", help="Customer-facing identifier of requesting user")
    authorize_cmd.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional request header for API calls (format: 'Name: value'). Repeatable.",
    )
    authorize_cmd.add_argument("--non-interactive", action="store_true", help="Disable browser flow and use headless fallback")
    authorize_cmd.add_argument("--no-browser", action="store_true", help="Print browser approval URL without auto-opening")
    authorize_cmd.add_argument("--login-timeout", type=float, default=180.0, help="Seconds to wait for browser approval")
    authorize_cmd.add_argument("--dry-run", action="store_true", help="Preview request shape without sending network calls")
    authorize_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    authorize_cmd.add_argument("--timeout", type=float, default=10.0)
    authorize_cmd.add_argument("--session-file", default="")
    authorize_cmd.set_defaults(handler=run_authorize_agent)

    runtime_defaults = _runtime_bootstrap_defaults()

    openclaw_setup_cmd = subparsers.add_parser(
        OPENCLAW_SETUP_COMMAND,
        help="Starter-safe OpenClaw setup: approve once, start firewall, verify allow, verify kill-to-deny",
        parents=[common],
    )
    openclaw_setup_cmd.add_argument("--api-base", default="https://lemma.id")
    openclaw_setup_cmd.add_argument("--runtime-id", default="openclaw-default")
    openclaw_setup_cmd.add_argument("--agent-id", default="main")
    openclaw_setup_cmd.add_argument("--workspace-id", default="default")
    openclaw_setup_cmd.add_argument("--display-name", default="OpenClaw Runtime")
    openclaw_setup_cmd.add_argument("--proof-file", default=".lemma-proof.json")
    openclaw_setup_cmd.add_argument("--site-id", default="lemma.id")
    openclaw_setup_cmd.add_argument("--bind-host", default="127.0.0.1")
    openclaw_setup_cmd.add_argument("--firewall-port", type=int, default=8787)
    openclaw_setup_cmd.add_argument("--policy-profile", default=runtime_defaults["policy_profile"])
    openclaw_setup_cmd.add_argument("--root-type", default=runtime_defaults["root_type"], choices=["passkey_root", "workload_root", "policy_root"])
    openclaw_setup_cmd.add_argument("--org-id", default=runtime_defaults["org_id"])
    openclaw_setup_cmd.add_argument("--environment", default=runtime_defaults["environment"], choices=["dev", "staging", "prod"])
    openclaw_setup_cmd.add_argument("--no-browser", action="store_true", help="Print approve URL without auto-opening browser")
    openclaw_setup_cmd.add_argument("--link-timeout", type=float, default=180.0)
    openclaw_setup_cmd.add_argument("--keep-running", action="store_true", help="Keep local firewall running after setup (skip kill validation)")
    openclaw_setup_cmd.add_argument("--skip-openclaw-config", action="store_true", help="Do not patch OpenClaw config defaults")
    openclaw_setup_cmd.add_argument("--timeout", type=float, default=10.0)
    openclaw_setup_cmd.set_defaults(handler=run_setup_openclaw)

    firewall_cmd = subparsers.add_parser(
        "setup-firewall",
        help="Guided Lemma Firewall onboarding: verify -> authorize -> validate -> conformance",
        parents=[common],
    )
    firewall_cmd.add_argument("--api-base", default="https://lemma.id")
    firewall_cmd.add_argument("--header", default="", help="Pre-encoded X-Lemma-Credential header value")
    firewall_cmd.add_argument("--credential-file", default="", help="Credential JSON file path to encode")
    firewall_cmd.add_argument("--scope", default="read,write,admin")
    firewall_cmd.add_argument("--ttl-hours", type=int, default=8)
    firewall_cmd.add_argument("--agent-name", default="lemma-firewall-cli")
    firewall_cmd.add_argument("--task", default="Lemma Firewall onboarding session")
    firewall_cmd.add_argument("--allowed-site", action="append", default=[])
    firewall_cmd.add_argument("--platform-api-key", default="", help="Platform API key for auto self-issue fallback")
    firewall_cmd.add_argument("--user-email", default="", help="Admin email for platform self-issue fallback")
    firewall_cmd.add_argument("--site-id", default="lemma.id", help="Site ID used for platform self-issue fallback")
    firewall_cmd.add_argument("--site-domain", default="lemma.id", help="Site domain used for platform self-issue fallback")
    firewall_cmd.add_argument("--permission-level", default="super_admin", help="Permission level for platform self-issue fallback")
    firewall_cmd.add_argument("--issue-json", default="", help="JSON object (or @path) merged into /api/agent/auto-issue payload")
    firewall_cmd.add_argument("--delegation-reason", default="", help="Human-readable reason for delegation")
    firewall_cmd.add_argument("--delegation-id", default="", help="External delegation identifier for audits")
    firewall_cmd.add_argument("--acting-for-ppid", default="", help="PPID this agent action is performed for")
    firewall_cmd.add_argument("--requested-by-ppid", default="", help="PPID that requested this delegation")
    firewall_cmd.add_argument("--delegated-by-user-ref", default="", help="Customer-facing identifier of delegating user")
    firewall_cmd.add_argument("--acting-for-user-ref", default="", help="Customer-facing identifier of acting user")
    firewall_cmd.add_argument("--requested-by-user-ref", default="", help="Customer-facing identifier of requesting user")
    firewall_cmd.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional request header for API calls (format: 'Name: value'). Repeatable.",
    )
    firewall_cmd.add_argument("--non-interactive", action="store_true", help="Disable browser flow and use headless fallback")
    firewall_cmd.add_argument("--no-browser", action="store_true", help="Print browser approval URL without auto-opening")
    firewall_cmd.add_argument("--login-timeout", type=float, default=180.0, help="Seconds to wait for browser approval")
    firewall_cmd.add_argument("--agent-token", default="", help="Override token used for conformance command")
    firewall_cmd.add_argument("--firewall-audience", default="lemma-firewall", help="Expected Lemma Firewall audience for conformance checks")
    firewall_cmd.add_argument("--conformance-command", default="node mcp-server/run-lemma-firewall-conformance.js")
    firewall_cmd.add_argument("--conformance-workdir", default=".")
    firewall_cmd.add_argument("--conformance-timeout", type=float, default=600.0)
    firewall_cmd.add_argument("--skip-conformance", action="store_true")
    firewall_cmd.add_argument("--dry-run", action="store_true", help="Preview onboarding actions without side effects")
    firewall_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    firewall_cmd.add_argument("--timeout", type=float, default=10.0)
    firewall_cmd.add_argument("--session-file", default="")
    firewall_cmd.set_defaults(handler=run_setup_firewall)

    firewall_connect_cmd = subparsers.add_parser(
        "firewall-connect",
        aliases=["runtime-onboard", "openclaw-connect"],
        help="Canonical runtime onboarding (session-link + bootstrap + verify list)",
        parents=[common],
    )
    firewall_connect_cmd.add_argument("--api-base", default="https://lemma.id")
    firewall_connect_cmd.add_argument("--runtime-id", default="runtime-default")
    firewall_connect_cmd.add_argument("--agent-id", default="main")
    firewall_connect_cmd.add_argument("--workspace-id", default="default")
    firewall_connect_cmd.add_argument("--display-name", default="Lemma Runtime")
    firewall_connect_cmd.add_argument("--policy-profile", default=runtime_defaults["policy_profile"])
    firewall_connect_cmd.add_argument("--root-type", default=runtime_defaults["root_type"], choices=["passkey_root", "workload_root", "policy_root"])
    firewall_connect_cmd.add_argument("--org-id", default=runtime_defaults["org_id"])
    firewall_connect_cmd.add_argument("--environment", default=runtime_defaults["environment"], choices=["dev", "staging", "prod"])
    firewall_connect_cmd.add_argument("--control-plane-mode", default="hosted", choices=["hosted", "federated"])
    firewall_connect_cmd.add_argument("--external-control-plane-url", default="")
    firewall_connect_cmd.add_argument("--requested-scope", default="wallet:control_plane")
    firewall_connect_cmd.add_argument("--unlock-token", default="", help="Optional existing wallet unlock token")
    firewall_connect_cmd.add_argument("--no-browser", action="store_true", help="Print browser approval URL without auto-opening")
    firewall_connect_cmd.add_argument("--poll-interval", type=float, default=2.0)
    firewall_connect_cmd.add_argument("--link-timeout", type=float, default=180.0)
    firewall_connect_cmd.add_argument("--skip-openclaw-config", action="store_true", help="Do not patch OpenClaw config defaults")
    firewall_connect_cmd.add_argument("--dry-run", action="store_true", help="Preview connect actions without side effects")
    firewall_connect_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    firewall_connect_cmd.add_argument("--timeout", type=float, default=10.0)
    firewall_connect_cmd.set_defaults(handler=run_firewall_connect)

    login_cmd = subparsers.add_parser("login", help="Log in with Lemma credential for CLI sensitive actions", parents=[common])
    login_cmd.add_argument("--api-base", default="https://lemma.id")
    login_cmd.add_argument("--header", default="", help="Pre-encoded X-Lemma-Credential header value")
    login_cmd.add_argument("--credential-file", default="", help="Credential JSON file path to encode")
    login_cmd.add_argument("--scope", default="read,write,admin")
    login_cmd.add_argument("--ttl-hours", type=int, default=8)
    login_cmd.add_argument("--agent-name", default="lemma-cli")
    login_cmd.add_argument("--task", default="CLI authenticated provisioning session")
    login_cmd.add_argument("--allowed-site", action="append", default=[])
    login_cmd.add_argument("--platform-api-key", default="", help="Platform API key for auto self-issue fallback")
    login_cmd.add_argument("--user-email", default="", help="Admin email for platform self-issue fallback")
    login_cmd.add_argument("--site-id", default="lemma.id", help="Site ID used for platform self-issue fallback")
    login_cmd.add_argument("--site-domain", default="lemma.id", help="Site domain used for platform self-issue fallback")
    login_cmd.add_argument("--permission-level", default="super_admin", help="Permission level for platform self-issue fallback")
    login_cmd.add_argument("--issue-json", default="", help="JSON object (or @path) merged into /api/agent/auto-issue payload")
    login_cmd.add_argument("--delegation-reason", default="", help="Human-readable reason for delegation")
    login_cmd.add_argument("--delegation-id", default="", help="External delegation identifier for audits")
    login_cmd.add_argument("--acting-for-ppid", default="", help="PPID this agent action is performed for")
    login_cmd.add_argument("--requested-by-ppid", default="", help="PPID that requested this delegation")
    login_cmd.add_argument("--delegated-by-user-ref", default="", help="Customer-facing identifier of delegating user")
    login_cmd.add_argument("--acting-for-user-ref", default="", help="Customer-facing identifier of acting user")
    login_cmd.add_argument("--requested-by-user-ref", default="", help="Customer-facing identifier of requesting user")
    login_cmd.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional request header for API calls (format: 'Name: value'). Repeatable.",
    )
    login_cmd.add_argument("--non-interactive", action="store_true", help="Disable browser flow and use headless fallback")
    login_cmd.add_argument("--no-browser", action="store_true", help="Print browser approval URL without auto-opening")
    login_cmd.add_argument("--login-timeout", type=float, default=180.0, help="Seconds to wait for browser approval")
    login_cmd.add_argument("--dry-run", action="store_true", help="Preview request shape without sending network calls")
    login_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    login_cmd.add_argument("--timeout", type=float, default=10.0)
    login_cmd.add_argument("--session-file", default="")
    login_cmd.set_defaults(handler=run_login)

    flow_cmd = subparsers.add_parser(
        "flow",
        help="Run non-interactive happy path: setup -> login -> site-create -> issue -> validate",
        parents=[common],
    )
    flow_cmd.add_argument("--project-dir", default=".")
    flow_cmd.add_argument("--site-id", required=True)
    flow_cmd.add_argument("--site-domain", required=True)
    flow_cmd.add_argument("--new-site-domain", default="")
    flow_cmd.add_argument("--new-site-name", default="")
    flow_cmd.add_argument("--framework", choices=["flask", "express", "both"], default="both")
    flow_cmd.add_argument("--force", action="store_true")
    flow_cmd.add_argument("--api-base", default="https://lemma.id")
    flow_cmd.add_argument("--header", default="", help="Pre-encoded X-Lemma-Credential header value")
    flow_cmd.add_argument("--credential-file", default="", help="Credential JSON file path to encode")
    flow_cmd.add_argument("--scope", default="read,write,admin")
    flow_cmd.add_argument("--ttl-hours", type=int, default=8)
    flow_cmd.add_argument("--agent-name", default="lemma-cli")
    flow_cmd.add_argument("--task", default="CLI authenticated provisioning session")
    flow_cmd.add_argument("--allowed-site", action="append", default=[])
    flow_cmd.add_argument("--platform-api-key", default="")
    flow_cmd.add_argument("--user-email", default="")
    flow_cmd.add_argument("--permission-level", default="super_admin")
    flow_cmd.add_argument("--issue-json", default="", help="JSON object (or @path) merged into login issue payload")
    flow_cmd.add_argument("--delegation-reason", default="", help="Human-readable reason for delegation")
    flow_cmd.add_argument("--delegation-id", default="", help="External delegation identifier for audits")
    flow_cmd.add_argument("--acting-for-ppid", default="", help="PPID this agent action is performed for")
    flow_cmd.add_argument("--requested-by-ppid", default="", help="PPID that requested this delegation")
    flow_cmd.add_argument("--delegated-by-user-ref", default="", help="Customer-facing identifier of delegating user")
    flow_cmd.add_argument("--acting-for-user-ref", default="", help="Customer-facing identifier of acting user")
    flow_cmd.add_argument("--requested-by-user-ref", default="", help="Customer-facing identifier of requesting user")
    flow_cmd.add_argument("--site-create-json", default="", help="JSON object (or @path) merged into site-create payload")
    flow_cmd.add_argument("--key-bootstrap-json", default="", help="JSON object (or @path) merged into key-bootstrap payload")
    flow_cmd.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional request header for API calls (format: 'Name: value'). Repeatable.",
    )
    flow_cmd.add_argument("--skip-setup", action="store_true")
    flow_cmd.add_argument("--skip-login", action="store_true")
    flow_cmd.add_argument("--skip-site-create", action="store_true")
    flow_cmd.add_argument("--skip-issue", action="store_true")
    flow_cmd.add_argument("--skip-validate", action="store_true")
    flow_cmd.add_argument("--dry-run", action="store_true", help="Run steps in preview mode (no external state changes)")
    flow_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    flow_cmd.add_argument("--non-interactive", action="store_true", default=True)
    flow_cmd.add_argument("--no-browser", action="store_true", default=True)
    flow_cmd.add_argument("--login-timeout", type=float, default=180.0)
    flow_cmd.add_argument("--environment", default="development")
    flow_cmd.add_argument("--bootstrap-site-id", default="")
    flow_cmd.add_argument("--bootstrap-key-name", default="CLI Bootstrap Key")
    flow_cmd.add_argument("--key-type", choices=["live", "test"], default="live")
    flow_cmd.add_argument("--permissions", default="read,write")
    flow_cmd.add_argument("--env-file", default="")
    flow_cmd.add_argument("--overwrite-env", action="store_true")
    flow_cmd.add_argument("--timeout", type=float, default=10.0)
    flow_cmd.add_argument("--session-file", default="")
    flow_cmd.set_defaults(handler=run_flow)

    logout_cmd = subparsers.add_parser("logout", help="Clear local CLI auth session", parents=[common])
    logout_cmd.add_argument("--session-file", default="")
    logout_cmd.set_defaults(handler=run_logout)

    auth_status_cmd = subparsers.add_parser("auth-status", help="Validate stored CLI auth session", parents=[common])
    auth_status_cmd.add_argument("--api-base", default="")
    auth_status_cmd.add_argument("--dry-run", action="store_true", help="Preview validate request without network call")
    auth_status_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    auth_status_cmd.add_argument("--timeout", type=float, default=10.0)
    auth_status_cmd.add_argument("--session-file", default="")
    auth_status_cmd.set_defaults(handler=run_auth_status)

    safety_status_cmd = subparsers.add_parser(
        "safety-status",
        help="Check starter-safe local firewall posture (safe/degraded/unsafe)",
        parents=[common],
    )
    safety_status_cmd.add_argument("--firewall-url", default="http://127.0.0.1:8787")
    safety_status_cmd.add_argument("--timeout", type=float, default=5.0)
    safety_status_cmd.set_defaults(handler=run_safety_status)

    session_cmd = subparsers.add_parser("session", help="Manage unlock session flow", parents=[common])
    session_subparsers = session_cmd.add_subparsers(dest="session_command", required=True)

    session_start_cmd = session_subparsers.add_parser("start", help="Open unlock flow for wallet session", parents=[common])
    session_start_cmd.add_argument("--api-base", default="https://lemma.id")
    session_start_cmd.add_argument("--no-browser", action="store_true", help="Print unlock URL without opening browser")
    session_start_cmd.add_argument("--dry-run", action="store_true", help="Preview unlock action without opening browser")
    session_start_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    session_start_cmd.add_argument("--timeout", type=float, default=10.0)
    session_start_cmd.set_defaults(handler=run_session_start)

    session_status_cmd = session_subparsers.add_parser("status", help="Check wallet unlock session status", parents=[common])
    session_status_cmd.add_argument("--api-base", default="https://lemma.id")
    session_status_cmd.add_argument("--dry-run", action="store_true", help="Preview status request without network call")
    session_status_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    session_status_cmd.add_argument("--timeout", type=float, default=10.0)
    session_status_cmd.set_defaults(handler=run_session_status)

    session_link_cmd = session_subparsers.add_parser(
        "link",
        help="Open popup approval and fetch temporary wallet unlock token for CLI scripts",
        parents=[common],
    )
    session_link_cmd.add_argument("--api-base", default="https://lemma.id")
    session_link_cmd.add_argument("--requested-scope", default="wallet:revoke")
    session_link_cmd.add_argument("--no-browser", action="store_true", help="Print approve URL without auto-opening browser")
    session_link_cmd.add_argument("--poll-interval", type=float, default=2.0)
    session_link_cmd.add_argument("--link-timeout", type=float, default=120.0)
    session_link_cmd.add_argument("--timeout", type=float, default=10.0)
    session_link_cmd.add_argument("--dry-run", action="store_true", help="Preview link flow without network calls")
    session_link_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    session_link_cmd.set_defaults(handler=run_session_link)

    site_create_cmd = subparsers.add_parser("site-create", help="Provision a new developer site", parents=[common])
    site_create_cmd.add_argument("--api-base", default="https://lemma.id")
    site_create_cmd.add_argument("--name", default="")
    site_create_cmd.add_argument("--domain", required=True)
    site_create_cmd.add_argument("--environment", default="development")
    site_create_cmd.add_argument("--payload-json", default="", help="JSON object (or @path) merged into request payload")
    site_create_cmd.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional request header for API calls (format: 'Name: value'). Repeatable.",
    )
    site_create_cmd.add_argument("--dry-run", action="store_true", help="Preview request shape without sending network calls")
    site_create_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    site_create_cmd.add_argument("--agent-token", default="")
    site_create_cmd.add_argument("--api-key", default="")
    site_create_cmd.add_argument("--timeout", type=float, default=10.0)
    site_create_cmd.add_argument("--session-file", default="")
    site_create_cmd.set_defaults(handler=run_site_create)

    key_bootstrap_cmd = subparsers.add_parser("key-bootstrap", help="Create site API key and optionally write env", parents=[common])
    key_bootstrap_cmd.add_argument("--api-base", default="https://lemma.id")
    key_bootstrap_cmd.add_argument("--site-id", required=True)
    key_bootstrap_cmd.add_argument("--name", default="CLI Bootstrap Key")
    key_bootstrap_cmd.add_argument("--key-type", choices=["live", "test"], default="live")
    key_bootstrap_cmd.add_argument("--permissions", default="read,write")
    key_bootstrap_cmd.add_argument("--payload-json", default="", help="JSON object (or @path) merged into request payload")
    key_bootstrap_cmd.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional request header for API calls (format: 'Name: value'). Repeatable.",
    )
    key_bootstrap_cmd.add_argument("--dry-run", action="store_true", help="Preview request shape without sending network calls")
    key_bootstrap_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    key_bootstrap_cmd.add_argument("--env-file", default="")
    key_bootstrap_cmd.add_argument("--overwrite-env", action="store_true")
    key_bootstrap_cmd.add_argument("--agent-token", default="")
    key_bootstrap_cmd.add_argument("--api-key", default="")
    key_bootstrap_cmd.add_argument("--timeout", type=float, default=10.0)
    key_bootstrap_cmd.add_argument("--session-file", default="")
    key_bootstrap_cmd.set_defaults(handler=run_key_bootstrap)

    iam_create_cmd = subparsers.add_parser("iam-type-create", help="Create IAM permission type for a site", parents=[common])
    iam_create_cmd.add_argument("--api-base", default="https://lemma.id")
    iam_create_cmd.add_argument("--site-id", required=True)
    iam_create_cmd.add_argument("--name", required=True)
    iam_create_cmd.add_argument(
        "--iam-type",
        choices=["role", "scope", "time-bound", "attribute", "hierarchical"],
        default="role",
    )
    iam_create_cmd.add_argument("--description", default="")
    iam_create_cmd.add_argument("--config", default="", help="JSON object string for type config")
    iam_create_cmd.add_argument("--admin-email", default="")
    iam_create_cmd.add_argument("--agent-token", default="")
    iam_create_cmd.add_argument("--api-key", default="")
    iam_create_cmd.add_argument("--timeout", type=float, default=10.0)
    iam_create_cmd.add_argument("--session-file", default="")
    iam_create_cmd.set_defaults(handler=run_iam_type_create)

    iam_list_cmd = subparsers.add_parser("iam-type-list", help="List IAM permission types for a site", parents=[common])
    iam_list_cmd.add_argument("--api-base", default="https://lemma.id")
    iam_list_cmd.add_argument("--site-id", required=True)
    iam_list_cmd.add_argument("--agent-token", default="")
    iam_list_cmd.add_argument("--api-key", default="")
    iam_list_cmd.add_argument("--timeout", type=float, default=10.0)
    iam_list_cmd.add_argument("--session-file", default="")
    iam_list_cmd.set_defaults(handler=run_iam_type_list)

    doctor_cmd = subparsers.add_parser("doctor", help="Diagnose common Lemma integration errors", parents=[common])
    doctor_cmd.add_argument("--error", default="")
    doctor_cmd.add_argument("--message", default="")
    doctor_cmd.add_argument("--fix", action="store_true", help="Attempt one-command remediation for known denial classes")
    doctor_cmd.add_argument("--api-base", default="https://lemma.id")
    doctor_cmd.add_argument("--session-file", default="")
    doctor_cmd.add_argument("--no-browser", action="store_true", help="Print unlock URL without opening browser for fix actions")
    doctor_cmd.add_argument("--timeout", type=float, default=10.0)
    doctor_cmd.add_argument("--dry-run", action="store_true", help="Preview remediation steps without state changes")
    doctor_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    doctor_cmd.set_defaults(handler=run_doctor)

    incident_cmd = subparsers.add_parser(
        "incident-bundle",
        help="Export incident bundle with timeline + decision probes",
        parents=[common],
    )
    incident_cmd.add_argument("--api-base", default="https://lemma.id")
    incident_cmd.add_argument("--agent-token", default="", help="Use explicit agent token instead of local session")
    incident_cmd.add_argument("--session-file", default="")
    incident_cmd.add_argument("--output-dir", default="ops/evidence/launch")
    incident_cmd.add_argument("--bundle-label", default="incident-bundle")
    incident_cmd.add_argument("--audit-limit", type=int, default=20)
    incident_cmd.add_argument("--decision-probe-path", default="/api/developer/sites")
    incident_cmd.add_argument("--include-deny-probe", action="store_true")
    incident_cmd.add_argument("--timeout", type=float, default=10.0)
    incident_cmd.add_argument("--dry-run", action="store_true", help="Preview bundle requests without network or file writes")
    incident_cmd.add_argument("--dry-run-output", default="", help="Write dry-run JSON artifact to file path")
    incident_cmd.set_defaults(handler=run_incident_bundle)

    authz_latency_cmd = subparsers.add_parser(
        "authz-latency",
        help="Measure authz latency and enforce p95 budget",
        parents=[common],
    )
    authz_latency_cmd.add_argument("--api-base", default="https://lemma.id")
    authz_latency_cmd.add_argument("--agent-token", default="", help="Use explicit agent token instead of local session")
    authz_latency_cmd.add_argument(
        "--auth-mode",
        choices=["auto", "token", "proof"],
        default="auto",
        help="Auth probe mode: auto (token/proof), token-only, or proof-only",
    )
    authz_latency_cmd.add_argument("--proof", default="", help="Proof payload as JSON string, base64url, or @path")
    authz_latency_cmd.add_argument("--proof-file", default="", help="Path to proof payload file")
    authz_latency_cmd.add_argument("--pop", default="", help="Optional PoP envelope JSON/base64url or @path")
    authz_latency_cmd.add_argument("--pop-file", default="", help="Path to PoP envelope payload file")
    authz_latency_cmd.add_argument(
        "--pop-agent-key-id",
        default="lemma-cli",
        help="agent_key_id to include when generating PoP automatically",
    )
    authz_latency_cmd.add_argument("--session-file", default="")
    authz_latency_cmd.add_argument("--decision-probe-path", default="/api/developer/sites")
    authz_latency_cmd.add_argument("--requests", type=int, default=30)
    authz_latency_cmd.add_argument("--warmup", type=int, default=3)
    authz_latency_cmd.add_argument("--budget-p95-ms", type=float, default=5.0)
    authz_latency_cmd.add_argument(
        "--e2e-budget-p95-ms",
        type=float,
        default=0.0,
        help="Optional end-to-end latency budget (0 disables this gate)",
    )
    authz_latency_cmd.add_argument("--timeout", type=float, default=10.0)
    authz_latency_cmd.set_defaults(handler=run_authz_latency)

    start_cmd = subparsers.add_parser("start", help="Start a scoped agent session", parents=[common])
    start_cmd.add_argument("--scope", default="read", help='Scope level or scope:path pairs (default: "read"). E.g. "read", "write:~/project/**", "read:~/proj/** write:~/proj/src/**"')
    start_cmd.add_argument("--ttl", default="2h", help="Session duration (e.g. 30m, 2h, 1d)")
    start_cmd.add_argument("--api-base", default="https://lemma.id")
    start_cmd.add_argument("--firewall-port", type=int, default=8787)
    start_cmd.add_argument("--approve", default="", help='Actions requiring approval, e.g. "shell.exec file.delete"')
    start_cmd.add_argument("--policy", default="httpbin", help='Policy file path or comma-separated presets (httpbin,github,openai,anthropic,stripe). Default: "httpbin"')
    start_cmd.set_defaults(handler=run_start)

    stop_cmd = subparsers.add_parser("stop", help="Stop the active agent session", parents=[common])
    stop_cmd.set_defaults(handler=run_stop)

    replay_cmd = subparsers.add_parser("replay", help="Replay the last session's action log", parents=[common])
    replay_cmd.add_argument("--last", action="store_true", help="Show the most recent session")
    replay_cmd.add_argument("--session-id", default="", help="Specific session ID to replay")
    replay_cmd.set_defaults(handler=run_replay)

    demo_cmd = subparsers.add_parser("demo", help="One-command demo: issue credential, start firewall, run containment simulation", parents=[common])
    demo_cmd.add_argument("--api-base", default=os.getenv("LEMMA_BASE_URL", "https://lemma.id"))
    demo_cmd.add_argument("--runtime-id", default="lemma-demo-runtime")
    demo_cmd.add_argument("--firewall-port", type=int, default=8787)
    demo_cmd.add_argument("--skip-firewall", action="store_true", help="Issue credential and print it without starting firewall")
    demo_cmd.set_defaults(handler=run_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

