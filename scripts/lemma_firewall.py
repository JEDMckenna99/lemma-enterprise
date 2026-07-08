#!/usr/bin/env python3
"""
Lemma Firewall (AIM gateway).

Server-side enforcement gateway for agent API calls:
- Validates Lemma proof (or legacy token) on every request
- Enforces per-API/per-path/per-method policy locally
- Forwards only allowed calls to configured upstream APIs
- Authorizes local agent actions (file, shell, DB, etc.) via /aim/authorize
- Logs cross-API activity back to Lemma AIM monitor
"""

from __future__ import annotations

import collections
import fnmatch
import json
import queue
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from flask import Flask, Response, jsonify, request

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.authz.mode_policy import MODE_COMPAT_PROOF_WRAPPED, MODE_PROOF_REQUIRED, evaluate_mode_policy
from api.authz.replay import validate_pop_replay
from api.authz.verifier import evaluate_proof_native

# pylint: disable=broad-exception-caught,redefined-outer-name


@dataclass
class ApiPolicy:
    api_id: str
    base_url: str
    allowed_methods: set[str]
    path_prefixes: list[str]
    required_scope: str
    risk_tier: str
    forward_headers: set[str]
    action_type: str = ""
    taint_on_response: bool = False


def _load_policy(policy_path: str) -> tuple[dict[str, ApiPolicy], float]:
    raw = Path(policy_path).read_text(encoding="utf-8")
    data = json.loads(raw)
    apis = {}
    for api_id, cfg in (data.get("apis") or {}).items():
        methods = {str(m).upper() for m in (cfg.get("allowed_methods") or ["GET"])}
        prefixes = [str(p) for p in (cfg.get("path_prefixes") or ["/"])]
        forward_headers = {str(h).lower() for h in (cfg.get("forward_headers") or ["content-type", "authorization"])}
        apis[str(api_id)] = ApiPolicy(
            api_id=str(api_id),
            base_url=str(cfg.get("base_url") or "").rstrip("/"),
            allowed_methods=methods,
            path_prefixes=prefixes,
            required_scope=str(cfg.get("required_scope") or "").strip().lower(),
            risk_tier=str(cfg.get("risk_tier") or "low").strip().lower(),
            forward_headers=forward_headers,
            action_type=str(cfg.get("action_type") or "").strip(),
            taint_on_response=str(cfg.get("taint_on_response") or "").strip().lower() in {"1", "true", "yes", "on"},
        )
    timeout = float(data.get("default_timeout_seconds") or 25.0)
    return apis, timeout


LEMMA_BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
POLICY_PATH = os.environ.get(
    "LEMMA_FIREWALL_POLICY_FILE",
    str(Path(__file__).resolve().parent / "lemma_firewall_policy.example.json"),
)
DEFAULT_AGENT_TOKEN = os.environ.get("LEMMA_AGENT_TOKEN", "").strip()
DEFAULT_LEMMA_CREDENTIAL = os.environ.get("LEMMA_CREDENTIAL", "").strip()
DEFAULT_LEMMA_CREDENTIAL_FILE = os.environ.get("LEMMA_PROOF_FILE", "").strip()
DEFAULT_RUNTIME_ID = os.environ.get("LEMMA_FIREWALL_RUNTIME_ID", "lemma-firewall-default").strip() or "lemma-firewall-default"
LOG_EXTERNAL_ACTIVITY = str(os.environ.get("LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY", "1")).strip().lower() not in {"0", "false", "no", "off"}
LOCAL_PROOF_ENFORCEMENT = str(os.environ.get("LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT", "1")).strip().lower() not in {"0", "false", "no", "off"}
RUNTIME_AUTHORIZE_CACHE_TTL_MS = max(0, int(os.environ.get("LEMMA_FIREWALL_RUNTIME_AUTHORIZE_CACHE_TTL_MS", "30000") or "30000"))
CONTROL_PLANE_SYNC_ENABLED = str(os.environ.get("LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}
REVOCATION_SYNC_INTERVAL_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_REVOCATION_SYNC_INTERVAL_MS", "30000") or "30000"))
POLICY_SYNC_INTERVAL_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_POLICY_SYNC_INTERVAL_MS", "300000") or "300000"))
JWKS_SYNC_INTERVAL_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_JWKS_SYNC_INTERVAL_MS", "300000") or "300000"))
MAX_STALENESS_LOW_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_MAX_STALENESS_LOW_MS", "300000") or "300000"))
MAX_STALENESS_HIGH_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_MAX_STALENESS_HIGH_MS", "120000") or "120000"))
MAX_STALENESS_CRITICAL_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_MAX_STALENESS_CRITICAL_MS", "10000") or "10000"))
RUNTIME_AUTHORIZE_REQUIRED_TIERS = {
    part.strip().lower()
    for part in str(os.environ.get("LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS", "critical")).split(",")
    if part.strip()
}
RUNTIME_STATE_CACHE_TTL_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_RUNTIME_STATE_CACHE_TTL_MS", "120000") or "120000"))
TAINT_SYNC_INTERVAL_MS = max(1000, int(os.environ.get("LEMMA_FIREWALL_TAINT_SYNC_INTERVAL_MS", "10000") or "10000"))
TAINT_ENFORCEMENT_ENABLED = str(os.environ.get("LEMMA_FIREWALL_TAINT_ENFORCEMENT_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}
ONLINE_CHECK_ON_STALE_NONCRITICAL = str(os.environ.get("LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL", "0")).strip().lower() in {"1", "true", "yes", "on"}
PROOF_REQUIRED_TIERS = {
    part.strip().lower()
    for part in str(os.environ.get("LEMMA_FIREWALL_PROOF_REQUIRED_TIERS", "high,critical")).split(",")
    if part.strip()
}
COMPAT_FALLBACK_ALLOWED = str(os.environ.get("LEMMA_FIREWALL_COMPAT_FALLBACK_ALLOWED", "1")).strip().lower() not in {"0", "false", "no", "off"}
REQUIRE_FRESH_PASSKEY_STEPUP = str(os.environ.get("LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP", "0")).strip().lower() in {"1", "true", "yes", "on"}
LOCAL_OPS_GATE_ENABLED = str(os.environ.get("LEMMA_FIREWALL_LOCAL_OPS_GATE", "1")).strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OPS_LOG_DECISIONS = str(os.environ.get("LEMMA_FIREWALL_LOCAL_OPS_LOG_DECISIONS", "1")).strip().lower() not in {"0", "false", "no", "off"}
STEPUP_REQUIRED_TIERS = {
    part.strip().lower()
    for part in str(os.environ.get("LEMMA_FIREWALL_STEPUP_REQUIRED_TIERS", "critical")).split(",")
    if part.strip()
}
PASSKEY_AGE_ENFORCEMENT_ENABLED = str(os.environ.get("LEMMA_FIREWALL_PASSKEY_AGE_ENFORCEMENT", "1")).strip().lower() not in {"0", "false", "no", "off"}
PASSKEY_MAX_AGE_LOW = int(os.environ.get("LEMMA_FIREWALL_PASSKEY_MAX_AGE_LOW", "259200") or "259200")
PASSKEY_MAX_AGE_HIGH = int(os.environ.get("LEMMA_FIREWALL_PASSKEY_MAX_AGE_HIGH", "28800") or "28800")
PASSKEY_MAX_AGE_CRITICAL = int(os.environ.get("LEMMA_FIREWALL_PASSKEY_MAX_AGE_CRITICAL", "3600") or "3600")
TAINT_ON_VIOLATION_ENABLED = str(os.environ.get(
    "LEMMA_FIREWALL_TAINT_ON_VIOLATION_ENABLED", "0"
)).strip().lower() in {"1", "true", "yes", "on"}
SESSION_LOG_FILE = os.environ.get("LEMMA_SESSION_LOG_FILE", "").strip()
APPROVAL_REQUIRED_ACTIONS = [
    p.strip() for p in str(os.environ.get("LEMMA_FIREWALL_APPROVAL_REQUIRED_ACTIONS", "")).split(",")
    if p.strip()
]
APPROVAL_TIMEOUT_SECONDS = int(os.environ.get("LEMMA_FIREWALL_APPROVAL_TIMEOUT_SECONDS", "60") or "60")

POLICIES, DEFAULT_TIMEOUT_SECONDS = _load_policy(POLICY_PATH)
HTTP = requests.Session()
APP = Flask(__name__)
_RUNTIME_AUTHZ_CACHE: dict[str, dict] = {}
_RUNTIME_STATE_CACHE: dict[str, dict] = {}
_SYNC_LOCK = threading.Lock()
_SYNC_THREAD: threading.Thread | None = None
_SYNC_STATE: dict[str, object] = {
    "revocation_cursor": 0,
    "revoked_credential_ids": set(),
    "revoked_proof_ids": set(),
    "revoked_root_grant_ids": set(),
    "min_revocation_epoch": 0,
    "last_revocation_sync_ms": 0,
    "last_policy_sync_ms": 0,
    "last_jwks_sync_ms": 0,
    "last_taint_sync_ms": 0,
    "policy_version": None,
    "jwks_key_count": 0,
    "last_sync_error": None,
}
_RUNTIME_TAINT_CACHE: dict[str, int] = {}
_LOCAL_OPS_COUNTERS = {"allow": 0, "deny": 0}
_DECISION_RING: collections.deque = collections.deque(maxlen=500)
_DECISION_SUBSCRIBERS: list[queue.Queue] = []
_PENDING_APPROVALS: dict[str, threading.Event] = {}
_APPROVAL_RESULTS: dict[str, bool] = {}
_SESSION_ACTIONS_MAP: dict | None = None
_SESSION_SCOPE_OVERRIDE: set | None = None


def _log_local_decision(decision_body: dict) -> None:
    """Append decision to the local JSONL session log (best-effort)."""
    if not SESSION_LOG_FILE:
        return
    entry = {**decision_body, "timestamp": time.time()}
    try:
        Path(SESSION_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _publish_decision(decision_body: dict) -> None:
    """Push decision to the in-memory ring buffer and all SSE subscribers."""
    stamped = {**decision_body, "timestamp": time.time()}
    _DECISION_RING.append(stamped)
    dead: list[int] = []
    for i, q in enumerate(_DECISION_SUBSCRIBERS):
        try:
            q.put_nowait(stamped)
        except Exception:
            dead.append(i)
    for i in reversed(dead):
        _DECISION_SUBSCRIBERS.pop(i)


def _bump_taint_on_violation(runtime_id: str) -> None:
    """Increment the local taint epoch for a runtime after a scope/action violation."""
    if not TAINT_ON_VIOLATION_ENABLED:
        return
    with _SYNC_LOCK:
        current = _RUNTIME_TAINT_CACHE.get(runtime_id, 0)
        _RUNTIME_TAINT_CACHE[runtime_id] = current + 1


def _log_proxy_decision(api_id: str, path: str, method: str, allowed: bool,
                        action: str = "", error: str = "", upstream_status: int = 0) -> None:
    """Log a proxy decision to session JSONL and SSE stream."""
    body: dict = {"allowed": allowed, "action": action or f"api.call.{method.lower()}",
                  "api_id": api_id, "resource": f"/firewall/{api_id}/{path}", "method": method}
    if error:
        body["error"] = error
    if upstream_status:
        body["upstream_status"] = upstream_status
    _log_local_decision(body)
    _publish_decision(body)


def _action_requires_approval(action: str) -> bool:
    if not APPROVAL_REQUIRED_ACTIONS:
        return False
    return any(fnmatch.fnmatch(action, pat) for pat in APPROVAL_REQUIRED_ACTIONS)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _max_staleness_ms_for_risk(risk_tier: str) -> int:
    tier = str(risk_tier or "low").strip().lower()
    if tier == "critical":
        return MAX_STALENESS_CRITICAL_MS
    if tier == "high":
        return MAX_STALENESS_HIGH_MS
    return MAX_STALENESS_LOW_MS


def _sync_revocation_delta_once() -> None:
    with _SYNC_LOCK:
        since = int(_SYNC_STATE.get("revocation_cursor", 0) or 0)
    response = HTTP.get(
        f"{LEMMA_BASE_URL}/api/authz/revocation/delta",
        params={"since": since, "limit": 500},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    payload = response.json() if response.content else {}
    if response.status_code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"revocation_sync_failed:{response.status_code}")
    changes = payload.get("changes") if isinstance(payload.get("changes"), list) else []
    next_cursor = int(payload.get("next_cursor") or since)
    new_revoked = set()
    new_revoked_proof_ids = set()
    new_revoked_root_grant_ids = set()
    min_revocation_epoch = 0
    for item in changes:
        if not isinstance(item, dict):
            continue
        cred_id = str(item.get("credential_id") or "").strip()
        if cred_id:
            new_revoked.add(cred_id)
        proof_id = str(item.get("proof_id") or "").strip()
        if proof_id:
            new_revoked_proof_ids.add(proof_id)
        root_grant_id = str(item.get("root_grant_id") or "").strip()
        if root_grant_id:
            new_revoked_root_grant_ids.add(root_grant_id)
        ancestor_ids = item.get("ancestor_ids") if isinstance(item.get("ancestor_ids"), list) else []
        for ancestor_id in ancestor_ids:
            ancestor = str(ancestor_id or "").strip()
            lowered_ancestor = ancestor.lower()
            if ancestor.startswith(("dpf_", "prf_", "proof_")):
                new_revoked_proof_ids.add(ancestor)
            elif ancestor.startswith(("rgr_", "wkr_", "plr_", "root_grant_")):
                new_revoked_root_grant_ids.add(ancestor)
            elif lowered_ancestor.startswith("proof:"):
                new_revoked_proof_ids.add(ancestor.partition(":")[2].strip())
            elif lowered_ancestor.startswith(("root_grant:", "grant:", "workload_root:", "policy_root:")):
                new_revoked_root_grant_ids.add(ancestor.partition(":")[2].strip())
        try:
            epoch_val = int(item.get("revocation_epoch") or 0)
        except (TypeError, ValueError):
            epoch_val = 0
        if epoch_val > min_revocation_epoch:
            min_revocation_epoch = epoch_val
    with _SYNC_LOCK:
        revoked = set(_SYNC_STATE.get("revoked_credential_ids") or set())
        revoked_proofs = set(_SYNC_STATE.get("revoked_proof_ids") or set())
        revoked_roots = set(_SYNC_STATE.get("revoked_root_grant_ids") or set())
        revoked.update(new_revoked)
        revoked_proofs.update(new_revoked_proof_ids)
        revoked_roots.update(new_revoked_root_grant_ids)
        _SYNC_STATE["revoked_credential_ids"] = revoked
        _SYNC_STATE["revoked_proof_ids"] = revoked_proofs
        _SYNC_STATE["revoked_root_grant_ids"] = revoked_roots
        _SYNC_STATE["min_revocation_epoch"] = max(int(_SYNC_STATE.get("min_revocation_epoch") or 0), min_revocation_epoch)
        _SYNC_STATE["revocation_cursor"] = max(next_cursor, since)
        _SYNC_STATE["last_revocation_sync_ms"] = _now_ms()
        _SYNC_STATE["last_sync_error"] = None


def _sync_policy_snapshot_once() -> None:
    response = HTTP.get(f"{LEMMA_BASE_URL}/api/authz/policy/snapshot", timeout=DEFAULT_TIMEOUT_SECONDS)
    payload = response.json() if response.content else {}
    if response.status_code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"policy_sync_failed:{response.status_code}")
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    policy_version = str(policy.get("policy_version") or "").strip() or None
    with _SYNC_LOCK:
        _SYNC_STATE["policy_version"] = policy_version
        _SYNC_STATE["last_policy_sync_ms"] = _now_ms()
        _SYNC_STATE["last_sync_error"] = None


def _sync_jwks_once() -> None:
    response = HTTP.get(f"{LEMMA_BASE_URL}/api/authz/jwks", timeout=DEFAULT_TIMEOUT_SECONDS)
    payload = response.json() if response.content else {}
    if response.status_code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"jwks_sync_failed:{response.status_code}")
    jwks = payload.get("jwks") if isinstance(payload.get("jwks"), dict) else {}
    keys = jwks.get("keys") if isinstance(jwks.get("keys"), list) else []
    synced_issuers = set()
    for key in keys:
        issuer_did = str(key.get("issuer") or "").strip()
        if issuer_did.startswith("did:lemma:"):
            synced_issuers.add(issuer_did)
    if synced_issuers:
        existing = set(d.strip() for d in os.environ.get("TRUSTED_ISSUER_DIDS", "").split(",") if d.strip())
        merged = existing | synced_issuers
        os.environ["TRUSTED_ISSUER_DIDS"] = ",".join(sorted(merged))
        try:
            from api.trusted_issuers import _clear_cache
            _clear_cache()
        except (ImportError, AttributeError):
            pass
    with _SYNC_LOCK:
        _SYNC_STATE["jwks_key_count"] = len(keys)
        _SYNC_STATE["trusted_issuer_count"] = len(synced_issuers)
        _SYNC_STATE["last_jwks_sync_ms"] = _now_ms()
        _SYNC_STATE["last_sync_error"] = None


def _sync_runtime_taint_once() -> None:
    """Fetch current taint epoch for the default runtime from the control plane.

    Tries two paths:
    1. GET /api/demo/state (no auth, works for demo-allowlisted runtimes)
    2. POST /api/wallet/runtimes/<id>/authorize (requires credential, works for all runtimes)
    """
    if not TAINT_ENFORCEMENT_ENABLED:
        return
    runtime_id = DEFAULT_RUNTIME_ID

    # Path 1: demo state endpoint (no auth required)
    try:
        response = HTTP.get(
            f"{LEMMA_BASE_URL}/api/demo/state",
            params={"runtime_id": runtime_id},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            payload = response.json() if response.content else {}
            state = payload.get("runtime_state", payload)
            taint_epoch = int(state.get("taint_epoch") or 0)
            with _SYNC_LOCK:
                _RUNTIME_TAINT_CACHE[runtime_id] = taint_epoch
                _SYNC_STATE["last_taint_sync_ms"] = _now_ms()
            return
    except Exception:
        pass

    # Path 2: runtime authorize probe (requires credential or token)
    credential = DEFAULT_LEMMA_CREDENTIAL
    if not credential and DEFAULT_LEMMA_CREDENTIAL_FILE and Path(DEFAULT_LEMMA_CREDENTIAL_FILE).exists():
        credential = Path(DEFAULT_LEMMA_CREDENTIAL_FILE).read_text(encoding="utf-8").strip()
    headers = {"Content-Type": "application/json"}
    if credential:
        headers["X-Lemma-Credential"] = credential
    elif DEFAULT_AGENT_TOKEN:
        headers["X-Agent-Token"] = DEFAULT_AGENT_TOKEN
    else:
        return
    try:
        response = HTTP.post(
            f"{LEMMA_BASE_URL}/api/wallet/runtimes/{runtime_id}/authorize",
            headers=headers,
            json={"action": "taint_sync_probe", "risk": "low", "resource": "firewall_sync"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            payload = response.json() if response.content else {}
            taint_epoch = int(payload.get("taint_epoch") or 0)
            with _SYNC_LOCK:
                _RUNTIME_TAINT_CACHE[runtime_id] = taint_epoch
                _SYNC_STATE["last_taint_sync_ms"] = _now_ms()
    except Exception:
        pass


def _get_runtime_taint_epoch(runtime_id: str) -> int | None:
    """Return the cached taint epoch for a runtime, or None if unknown."""
    with _SYNC_LOCK:
        return _RUNTIME_TAINT_CACHE.get(runtime_id)


def _sync_loop() -> None:
    while CONTROL_PLANE_SYNC_ENABLED:
        now = _now_ms()
        with _SYNC_LOCK:
            last_revocation = int(_SYNC_STATE.get("last_revocation_sync_ms") or 0)
            last_policy = int(_SYNC_STATE.get("last_policy_sync_ms") or 0)
            last_jwks = int(_SYNC_STATE.get("last_jwks_sync_ms") or 0)
            last_taint = int(_SYNC_STATE.get("last_taint_sync_ms") or 0)
        try:
            if now - last_revocation >= REVOCATION_SYNC_INTERVAL_MS:
                _sync_revocation_delta_once()
            if now - last_policy >= POLICY_SYNC_INTERVAL_MS:
                _sync_policy_snapshot_once()
            if now - last_jwks >= JWKS_SYNC_INTERVAL_MS:
                _sync_jwks_once()
            if now - last_taint >= TAINT_SYNC_INTERVAL_MS:
                _sync_runtime_taint_once()
        except Exception as exc:  # pragma: no cover
            with _SYNC_LOCK:
                _SYNC_STATE["last_sync_error"] = str(exc)
        time.sleep(1.0)


def _ensure_sync_thread_started() -> None:
    global _SYNC_THREAD
    if not CONTROL_PLANE_SYNC_ENABLED:
        return
    if _SYNC_THREAD and _SYNC_THREAD.is_alive():
        return
    _SYNC_THREAD = threading.Thread(target=_sync_loop, name="lemma-firewall-sync", daemon=True)
    _SYNC_THREAD.start()


def _is_locally_revoked(credential_id: str) -> bool:
    if not credential_id:
        return False
    with _SYNC_LOCK:
        revoked_ids = _SYNC_STATE.get("revoked_credential_ids") or set()
        return credential_id in revoked_ids


def _revocation_stale_for_risk(risk_tier: str) -> bool:
    if not CONTROL_PLANE_SYNC_ENABLED:
        return False
    now = _now_ms()
    with _SYNC_LOCK:
        last_revocation = int(_SYNC_STATE.get("last_revocation_sync_ms") or 0)
    if last_revocation <= 0:
        return True
    return (now - last_revocation) > _max_staleness_ms_for_risk(risk_tier)


def _token_from_request() -> str:
    token = str(request.headers.get("X-Agent-Token") or "").strip()
    if token:
        return token
    return DEFAULT_AGENT_TOKEN


def _lemma_credential_from_request() -> str:
    header_value = str(request.headers.get("X-Lemma-Credential") or "").strip()
    if header_value:
        return header_value
    if DEFAULT_LEMMA_CREDENTIAL:
        return DEFAULT_LEMMA_CREDENTIAL
    if DEFAULT_LEMMA_CREDENTIAL_FILE and Path(DEFAULT_LEMMA_CREDENTIAL_FILE).exists():
        return Path(DEFAULT_LEMMA_CREDENTIAL_FILE).read_text(encoding="utf-8").strip()
    return ""


def _lemma_proof_from_request() -> str:
    return str(request.headers.get("X-Lemma-Proof") or "").strip()


def _decode_json_object(raw_text: str) -> dict:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _scope_from_proof_payload(proof_payload: dict) -> list[str]:
    delegated = proof_payload.get("delegated_proof") if isinstance(proof_payload.get("delegated_proof"), dict) else {}
    claims = delegated.get("claims") if isinstance(delegated.get("claims"), dict) else {}
    raw_scope = (
        delegated.get("scope")
        or proof_payload.get("scope")
        or claims.get("scope")
        or claims.get("permissions")
        or []
    )
    if isinstance(raw_scope, str):
        return [part.strip().lower() for part in raw_scope.replace(";", ",").split(",") if part.strip()]
    if isinstance(raw_scope, list):
        return [str(part).strip().lower() for part in raw_scope if str(part).strip()]
    return []


def _expected_mode_for_risk(risk_tier: str) -> str:
    tier = str(risk_tier or "low").strip().lower()
    if tier in PROOF_REQUIRED_TIERS:
        return MODE_PROOF_REQUIRED
    return MODE_COMPAT_PROOF_WRAPPED


def _is_locally_revoked_chain(
    *,
    credential_id: str | None,
    proof_id: str | None,
    root_grant_id: str | None,
    ancestor_ids: list[str] | None = None,
) -> bool:
    with _SYNC_LOCK:
        revoked_credential_ids = set(_SYNC_STATE.get("revoked_credential_ids") or set())
        revoked_proof_ids = set(_SYNC_STATE.get("revoked_proof_ids") or set())
        revoked_root_grant_ids = set(_SYNC_STATE.get("revoked_root_grant_ids") or set())
    cred_id = str(credential_id or "").strip()
    proof_key = str(proof_id or "").strip()
    root_key = str(root_grant_id or "").strip()
    normalized_ancestors = [str(item or "").strip() for item in (ancestor_ids or []) if str(item or "").strip()]
    ancestor_revoked = False
    for ancestor in normalized_ancestors:
        if ancestor in revoked_proof_ids or ancestor in revoked_root_grant_ids:
            ancestor_revoked = True
            break
    return bool(
        (cred_id and cred_id in revoked_credential_ids)
        or (proof_key and proof_key in revoked_proof_ids)
        or (root_key and root_key in revoked_root_grant_ids)
        or ancestor_revoked
    )


def _validate_agent_token(token: str) -> tuple[bool, dict]:
    if not token:
        return False, {"error": "missing_agent_token"}
    try:
        response = HTTP.post(
            f"{LEMMA_BASE_URL}/api/agent/validate",
            headers={"X-Agent-Token": token, "Content-Type": "application/json"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        payload = response.json() if response.content else {}
        if response.status_code != 200 or not bool(payload.get("valid")):
            return False, payload or {"error": "invalid_agent_token"}
        return True, payload
    except Exception as exc:  # pragma: no cover
        return False, {"error": f"token_validation_failed: {exc}"}


def _parse_scope_from_lemma_credential(lemma_credential: str) -> set[str]:
    try:
        payload = json.loads(lemma_credential)
    except Exception:
        return set()
    claims = payload.get("claims") or payload.get("credentialSubject") or {}
    scope = claims.get("scope") or claims.get("permissions") or claims.get("permission")
    if isinstance(scope, list):
        return {str(s).strip().lower() for s in scope if str(s).strip()}
    if isinstance(scope, str):
        raw = scope.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import ast
                parsed = ast.literal_eval(raw)
                if isinstance(parsed, list):
                    return {
                        str(item).strip().strip("[]'\"").lower()
                        for item in parsed
                        if str(item).strip().strip("[]'\"")
                    }
            except (ValueError, SyntaxError):
                pass
        parts = [p.strip().strip("[]'\"").lower() for p in raw.replace(";", ",").split(",")]
        return {p for p in parts if p}
    return set()


def _validate_lemma_credential(lemma_credential: str) -> tuple[bool, dict]:
    if LOCAL_PROOF_ENFORCEMENT:
        return _validate_lemma_credential_local(lemma_credential)
    return _validate_lemma_credential_remote(lemma_credential)


def _validate_lemma_credential_local(lemma_credential: str) -> tuple[bool, dict]:
    if not lemma_credential:
        return False, {"error": "missing_lemma_credential"}
    try:
        payload = json.loads(lemma_credential)
    except Exception:
        return False, {"error": "invalid_lemma_credential"}
    if not isinstance(payload, dict):
        return False, {"error": "invalid_lemma_credential"}

    try:
        from api.trusted_issuers import verify_credential_with_trust
    except Exception as exc:
        return False, {"error": f"local_verifier_unavailable: {exc}"}

    verification = verify_credential_with_trust(payload)
    if not bool((verification or {}).get("valid")):
        reason = str((verification or {}).get("reason") or "invalid_lemma_credential")
        return False, {"error": reason}

    claims = payload.get("claims") or payload.get("credentialSubject") or {}

    expires_raw = claims.get("expires_at") or payload.get("expires_at")
    if expires_raw is not None:
        try:
            expires_ts = float(expires_raw)
            if time.time() > expires_ts:
                return False, {"error": "credential_expired", "expires_at": expires_ts}
        except (TypeError, ValueError):
            pass
    normalized = {
        "scope": sorted(_parse_scope_from_lemma_credential(lemma_credential)),
        "credential_id": str(payload.get("id") or "").strip() or None,
        "ppid": str(
            payload.get("subject")
            or payload.get("sub")
            or claims.get("sub")
            or claims.get("ppid")
            or claims.get("id")
            or ""
        ).strip()
        or None,
    }
    for key in ("site_id", "site_domain", "permission_id", "permission_level"):
        if key in claims:
            normalized[key] = claims.get(key)
    taint_raw = claims.get("taint_epoch")
    if taint_raw is not None:
        try:
            normalized["taint_epoch"] = int(taint_raw)
        except (TypeError, ValueError):
            pass
    passkey_raw = claims.get("passkey_verified_at")
    if passkey_raw is not None:
        try:
            normalized["passkey_verified_at"] = int(passkey_raw)
        except (TypeError, ValueError):
            pass
    actions_raw = claims.get("actions")
    if actions_raw is not None:
        if isinstance(actions_raw, str):
            try:
                import json as _json
                normalized["actions"] = _json.loads(actions_raw)
            except (ValueError, TypeError):
                pass
        elif isinstance(actions_raw, dict):
            normalized["actions"] = actions_raw
    return True, normalized


def _validate_lemma_credential_remote(lemma_credential: str) -> tuple[bool, dict]:
    if not lemma_credential:
        return False, {"error": "missing_lemma_credential"}
    try:
        response = HTTP.post(
            f"{LEMMA_BASE_URL}/api/auth/exchange-proof",
            headers={
                "X-Lemma-Credential": lemma_credential,
                "Content-Type": "application/json",
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        payload = response.json() if response.content else {}
        if response.status_code != 200:
            return False, payload or {"error": "invalid_lemma_credential"}
        payload = payload if isinstance(payload, dict) else {}
        payload["scope"] = sorted(_parse_scope_from_lemma_credential(lemma_credential))
        return True, payload
    except Exception as exc:  # pragma: no cover
        return False, {"error": f"lemma_credential_validation_failed: {exc}"}


def _runtime_id_from_request() -> str:
    runtime_id = str(request.headers.get("X-Lemma-Firewall-Runtime-Id") or "").strip()
    if runtime_id:
        return runtime_id
    return DEFAULT_RUNTIME_ID


def _runtime_active_for_credential(
    lemma_credential: str,
    runtime_id: str,
    *,
    action: str,
    resource: str,
    risk: str,
) -> tuple[bool, dict]:
    try:
        org_id = str(os.getenv("LEMMA_ORG_ID") or "org_default").strip() or "org_default"
        environment = str(os.getenv("LEMMA_ENVIRONMENT") or "prod").strip() or "prod"
        root_type = str(os.getenv("LEMMA_ROOT_TYPE") or "passkey_root").strip() or "passkey_root"
        response = HTTP.post(
            f"{LEMMA_BASE_URL}/api/wallet/runtimes/{runtime_id}/authorize",
            headers={
                "X-Lemma-Credential": lemma_credential,
                "X-Lemma-Org-Id": org_id,
                "X-Lemma-Environment": environment,
                "Content-Type": "application/json",
            },
            json={
                "action": action,
                "resource": resource,
                "risk": risk,
                "org_id": org_id,
                "environment": environment,
                "root_type": root_type,
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        payload = response.json() if response.content else {}
        if response.status_code != 200:
            return False, payload if isinstance(payload, dict) else {"error": "runtime_not_authorized"}
        return True, payload if isinstance(payload, dict) else {}
    except Exception as exc:  # pragma: no cover
        return False, {"error": f"runtime_authorize_failed: {exc}"}


def _runtime_active_for_credential_cached(
    lemma_credential: str,
    runtime_id: str,
    *,
    action: str,
    resource: str,
    risk: str,
    force_refresh: bool = False,
) -> tuple[bool, dict]:
    now_ms = int(time.time() * 1000)
    entry = _RUNTIME_AUTHZ_CACHE.get(runtime_id)
    if (not force_refresh) and entry and int(entry.get("expires_at_ms", 0)) > now_ms:
        return bool(entry.get("ok")), dict(entry.get("payload") or {})

    ok, payload = _runtime_active_for_credential(
        lemma_credential,
        runtime_id,
        action=action,
        resource=resource,
        risk=risk,
    )
    if ok:
        _RUNTIME_AUTHZ_CACHE[runtime_id] = {
            "ok": True,
            "payload": dict(payload or {}),
            "expires_at_ms": now_ms + RUNTIME_AUTHORIZE_CACHE_TTL_MS,
        }
    else:
        _RUNTIME_AUTHZ_CACHE.pop(runtime_id, None)
    return ok, payload


def _runtime_state_cache_key(*, runtime_id: str, auth_payload: dict) -> str:
    ppid = str((auth_payload or {}).get("ppid") or "").strip().lower()
    if ppid:
        return f"{runtime_id}|{ppid}"
    credential_id = str((auth_payload or {}).get("credential_id") or "").strip()
    if credential_id:
        return f"{runtime_id}|cred:{credential_id}"
    return runtime_id


def _runtime_state_cached(*, runtime_id: str, auth_payload: dict) -> dict | None:
    now_ms = _now_ms()
    key = _runtime_state_cache_key(runtime_id=runtime_id, auth_payload=auth_payload)
    entry = _RUNTIME_STATE_CACHE.get(key)
    if not entry:
        return None
    if int(entry.get("expires_at_ms", 0)) <= now_ms:
        _RUNTIME_STATE_CACHE.pop(key, None)
        return None
    return dict(entry)


def _runtime_state_update(*, runtime_id: str, auth_payload: dict, active: bool, source: str) -> None:
    key = _runtime_state_cache_key(runtime_id=runtime_id, auth_payload=auth_payload)
    _RUNTIME_STATE_CACHE[key] = {
        "active": bool(active),
        "source": str(source),
        "updated_at_ms": _now_ms(),
        "expires_at_ms": _now_ms() + RUNTIME_STATE_CACHE_TTL_MS,
    }


def _scope_allowed(required_scope: str, token_payload: dict) -> bool:
    if not required_scope:
        return True
    if _SESSION_SCOPE_OVERRIDE is not None and required_scope in _SESSION_SCOPE_OVERRIDE:
        return True
    scope = token_payload.get("scope") or []
    if isinstance(scope, str):
        scope = [scope]
    normalized = {str(s).strip().lower() for s in scope if s}
    return required_scope in normalized


def _resolve_action_type(policy: ApiPolicy, method: str) -> str:
    """Map a request to an action type based on policy config and HTTP method."""
    if policy.action_type:
        return policy.action_type
    method_upper = method.upper()
    if method_upper == "GET":
        return "api.call.read"
    if method_upper in {"POST", "PUT", "PATCH"}:
        return "api.call.write"
    if method_upper == "DELETE":
        return "file.delete"
    return "api.call.read"


def _path_allowed(path: str, prefixes: list[str]) -> bool:
    normalized = "/" + str(path or "").lstrip("/")
    for prefix in prefixes:
        pref = "/" + str(prefix or "").lstrip("/")
        if normalized.startswith(pref):
            return True
    return False


def _log_external_activity(
    token: str,
    lemma_credential: str,
    api_policy: ApiPolicy,
    upstream_path: str,
    status_code: int,
    success: bool,
    runtime_id: str,
) -> None:
    if not LOG_EXTERNAL_ACTIVITY:
        return
    try:
        headers = {"Content-Type": "application/json"}
        if lemma_credential:
            headers["X-Lemma-Credential"] = lemma_credential
        elif token:
            headers["X-Agent-Token"] = token

        HTTP.post(
            f"{LEMMA_BASE_URL}/api/agent/monitor/log-external",
            headers=headers,
            json={
                "action": "external_api_call",
                "resource": api_policy.api_id,
                "upstream_api_id": api_policy.api_id,
                "upstream_base_url": api_policy.base_url,
                "target_url": f"{api_policy.base_url}/{upstream_path.lstrip('/')}",
                "method": request.method,
                "path": f"/{upstream_path.lstrip('/')}",
                "status_code": int(status_code),
                "success": bool(success),
                "risk_tier": api_policy.risk_tier,
                "runtime_id": runtime_id,
                "path_allowed": True,
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except Exception:
        # Best-effort logging only.
        return


@APP.route("/aim/health", methods=["GET"])
def health():
    with _SYNC_LOCK:
        taint_view = dict(_RUNTIME_TAINT_CACHE)
        sync_view = {
            "enabled": CONTROL_PLANE_SYNC_ENABLED,
            "last_revocation_sync_ms": int(_SYNC_STATE.get("last_revocation_sync_ms") or 0),
            "last_policy_sync_ms": int(_SYNC_STATE.get("last_policy_sync_ms") or 0),
            "last_jwks_sync_ms": int(_SYNC_STATE.get("last_jwks_sync_ms") or 0),
            "last_taint_sync_ms": int(_SYNC_STATE.get("last_taint_sync_ms") or 0),
            "revoked_credential_count": len(_SYNC_STATE.get("revoked_credential_ids") or set()),
            "revoked_proof_count": len(_SYNC_STATE.get("revoked_proof_ids") or set()),
            "revoked_root_grant_count": len(_SYNC_STATE.get("revoked_root_grant_ids") or set()),
            "min_revocation_epoch": int(_SYNC_STATE.get("min_revocation_epoch") or 0),
            "runtime_taint_epochs": taint_view,
            "policy_version": _SYNC_STATE.get("policy_version"),
            "jwks_key_count": int(_SYNC_STATE.get("jwks_key_count") or 0),
            "last_sync_error": _SYNC_STATE.get("last_sync_error"),
        }
    return jsonify(
        {
            "ok": True,
            "lemma_base_url": LEMMA_BASE_URL,
            "policy_path": POLICY_PATH,
            "auth_mode": "proof" if (DEFAULT_LEMMA_CREDENTIAL or DEFAULT_LEMMA_CREDENTIAL_FILE) else "token",
            "local_proof_enforcement": LOCAL_PROOF_ENFORCEMENT,
            "runtime_authorize_cache_ttl_ms": RUNTIME_AUTHORIZE_CACHE_TTL_MS,
            "runtime_state_cache_ttl_ms": RUNTIME_STATE_CACHE_TTL_MS,
            "runtime_authorize_required_tiers": sorted(RUNTIME_AUTHORIZE_REQUIRED_TIERS),
            "online_check_on_stale_noncritical": ONLINE_CHECK_ON_STALE_NONCRITICAL,
            "proof_required_tiers": sorted(PROOF_REQUIRED_TIERS),
            "compat_fallback_allowed": COMPAT_FALLBACK_ALLOWED,
            "require_fresh_passkey_stepup": REQUIRE_FRESH_PASSKEY_STEPUP,
            "stepup_required_tiers": sorted(STEPUP_REQUIRED_TIERS),
            "taint_enforcement_enabled": TAINT_ENFORCEMENT_ENABLED,
            "passkey_age_enforcement": PASSKEY_AGE_ENFORCEMENT_ENABLED,
            "passkey_max_age": {"low": PASSKEY_MAX_AGE_LOW, "high": PASSKEY_MAX_AGE_HIGH, "critical": PASSKEY_MAX_AGE_CRITICAL},
            "local_ops_gate": {
                "enabled": LOCAL_OPS_GATE_ENABLED,
                "log_decisions": LOCAL_OPS_LOG_DECISIONS,
                "decisions_allow": _LOCAL_OPS_COUNTERS["allow"],
                "decisions_deny": _LOCAL_OPS_COUNTERS["deny"],
            },
            "sync": sync_view,
            "apis": sorted(POLICIES.keys()),
            "runtime_id": DEFAULT_RUNTIME_ID,
        }
    )


@APP.route("/aim/revoke", methods=["POST"])
def local_revoke():
    """Add a credential ID to the local revocation set (immediate, no sync needed)."""
    body = request.get_json(silent=True) or {}
    credential_id = str(body.get("credential_id") or "").strip()
    if not credential_id:
        return jsonify({"success": False, "error": "credential_id_required"}), 400
    with _SYNC_LOCK:
        revoked = set(_SYNC_STATE.get("revoked_credential_ids") or set())
        revoked.add(credential_id)
        _SYNC_STATE["revoked_credential_ids"] = revoked
    return jsonify({"success": True, "credential_id": credential_id, "event": "credential_revoked_local"})


def _authorize_local_op(
    *,
    action: str,
    resource: str,
    risk_override: str | None = None,
    metadata: dict | None = None,
) -> tuple[dict, int]:
    """Shared authorization logic for local agent actions.

    Validates the request credential/proof against the action taxonomy,
    scope hierarchy, path bounds, revocation state, runtime kill switch,
    and taint epoch -- same enforcement pipeline as the HTTP proxy but
    for arbitrary local actions (file I/O, shell, DB, etc.).

    Returns (response_body, status_code).
    """
    from api.action_taxonomy import (
        TAXONOMY,
        RISK_ORDER,
        SCOPE_HIERARCHY,
        check_action_granted,
        risk_for_action,
        scope_for_action,
    )

    _ensure_sync_thread_started()
    decision_id = f"lop_{uuid.uuid4().hex[:16]}"
    now_ts = int(time.time())

    if not action:
        return {"allowed": False, "error": "action_required", "decision_id": decision_id}, 400

    known_action = action in TAXONOMY
    risk_tier = str(risk_override or "").strip().lower()
    if not risk_tier:
        risk_tier = risk_for_action(action) if known_action else "critical"
    required_scope = scope_for_action(action) if known_action else "admin"

    lemma_credential = _lemma_credential_from_request()
    lemma_proof = _lemma_proof_from_request()
    token = _token_from_request()
    runtime_id = _runtime_id_from_request()

    expected_mode = _expected_mode_for_risk(risk_tier)
    mode_decision = evaluate_mode_policy(expected_mode=expected_mode, headers=request.headers)
    if not mode_decision.allowed:
        _LOCAL_OPS_COUNTERS["deny"] += 1
        return {
            "allowed": False,
            "error": mode_decision.reason_code or "auth_mode_denied",
            "decision_id": decision_id,
            "action": action,
            "risk": risk_tier,
        }, 403

    if (
        expected_mode == MODE_PROOF_REQUIRED
        and not mode_decision.proof_present
        and str(os.environ.get("LEMMA_ENFORCE_PROOF_REQUIRED", "0") or "0").strip().lower()
        in {"1", "true", "yes", "on"}
    ):
        _LOCAL_OPS_COUNTERS["deny"] += 1
        return {
            "allowed": False,
            "error": "AUTH_PROOF_REQUIRED",
            "decision_id": decision_id,
            "action": action,
            "risk": risk_tier,
        }, 403

    auth_payload = {}
    used_proof = False

    if mode_decision.proof_present:
        proof_payload = _decode_json_object(lemma_proof)
        with _SYNC_LOCK:
            revoked_proof_ids = set(_SYNC_STATE.get("revoked_proof_ids") or set())
            revoked_root_grant_ids = set(_SYNC_STATE.get("revoked_root_grant_ids") or set())
            min_revocation_epoch = int(_SYNC_STATE.get("min_revocation_epoch") or 0)
        proof_eval = evaluate_proof_native(
            headers=request.headers,
            method="POST",
            path=str(resource or "/"),
            required_scope=required_scope,
            base_url=LEMMA_BASE_URL,
            revoked_proof_ids=revoked_proof_ids,
            revoked_root_grant_ids=revoked_root_grant_ids,
            min_revocation_epoch=min_revocation_epoch,
        )
        if not proof_eval.allowed:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": proof_eval.reason_code or "AUTH_CHAIN_BROKEN",
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 403
        auth_payload = {
            "scope": _scope_from_proof_payload(proof_payload),
            "proof_id": proof_eval.proof_id,
            "root_grant_id": proof_eval.root_grant_id,
            "auth_mode": "proof_native",
            "ppid": str(
                (proof_payload.get("delegated_proof") or {}).get("acting_for_ppid")
                or (proof_payload.get("root_proof") or {}).get("subject_ppid")
                or ""
            ).strip()
            or None,
        }
        if _is_locally_revoked_chain(
            credential_id=None,
            proof_id=proof_eval.proof_id,
            root_grant_id=proof_eval.root_grant_id,
        ):
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": "revoked_proof_chain_local",
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 403
        used_proof = True

    if not used_proof and lemma_credential:
        valid, auth_payload = _validate_lemma_credential(lemma_credential)
        if not valid:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": auth_payload.get("error", "invalid_lemma_credential"),
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 401
        credential_id = str(auth_payload.get("credential_id") or "").strip()
        if _is_locally_revoked_chain(credential_id=credential_id, proof_id=None, root_grant_id=None):
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": "revoked_credential_local",
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 401

    if not used_proof and not lemma_credential and token:
        if expected_mode == MODE_PROOF_REQUIRED:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": "AUTH_PROOF_REQUIRED",
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 403
        valid, auth_payload = _validate_agent_token(token)
        if not valid:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": auth_payload.get("error", "invalid_agent_token"),
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 401

    if not auth_payload:
        _LOCAL_OPS_COUNTERS["deny"] += 1
        return {
            "allowed": False,
            "error": "missing_auth",
            "decision_id": decision_id,
            "action": action,
            "risk": risk_tier,
        }, 401

    # Passkey step-up for critical local ops
    if REQUIRE_FRESH_PASSKEY_STEPUP and risk_tier in STEPUP_REQUIRED_TIERS:
        stepup_marker = str(request.headers.get("X-Lemma-Step-Up") or "").strip().lower()
        if stepup_marker != "fresh_passkey":
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": "AUTH_RISK_STEP_UP_REQUIRED",
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
                "message": "Fresh passkey step-up required for this risk tier.",
            }, 403

    # Passkey age enforcement
    if PASSKEY_AGE_ENFORCEMENT_ENABLED:
        passkey_ts_raw = auth_payload.get("passkey_verified_at")
        if passkey_ts_raw is not None:
            try:
                passkey_ts = int(passkey_ts_raw)
            except (TypeError, ValueError):
                passkey_ts = 0
            if risk_tier == "critical":
                max_age = PASSKEY_MAX_AGE_CRITICAL
            elif risk_tier == "high":
                max_age = PASSKEY_MAX_AGE_HIGH
            else:
                max_age = PASSKEY_MAX_AGE_LOW
            age_seconds = now_ts - passkey_ts
            if age_seconds > max_age:
                _LOCAL_OPS_COUNTERS["deny"] += 1
                return {
                    "allowed": False,
                    "error": "passkey_age_exceeded",
                    "decision_id": decision_id,
                    "action": action,
                    "risk": risk_tier,
                    "passkey_age_seconds": age_seconds,
                    "max_age_seconds": max_age,
                }, 403

    # Runtime kill switch check
    runtime_state = _runtime_state_cached(runtime_id=runtime_id, auth_payload=auth_payload)
    if runtime_state and not bool(runtime_state.get("active")):
        _LOCAL_OPS_COUNTERS["deny"] += 1
        return {
            "allowed": False,
            "error": "runtime_inactive_local",
            "decision_id": decision_id,
            "action": action,
            "risk": risk_tier,
            "runtime_id": runtime_id,
        }, 403

    required_online = risk_tier in RUNTIME_AUTHORIZE_REQUIRED_TIERS
    stale_for_risk = _revocation_stale_for_risk(risk_tier)
    should_online_check = required_online or (stale_for_risk and ONLINE_CHECK_ON_STALE_NONCRITICAL)
    if should_online_check:
        if not lemma_credential:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": "runtime_authorize_requires_credential",
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
            }, 403
        runtime_ok, runtime_payload = _runtime_active_for_credential_cached(
            lemma_credential,
            runtime_id,
            action=action,
            resource=str(resource or "/"),
            risk=risk_tier,
            force_refresh=stale_for_risk or required_online,
        )
        if not runtime_ok:
            runtime_error = str((runtime_payload or {}).get("error") or "")
            if runtime_error in {"runtime_inactive", "runtime_killed"}:
                _runtime_state_update(
                    runtime_id=runtime_id,
                    auth_payload=auth_payload,
                    active=False,
                    source="local_ops_runtime_authorize",
                )
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": runtime_payload.get("error", "runtime_not_authorized"),
                "decision_id": decision_id,
                "action": action,
                "risk": risk_tier,
                "runtime_id": runtime_id,
            }, 403
        _runtime_state_update(
            runtime_id=runtime_id,
            auth_payload=auth_payload,
            active=True,
            source="local_ops_runtime_authorize",
        )

    # Scope check
    if not _scope_allowed(required_scope, auth_payload):
        _LOCAL_OPS_COUNTERS["deny"] += 1
        _bump_taint_on_violation(runtime_id)
        return {
            "allowed": False,
            "error": "insufficient_scope",
            "decision_id": decision_id,
            "action": action,
            "risk": risk_tier,
            "required_scope": required_scope,
        }, 403

    # Action taxonomy + path bound check (use widened session map if present)
    actions_map = _SESSION_ACTIONS_MAP if _SESSION_ACTIONS_MAP is not None else auth_payload.get("actions")
    if actions_map and isinstance(actions_map, dict):
        action_ok, action_reason = check_action_granted(actions_map, action, resource or None)
        if not action_ok:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            _bump_taint_on_violation(runtime_id)
            return {
                "allowed": False,
                "error": "action_not_granted",
                "decision_id": decision_id,
                "action": action,
                "reason": action_reason,
                "resource": resource,
                "risk": risk_tier,
            }, 403

    # Taint epoch enforcement
    if TAINT_ENFORCEMENT_ENABLED:
        runtime_taint = _get_runtime_taint_epoch(runtime_id)
        proof_taint_raw = auth_payload.get("taint_epoch")
        if runtime_taint is not None and runtime_taint > 0 and proof_taint_raw is not None:
            proof_taint = int(proof_taint_raw)
            if proof_taint < runtime_taint:
                _LOCAL_OPS_COUNTERS["deny"] += 1
                return {
                    "allowed": False,
                    "error": "proof_taint_epoch_stale",
                    "decision_id": decision_id,
                    "action": action,
                    "risk": risk_tier,
                    "proof_taint_epoch": proof_taint,
                    "runtime_taint_epoch": runtime_taint,
                    "runtime_id": runtime_id,
                }, 403

    # Tap-to-approve gate
    if _action_requires_approval(action):
        pending_body = {
            "allowed": "pending",
            "decision_id": decision_id,
            "action": action,
            "resource": resource,
            "risk": risk_tier,
            "required_scope": required_scope,
            "runtime_id": runtime_id,
        }
        _publish_decision(pending_body)
        _log_local_decision(pending_body)
        evt = threading.Event()
        _PENDING_APPROVALS[decision_id] = evt
        approved = evt.wait(timeout=APPROVAL_TIMEOUT_SECONDS)
        _PENDING_APPROVALS.pop(decision_id, None)
        result = _APPROVAL_RESULTS.pop(decision_id, False)
        if not approved or not result:
            _LOCAL_OPS_COUNTERS["deny"] += 1
            return {
                "allowed": False,
                "error": "approval_timeout" if not approved else "approval_denied",
                "decision_id": decision_id,
                "action": action,
                "resource": resource,
                "risk": risk_tier,
            }, 403

    _LOCAL_OPS_COUNTERS["allow"] += 1

    # Auto-bump taint epoch when agent declares it is ingesting untrusted content.
    # The action is allowed (agent needs to read), but authority for privileged
    # actions is invalidated until a fresh proof is obtained.
    taint_bumped = False
    if TAINT_ENFORCEMENT_ENABLED and action in {
        "ingest.external", "ingest.user_content",
    }:
        with _SYNC_LOCK:
            prev = _RUNTIME_TAINT_CACHE.get(runtime_id, 0)
            _RUNTIME_TAINT_CACHE[runtime_id] = prev + 1
        taint_bumped = True
        _log_local_decision({
            "event": "taint_epoch_bumped",
            "trigger": "ingest_action",
            "action": action,
            "resource": resource,
            "previous_epoch": prev,
            "new_epoch": prev + 1,
            "runtime_id": runtime_id,
        })

    result = {
        "allowed": True,
        "decision_id": decision_id,
        "action": action,
        "resource": resource,
        "risk": risk_tier,
        "required_scope": required_scope,
        "runtime_id": runtime_id,
    }
    if taint_bumped:
        result["taint_epoch_bumped"] = True
        result["new_taint_epoch"] = prev + 1
    return result, 200


def _log_local_ops_decision(
    decision_body: dict,
    lemma_credential: str,
    token: str,
    runtime_id: str,
) -> None:
    """Best-effort log of a local ops decision to the platform monitor."""
    if not LOCAL_OPS_LOG_DECISIONS:
        return
    try:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if lemma_credential:
            headers["X-Lemma-Credential"] = lemma_credential
        elif token:
            headers["X-Agent-Token"] = token
        HTTP.post(
            f"{LEMMA_BASE_URL}/api/agent/monitor/log-external",
            headers=headers,
            json={
                "action": decision_body.get("action", "local_ops"),
                "resource": decision_body.get("resource", ""),
                "event_type": "local_ops_decision",
                "decision_id": decision_body.get("decision_id"),
                "allowed": bool(decision_body.get("allowed")),
                "risk_tier": decision_body.get("risk", ""),
                "error": decision_body.get("error"),
                "runtime_id": runtime_id,
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except Exception:
        pass


@APP.route("/aim/authorize", methods=["POST"])
def local_ops_authorize():
    """Authorize a local agent action against the credential's action taxonomy.

    The agent runtime calls this endpoint before performing any local action
    (file read/write, shell exec, DB query, etc.).  The daemon applies the
    full enforcement pipeline -- credential verification, scope, action
    taxonomy, path bounds, revocation, runtime kill switch, taint epoch --
    and returns an allow/deny decision the runtime can enforce.

    Request body:
        {
            "action":   "file.write",          // action taxonomy key (required)
            "resource": "/src/main.py",        // target path or identifier
            "risk":     "high",                // optional risk tier override
            "metadata": { ... }                // optional context (logged only)
        }

    Response:
        {
            "allowed":       true|false,
            "decision_id":   "lop_...",
            "action":        "file.write",
            "resource":      "/src/main.py",
            "risk":          "high",
            "required_scope":"write",
            "runtime_id":    "...",
            "error":         "..." // only on deny
        }
    """
    if not LOCAL_OPS_GATE_ENABLED:
        return jsonify({"allowed": True, "reason": "local_ops_gate_disabled"}), 200

    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip()
    resource = str(body.get("resource") or "").strip()
    risk_override = str(body.get("risk") or "").strip() or None
    op_metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else None

    decision_body, status_code = _authorize_local_op(
        action=action,
        resource=resource,
        risk_override=risk_override,
        metadata=op_metadata,
    )

    _log_local_decision(decision_body)
    _publish_decision(decision_body)

    _log_local_ops_decision(
        decision_body,
        _lemma_credential_from_request(),
        _token_from_request(),
        _runtime_id_from_request(),
    )

    return jsonify(decision_body), status_code


@APP.route("/aim/authorize/batch", methods=["POST"])
def local_ops_authorize_batch():
    """Authorize multiple local actions in a single round-trip.

    Request body:
        {
            "operations": [
                { "action": "file.read", "resource": "/src/main.py" },
                { "action": "shell.exec", "resource": "npm test" },
                ...
            ]
        }

    Response:
        {
            "results": [
                { "allowed": true, "decision_id": "lop_...", ... },
                { "allowed": false, "error": "action_not_granted", ... }
            ],
            "all_allowed": false
        }
    """
    if not LOCAL_OPS_GATE_ENABLED:
        return jsonify({"results": [], "all_allowed": True, "reason": "local_ops_gate_disabled"}), 200

    body = request.get_json(silent=True) or {}
    operations = body.get("operations") if isinstance(body.get("operations"), list) else []
    if not operations:
        return jsonify({"results": [], "all_allowed": True, "error": "no_operations"}), 400

    max_batch = 50
    if len(operations) > max_batch:
        return jsonify({"results": [], "all_allowed": False, "error": f"batch_limit_exceeded (max {max_batch})"}), 400

    results = []
    all_allowed = True
    credential = _lemma_credential_from_request()
    token = _token_from_request()
    runtime_id = _runtime_id_from_request()

    for op in operations:
        if not isinstance(op, dict):
            results.append({"allowed": False, "error": "invalid_operation_entry"})
            all_allowed = False
            continue
        action = str(op.get("action") or "").strip()
        resource = str(op.get("resource") or "").strip()
        risk_override = str(op.get("risk") or "").strip() or None

        decision_body, _ = _authorize_local_op(
            action=action,
            resource=resource,
            risk_override=risk_override,
        )
        results.append(decision_body)
        if not decision_body.get("allowed"):
            all_allowed = False

        _log_local_decision(decision_body)
        _publish_decision(decision_body)
        _log_local_ops_decision(decision_body, credential, token, runtime_id)

    return jsonify({"results": results, "all_allowed": all_allowed}), 200


@APP.route("/", methods=["GET"])
def root():
    return jsonify(
        {
            "ok": True,
            "service": "lemma_firewall",
            "mode": "local_gateway",
            "message": (
                "This process is a local Lemma Firewall gateway that validates Lemma proofs "
                "and forwards allowed calls. Lemma.id remains the hosted control plane."
            ),
            "next": {
                "health": "/aim/health",
                "policy": "/aim/policy",
                "authorize": "/aim/authorize",
                "authorize_batch": "/aim/authorize/batch",
                "forward_pattern": "/firewall/<api_id>/<path>",
            },
            "runtime_id": DEFAULT_RUNTIME_ID,
            "local_ops_gate": LOCAL_OPS_GATE_ENABLED,
        }
    )


@APP.route("/aim/policy", methods=["GET"])
def policy():
    return jsonify(
        {
            "success": True,
            "apis": {
                api_id: {
                    "base_url": p.base_url,
                    "allowed_methods": sorted(p.allowed_methods),
                    "path_prefixes": p.path_prefixes,
                    "required_scope": p.required_scope,
                    "risk_tier": p.risk_tier,
                }
                for api_id, p in POLICIES.items()
            },
        }
    )


@APP.route("/firewall/<api_id>/<path:upstream_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def firewall(api_id: str, upstream_path: str):
    _ensure_sync_thread_started()
    policy = POLICIES.get(api_id)
    if not policy:
        _log_proxy_decision(api_id, upstream_path, request.method.upper(), False, error="unknown_api_id")
        return jsonify({"success": False, "error": "unknown_api_id"}), 404

    method = request.method.upper()
    if method not in policy.allowed_methods:
        _log_proxy_decision(api_id, upstream_path, method, False, error="method_not_allowed")
        return jsonify({"success": False, "error": "method_not_allowed"}), 403

    if not _path_allowed("/" + upstream_path.lstrip("/"), policy.path_prefixes):
        _log_proxy_decision(api_id, upstream_path, method, False, error="path_not_allowed")
        return jsonify({"success": False, "error": "path_not_allowed"}), 403

    lemma_credential = _lemma_credential_from_request()
    lemma_proof = _lemma_proof_from_request()
    token = _token_from_request()
    runtime_id = _runtime_id_from_request()
    expected_mode = _expected_mode_for_risk(policy.risk_tier)
    mode_decision = evaluate_mode_policy(expected_mode=expected_mode, headers=request.headers)
    if not mode_decision.allowed:
        _log_proxy_decision(api_id, upstream_path, method, False, error=mode_decision.reason_code or "auth_mode_denied")
        return jsonify({"success": False, "error": mode_decision.reason_code or "auth_mode_denied"}), 403

    if (
        expected_mode == MODE_PROOF_REQUIRED
        and not mode_decision.proof_present
        and str(os.environ.get("LEMMA_ENFORCE_PROOF_REQUIRED", "0") or "0").strip().lower()
        in {"1", "true", "yes", "on"}
    ):
        _log_proxy_decision(api_id, upstream_path, method, False, error="AUTH_PROOF_REQUIRED")
        return jsonify({"success": False, "error": "AUTH_PROOF_REQUIRED"}), 403

    auth_payload = {}
    used_proof = False
    if mode_decision.proof_present:
        proof_payload = _decode_json_object(lemma_proof)
        with _SYNC_LOCK:
            revoked_proof_ids = set(_SYNC_STATE.get("revoked_proof_ids") or set())
            revoked_root_grant_ids = set(_SYNC_STATE.get("revoked_root_grant_ids") or set())
            min_revocation_epoch = int(_SYNC_STATE.get("min_revocation_epoch") or 0)
        proof_eval = evaluate_proof_native(
            headers=request.headers,
            method=method,
            path="/" + upstream_path.lstrip("/"),
            required_scope=policy.required_scope,
            base_url=LEMMA_BASE_URL,
            revoked_proof_ids=revoked_proof_ids,
            revoked_root_grant_ids=revoked_root_grant_ids,
            min_revocation_epoch=min_revocation_epoch,
        )
        if not proof_eval.allowed:
            _log_proxy_decision(api_id, upstream_path, method, False, error=proof_eval.reason_code or "AUTH_CHAIN_BROKEN")
            return jsonify({"success": False, "error": proof_eval.reason_code or "AUTH_CHAIN_BROKEN"}), 403
        pop_eval = validate_pop_replay(
            headers=request.headers,
            method=method,
            path="/" + upstream_path.lstrip("/"),
            body_bytes=request.get_data(cache=True),
            required=True,
            require_signature=True,
        )
        if not pop_eval.valid:
            _log_proxy_decision(api_id, upstream_path, method, False, error=pop_eval.code or "AUTH_PROOF_OF_POSSESSION_FAILED")
            return jsonify({"success": False, "error": pop_eval.code or "AUTH_PROOF_OF_POSSESSION_FAILED"}), 403
        auth_payload = {
            "scope": _scope_from_proof_payload(proof_payload),
            "proof_id": proof_eval.proof_id,
            "root_grant_id": proof_eval.root_grant_id,
            "policy_version": proof_eval.policy_version,
            "auth_mode": "proof_native",
            "ppid": str(
                (proof_payload.get("delegated_proof") or {}).get("acting_for_ppid")
                or (proof_payload.get("root_proof") or {}).get("subject_ppid")
                or ""
            ).strip()
            or None,
        }
        if _is_locally_revoked_chain(
            credential_id=None,
            proof_id=proof_eval.proof_id,
            root_grant_id=proof_eval.root_grant_id,
            ancestor_ids=(
                (proof_payload.get("delegated_proof") or {}).get("ancestor_ids")
                if isinstance((proof_payload.get("delegated_proof") or {}).get("ancestor_ids"), list)
                else []
            ),
        ):
            _log_proxy_decision(api_id, upstream_path, method, False, error="revoked_proof_chain_local")
            return jsonify({"success": False, "error": "revoked_proof_chain_local"}), 401
        used_proof = True

    if not used_proof and lemma_credential:
        valid, auth_payload = _validate_lemma_credential(lemma_credential)
        if not valid:
            _log_proxy_decision(api_id, upstream_path, method, False, error=auth_payload.get("error", "invalid_lemma_credential"))
            return jsonify({"success": False, "error": auth_payload.get("error", "invalid_lemma_credential")}), 401
        credential_id = str(auth_payload.get("credential_id") or "").strip()
        if _is_locally_revoked_chain(credential_id=credential_id, proof_id=None, root_grant_id=None):
            _log_proxy_decision(api_id, upstream_path, method, False, error="revoked_credential_local")
            return jsonify({"success": False, "error": "revoked_credential_local"}), 401

    if not used_proof and not lemma_credential and token:
        if expected_mode == MODE_PROOF_REQUIRED:
            _log_proxy_decision(api_id, upstream_path, method, False, error="AUTH_PROOF_REQUIRED")
            return jsonify({"success": False, "error": "AUTH_PROOF_REQUIRED"}), 403
        valid, auth_payload = _validate_agent_token(token)
        if not valid:
            _log_proxy_decision(api_id, upstream_path, method, False, error=auth_payload.get("error", "invalid_agent_token"))
            return jsonify({"success": False, "error": auth_payload.get("error", "invalid_agent_token")}), 401

    if not auth_payload:
        _log_proxy_decision(api_id, upstream_path, method, False, error="missing_auth")
        return jsonify({"success": False, "error": "missing_auth"}), 401

    if REQUIRE_FRESH_PASSKEY_STEPUP and str(policy.risk_tier or "low").strip().lower() in STEPUP_REQUIRED_TIERS:
        stepup_marker = str(request.headers.get("X-Lemma-Step-Up") or "").strip().lower()
        if stepup_marker != "fresh_passkey":
            _log_proxy_decision(api_id, upstream_path, method, False, error="AUTH_RISK_STEP_UP_REQUIRED")
            return jsonify(
                {
                    "success": False,
                    "error": "AUTH_RISK_STEP_UP_REQUIRED",
                    "message": "Fresh passkey step-up required for this risk tier.",
                }
            ), 403

    if PASSKEY_AGE_ENFORCEMENT_ENABLED:
        passkey_ts_raw = auth_payload.get("passkey_verified_at")
        if passkey_ts_raw is not None:
            try:
                passkey_ts = int(passkey_ts_raw)
            except (TypeError, ValueError):
                passkey_ts = 0
            tier = str(policy.risk_tier or "low").strip().lower()
            if tier == "critical":
                max_age = PASSKEY_MAX_AGE_CRITICAL
            elif tier == "high":
                max_age = PASSKEY_MAX_AGE_HIGH
            else:
                max_age = PASSKEY_MAX_AGE_LOW
            age_seconds = int(time.time()) - passkey_ts
            if age_seconds > max_age:
                _log_proxy_decision(api_id, upstream_path, method, False, error="passkey_age_exceeded")
                return jsonify(
                    {
                        "success": False,
                        "error": "passkey_age_exceeded",
                        "risk_tier": tier,
                        "passkey_age_seconds": age_seconds,
                        "max_age_seconds": max_age,
                        "message": f"Passkey re-authentication required. Last verified {age_seconds}s ago, max for {tier} tier is {max_age}s.",
                    }
                ), 403

    required_online = str(policy.risk_tier or "low").strip().lower() in RUNTIME_AUTHORIZE_REQUIRED_TIERS
    action_type = _resolve_action_type(policy, method)
    action_resource = "/" + upstream_path.lstrip("/")
    risk_tier = str(policy.risk_tier or "low").strip().lower()
    stale_for_risk = _revocation_stale_for_risk(policy.risk_tier)
    runtime_state = _runtime_state_cached(runtime_id=runtime_id, auth_payload=auth_payload)
    if runtime_state and not bool(runtime_state.get("active")):
        _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error="runtime_inactive_local")
        return jsonify(
            {
                "success": False,
                "error": "runtime_inactive_local",
                "runtime_id": runtime_id,
                "runtime_check": {"source": runtime_state.get("source"), "active": False},
            }
        ), 403

    should_online_check = required_online or (stale_for_risk and ONLINE_CHECK_ON_STALE_NONCRITICAL)
    if should_online_check:
        if not lemma_credential:
            _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error="runtime_authorize_requires_credential")
            return jsonify({"success": False, "error": "runtime_authorize_requires_credential"}), 403
        runtime_ok, runtime_payload = _runtime_active_for_credential_cached(
            lemma_credential,
            runtime_id,
            action=action_type,
            resource=action_resource,
            risk=risk_tier,
            force_refresh=stale_for_risk or required_online,
        )
        if not runtime_ok:
            runtime_error = str((runtime_payload or {}).get("error") or "")
            if runtime_error in {"runtime_inactive", "runtime_killed"}:
                _runtime_state_update(runtime_id=runtime_id, auth_payload=auth_payload, active=False, source="online_runtime_authorize")
            _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error=runtime_payload.get("error", "runtime_not_authorized"))
            return (
                jsonify(
                    {
                        "success": False,
                        "error": runtime_payload.get("error", "runtime_not_authorized"),
                        "runtime_id": runtime_id,
                        "runtime_check": runtime_payload,
                        "online_check_reason": "stale_freshness" if stale_for_risk else "risk_tier_required",
                    }
                ),
                403,
            )
        _runtime_state_update(runtime_id=runtime_id, auth_payload=auth_payload, active=True, source="online_runtime_authorize")

    if not _scope_allowed(policy.required_scope, auth_payload):
        _bump_taint_on_violation(runtime_id)
        _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error="insufficient_scope")
        return jsonify(
            {
                "success": False,
                "error": "insufficient_scope",
                "required_scope": policy.required_scope,
            }
        ), 403

    actions_map = auth_payload.get("actions")
    if actions_map and isinstance(actions_map, dict):
        from api.action_taxonomy import check_action_granted
        action_ok, action_reason = check_action_granted(actions_map, action_type, action_resource)
        if not action_ok:
            _bump_taint_on_violation(runtime_id)
            _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error="action_not_granted")
            return jsonify(
                {
                    "success": False,
                    "error": "action_not_granted",
                    "action": action_type,
                    "reason": action_reason,
                    "resource": action_resource,
                }
            ), 403

    if TAINT_ENFORCEMENT_ENABLED:
        runtime_taint = _get_runtime_taint_epoch(runtime_id)
        proof_taint_raw = auth_payload.get("taint_epoch")
        if runtime_taint is not None and runtime_taint > 0 and proof_taint_raw is not None:
            proof_taint = int(proof_taint_raw)
            if proof_taint < runtime_taint:
                _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error="proof_taint_epoch_stale")
                return jsonify(
                    {
                        "success": False,
                        "error": "proof_taint_epoch_stale",
                        "proof_taint_epoch": proof_taint,
                        "runtime_taint_epoch": runtime_taint,
                        "runtime_id": runtime_id,
                    }
                ), 403

    upstream_url = urljoin(policy.base_url + "/", upstream_path.lstrip("/"))
    forward_headers = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in {"host", "content-length"}:
            continue
        if lower in policy.forward_headers:
            forward_headers[key] = value

    try:
        upstream_response = HTTP.request(
            method=method,
            url=upstream_url,
            params=request.args,
            headers=forward_headers,
            data=request.get_data(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except Exception as exc:
        _log_external_activity(token, lemma_credential, policy, upstream_path, 502, False, runtime_id)
        _log_proxy_decision(api_id, upstream_path, method, False, action=action_type, error=f"upstream_unreachable: {exc}")
        return jsonify({"success": False, "error": f"upstream_unreachable: {exc}"}), 502

    _log_external_activity(
        token,
        lemma_credential,
        policy,
        upstream_path,
        int(upstream_response.status_code),
        bool(upstream_response.status_code < 400),
        runtime_id,
    )
    _log_proxy_decision(api_id, upstream_path, method, True, action=action_type, upstream_status=int(upstream_response.status_code))

    if policy.taint_on_response and TAINT_ENFORCEMENT_ENABLED and upstream_response.status_code < 400:
        with _SYNC_LOCK:
            prev = _RUNTIME_TAINT_CACHE.get(runtime_id, 0)
            _RUNTIME_TAINT_CACHE[runtime_id] = prev + 1
        _log_local_decision({
            "event": "taint_epoch_bumped",
            "trigger": "external_content_ingestion",
            "api_id": api_id,
            "resource": f"/firewall/{api_id}/{upstream_path}",
            "previous_epoch": prev,
            "new_epoch": prev + 1,
            "runtime_id": runtime_id,
        })

    passthrough_headers = {
        k: v
        for k, v in upstream_response.headers.items()
        if k.lower() in {"content-type", "cache-control", "etag", "last-modified"}
    }
    return Response(
        response=upstream_response.content,
        status=upstream_response.status_code,
        headers=passthrough_headers,
    )


@APP.route("/aim/decisions/stream")
def decisions_stream():
    """SSE endpoint streaming live authorization decisions."""
    def _generate():
        q: queue.Queue = queue.Queue()
        _DECISION_SUBSCRIBERS.append(q)
        try:
            for item in list(_DECISION_RING):
                yield f"data: {json.dumps(item)}\n\n"
            while True:
                try:
                    item = q.get(timeout=30)
                    yield f"data: {json.dumps(item)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            try:
                _DECISION_SUBSCRIBERS.remove(q)
            except ValueError:
                pass

    return Response(_generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lemma AIM Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0d1117;color:#c9d1d9}
.bar{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;background:#161b22;border-bottom:1px solid #30363d}
.bar h1{font-size:16px;color:#58a6ff}
.bar .meta{font-size:12px;color:#8b949e}
.actions{padding:8px 20px;display:flex;gap:8px}
button{padding:6px 14px;border:1px solid #30363d;border-radius:6px;background:#21262d;color:#c9d1d9;cursor:pointer;font-size:13px}
button:hover{background:#30363d}
button.danger{border-color:#f85149;color:#f85149}
button.danger:hover{background:#f8514922}
#tbl{width:100%;border-collapse:collapse;margin-top:4px}
#tbl th{text-align:left;padding:8px 12px;font-size:12px;color:#8b949e;border-bottom:1px solid #21262d;position:sticky;top:0;background:#0d1117}
#tbl td{padding:6px 12px;font-size:13px;border-bottom:1px solid #161b22}
tr.allow td:first-child{color:#3fb950}
tr.deny td:first-child{color:#f85149}
tr.pending td:first-child{color:#d29922}
.cnt{padding:0 20px;overflow-y:auto;max-height:calc(100vh - 120px)}
</style></head><body>
<div class="bar"><h1>Lemma AIM &mdash; Live Dashboard</h1><div class="meta" id="meta">connecting&hellip;</div></div>
<div class="actions">
<button onclick="killSession()" class="danger">Kill Session</button>
</div>
<div class="cnt"><table id="tbl"><thead><tr><th>Result</th><th>Action</th><th>Resource</th><th>Risk</th><th>Decision ID</th><th>Time</th><th></th></tr></thead><tbody id="rows"></tbody></table></div>
<script>
let paused=false,count=0;
const rows=document.getElementById("rows"),meta=document.getElementById("meta");
const es=new EventSource("/aim/decisions/stream");
es.onmessage=function(e){
  if(paused)return;
  const d=JSON.parse(e.data);count++;
  meta.textContent=count+" decisions";
  const tr=document.createElement("tr");
  const res=d.allowed===true?"allow":d.allowed==="pending"?"pending":"deny";
  tr.className=res;
  const t=d.timestamp?new Date(d.timestamp*1000).toLocaleTimeString():"";
  let btns="";
  if(res==="deny")btns=`<button onclick="widenScope('${d.action}','${d.resource||""}')">Widen</button>`;
  if(res==="pending")btns=`<button onclick="approve('${d.decision_id}')">Approve</button>`;
  tr.innerHTML=`<td>${res.toUpperCase()}</td><td>${d.action||""}</td><td>${d.resource||""}</td><td>${d.risk||""}</td><td style="font-size:11px">${d.decision_id||""}</td><td>${t}</td><td>${btns}</td>`;
  rows.prepend(tr);
};
es.onerror=function(){meta.textContent="disconnected";};
function approve(id){fetch("/aim/approve/"+id,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({approved:true})}).then(r=>r.json()).then(d=>console.log("approve",d));}
function widenScope(action,resource){
  const acts={};acts[action]=resource?{paths:[resource,"**"]}:true;
  fetch("/aim/widen-scope",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({actions:acts})}).then(r=>r.json()).then(d=>console.log("widen",d));
}
function killSession(){if(confirm("Kill active session?")){fetch("/aim/revoke",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({credential_id:"*"})}).then(()=>meta.textContent="SESSION KILLED");}}
</script></body></html>"""


@APP.route("/aim/dashboard")
def dashboard():
    return Response(_DASHBOARD_HTML, mimetype="text/html")


@APP.route("/aim/widen-scope", methods=["POST"])
def widen_scope():
    """Dynamically expand the session's scope and action map."""
    global _SESSION_ACTIONS_MAP, _SESSION_SCOPE_OVERRIDE
    body = request.get_json(silent=True) or {}
    new_actions = body.get("actions")
    new_scope = body.get("scope")
    if (not new_actions or not isinstance(new_actions, dict)) and not new_scope:
        return jsonify({"success": False, "error": "actions_or_scope_required"}), 400
    if not new_actions:
        new_actions = {}
    if new_scope:
        if isinstance(new_scope, str):
            new_scope = [s.strip() for s in new_scope.split(",") if s.strip()]
        if _SESSION_SCOPE_OVERRIDE is None:
            _SESSION_SCOPE_OVERRIDE = set()
        for s in new_scope:
            _SESSION_SCOPE_OVERRIDE.add(s.strip().lower())

    if _SESSION_ACTIONS_MAP is None:
        credential_raw = DEFAULT_LEMMA_CREDENTIAL
        if not credential_raw and DEFAULT_LEMMA_CREDENTIAL_FILE and Path(DEFAULT_LEMMA_CREDENTIAL_FILE).exists():
            credential_raw = Path(DEFAULT_LEMMA_CREDENTIAL_FILE).read_text(encoding="utf-8").strip()
        base_actions = {}
        if credential_raw:
            try:
                cred = json.loads(credential_raw) if isinstance(credential_raw, str) else credential_raw
                base_actions = (cred.get("claims") or {}).get("actions") or {}
            except Exception:
                pass
        _SESSION_ACTIONS_MAP = dict(base_actions)

    for action_key, grant in new_actions.items():
        existing = _SESSION_ACTIONS_MAP.get(action_key)
        if existing is None:
            _SESSION_ACTIONS_MAP[action_key] = grant
        elif isinstance(existing, dict) and isinstance(grant, dict):
            existing_paths = list(existing.get("paths") or [])
            new_paths = list(grant.get("paths") or [])
            merged_paths = list(set(existing_paths + new_paths))
            _SESSION_ACTIONS_MAP[action_key] = {"paths": merged_paths}
        else:
            _SESSION_ACTIONS_MAP[action_key] = grant

    # Reset taint epoch for the runtime since the operator explicitly widened scope
    with _SYNC_LOCK:
        _RUNTIME_TAINT_CACHE[DEFAULT_RUNTIME_ID] = 0

    _publish_decision({
        "event": "scope_widened",
        "new_actions": new_actions,
        "session_actions_count": len(_SESSION_ACTIONS_MAP),
        "taint_epoch_reset": True,
    })

    return jsonify({
        "success": True,
        "session_actions": _SESSION_ACTIONS_MAP,
    })


@APP.route("/aim/approve/<decision_id>", methods=["POST"])
def approve_decision(decision_id: str):
    """Approve (or deny) a pending tap-to-approve decision."""
    body = request.get_json(silent=True) or {}
    approved = bool(body.get("approved", True))
    evt = _PENDING_APPROVALS.get(decision_id)
    if not evt:
        return jsonify({"success": False, "error": "decision_not_found_or_expired"}), 404
    _APPROVAL_RESULTS[decision_id] = approved
    evt.set()
    return jsonify({"success": True, "decision_id": decision_id, "approved": approved})


if __name__ == "__main__":
    _ensure_sync_thread_started()
    host = os.environ.get("LEMMA_FIREWALL_HOST", "127.0.0.1")
    port = int(os.environ.get("LEMMA_FIREWALL_PORT", "8787"))
    print(
        f"[Lemma Firewall] local gateway listening on http://{host}:{port} "
        f"(control plane: {LEMMA_BASE_URL})"
    )
    APP.run(host=host, port=port, debug=False)
