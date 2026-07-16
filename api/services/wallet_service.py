"""
Consolidated Wallet Service
===========================

Combines all wallet functionality from 8 separate files into a single organized service:
- wallet_first_auth.py → WalletAuthService
- wallet_session_sync.py → WalletSessionService  
- wallet_retrieval_flow.py → WalletRetrievalService
- wallet_revocation.py → WalletRevocationService
- wallet_transfer_session.py → WalletTransferService
- wallet_pin_reset.py → WalletPINService
- wallet_auth_decorator.py → Auth decorators
- multi_lemma_wallet_sync.py → MultiLemmaSyncService

All routes maintain backwards compatibility with existing URL patterns.
"""

import os
import json
import csv
import time
import secrets
import logging
import hashlib
import hmac
import uuid
import threading
import base64
import io
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from urllib.parse import urlparse
from urllib import request as urllib_request

from flask import Blueprint, request, jsonify, session, make_response, g
from api.agent_ops_store import (
    ensure_agent_ops_schema,
    get_decision as get_agent_ops_decision,
    get_runtime as get_agent_ops_runtime,
    kill_runtime as kill_agent_ops_runtime,
    list_policy_profiles as list_agent_ops_policy_profiles,
    list_decisions as list_agent_ops_decisions,
    list_runtimes as list_agent_ops_runtimes,
    publish_policy_profile as publish_agent_ops_policy_profile,
    record_decision_logs as record_agent_ops_decision_logs,
    rollback_policy_profile as rollback_agent_ops_policy_profile,
    upsert_policy_profile as upsert_agent_ops_policy_profile,
    upsert_runtime as upsert_agent_ops_runtime,
    upsert_runtime_org_controls as upsert_agent_ops_org_controls,
)

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - Import from centralized session manager
# ============================================================================

from auth.session_manager import (
    SESSION_COOKIE_NAME,
    SESSION_DURATION,
    CSRF_COOKIE_NAME,
    validate_session_token,
    validate_unlock_token,
    generate_session_token,
    generate_csrf_token,
    get_session_expiry,
    get_current_time_ms,
)

TOKEN_EXPIRY = 86400  # 24 hours for PIN reset

# CORS configuration from environment
_ALLOWED_ORIGINS = {
    origin.strip().lower()
    for origin in os.environ.get('LEMMA_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
}
_ALLOWED_ORIGIN_SUFFIXES = [
    suffix.strip().lower()
    for suffix in os.environ.get('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '').split(',')
    if suffix.strip()
]
_ALLOW_DEV_ORIGINS = os.environ.get('LEMMA_ALLOW_DEV_ORIGINS', '1') != '0'

# Redis setup for multi-dyno support (shared factory)
try:
    from api.redis_client import get_shared_redis

    redis_client = get_shared_redis(prefer_cloud=True, decode_responses=True)
    USE_REDIS = redis_client is not None
    if USE_REDIS:
        logger.info("Redis connected for wallet session storage")
    else:
        logger.warning("Redis not available for wallet session storage")
except Exception as e:
    redis_client = None
    USE_REDIS = False
    logger.warning(f"Redis not available: {e}")

# Multi-lemma engine availability
try:
    from lemma_crypto import PyQRSyncManager, PyDeviceDelegationManager, PyMinimalIssuer
    MULTI_LEMMA_AVAILABLE = True
except ImportError:
    MULTI_LEMMA_AVAILABLE = False

# Create unified blueprint
wallet_service_bp = Blueprint('wallet_service', __name__)


# ============================================================================
# CORS HELPERS
# ============================================================================

def _parse_origin(origin: str) -> str | None:
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc:
            return None
        return origin.lower()
    except Exception:
        return None


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    normalized = _parse_origin(origin)
    if not normalized:
        return False
    if normalized in _ALLOWED_ORIGINS:
        return True
    hostname = urlparse(normalized).hostname or ''
    if hostname:
        for suffix in _ALLOWED_ORIGIN_SUFFIXES:
            if hostname.endswith(suffix.lstrip('.')):
                return True
    if _ALLOW_DEV_ORIGINS and hostname in {'localhost', '127.0.0.1'}:
        return True
    return False


def _cors_headers(origin: str | None) -> dict:
    if not _origin_allowed(origin):
        return {'Referrer-Policy': 'no-referrer'}
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Lemma-CSRF',
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin',
        'Referrer-Policy': 'no-referrer',
    }


def _validate_csrf() -> bool:
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get('X-Lemma-CSRF')
    if not csrf_cookie or not csrf_header:
        return False
    return secrets.compare_digest(csrf_cookie, csrf_header)


def cross_origin_response(data: dict, status: int = 200):
    """Create a response with proper CORS headers."""
    origin = request.headers.get('Origin')
    response = jsonify(data)
    response.headers.update(_cors_headers(origin))
    return response, status


# ============================================================================
# SESSION TOKEN MANAGEMENT - Imported from auth.session_manager
# ============================================================================
# generate_session_token, validate_session_token, etc. are now imported from
# auth.session_manager to centralize session logic and avoid duplication.


# ============================================================================
# SESSION STORAGE (Redis or In-Memory)
# ============================================================================

class SessionStorage:
    """Multi-dyno compatible session storage."""
    
    def __init__(self):
        self.lock = threading.Lock()
        if not USE_REDIS:
            self.sessions = {}
    
    def set_session(self, session_id: str, session_data: dict, ttl: int = 300) -> bool:
        if USE_REDIS:
            try:
                redis_client.setex(f"transfer_session:{session_id}", ttl, json.dumps(session_data))
                return True
            except Exception as e:
                logger.error(f"Redis SET failed: {e}")
                return False
        else:
            with self.lock:
                self.sessions[session_id] = session_data
                return True
    
    def get_session(self, session_id: str) -> dict | None:
        if USE_REDIS:
            try:
                data = redis_client.get(f"transfer_session:{session_id}")
                return json.loads(data) if data else None
            except Exception as e:
                logger.error(f"Redis GET failed: {e}")
                return None
        else:
            with self.lock:
                return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        if USE_REDIS:
            try:
                redis_client.delete(f"transfer_session:{session_id}")
                return True
            except Exception:
                return False
        else:
            with self.lock:
                self.sessions.pop(session_id, None)
                return True
    
    def list_sessions(self) -> List[str]:
        if USE_REDIS:
            try:
                keys = redis_client.keys("transfer_session:*")
                return [key.replace("transfer_session:", "") for key in keys]
            except Exception:
                return []
        else:
            with self.lock:
                return list(self.sessions.keys())


_storage = SessionStorage()
_reset_tokens = {}  # PIN reset tokens


def _wallet_secure_mode_enabled() -> bool:
    raw = str(os.environ.get('LEMMA_WALLET_SECURE_MODE', '')).strip().lower()
    return raw in {'1', 'true', 'yes', 'on'}


def _wallet_transfer_max_payload_bytes() -> int:
    default_bytes = '131072' if _wallet_secure_mode_enabled() else '262144'
    raw = str(os.environ.get('LEMMA_WALLET_TRANSFER_MAX_BYTES') or default_bytes).strip()
    try:
        return max(16384, int(raw))
    except Exception:
        return int(default_bytes)


def _wallet_transfer_plaintext_allowed() -> bool:
    default_allowed = '0' if _wallet_secure_mode_enabled() else '1'
    raw = str(os.environ.get('LEMMA_WALLET_TRANSFER_PLAINTEXT_ALLOWED', default_allowed)).strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


LEGACY_WALLET_SECRET_REMOVED = {
    'success': False,
    'error': 'wallet_secret_not_accepted',
    'message': (
        'wallet_secret is no longer accepted by this endpoint; '
        'derive PPID client-side or use passkey_credential_id'
    ),
}


def _reject_wallet_secret_payload(data) -> tuple | None:
    """Return a 410 response tuple when legacy wallet_secret is supplied."""
    if isinstance(data, dict) and data.get('wallet_secret'):
        logger.warning("Rejected legacy wallet_secret payload on %s", request.path)
        return jsonify(LEGACY_WALLET_SECRET_REMOVED), 410
    return None


def _is_network_wide_credential(credential_type: str, credential_scope: str) -> bool:
    cred_type = str(credential_type or '').lower()
    scope = str(credential_scope or '').lower()
    return scope == 'cross_site' or cred_type == 'poh'


def _is_site_scoped_credential(credential_type: str, credential_scope: str) -> bool:
    if _is_network_wide_credential(credential_type, credential_scope):
        return False
    cred_type = str(credential_type or '').lower()
    return cred_type not in {'unknown', ''}


def _payload_contains_sensitive_wallet_keys(value) -> bool:
    sensitive = {'wallet_secret', 'secret', 'master_secret', 'private_key', 'seed'}
    if isinstance(value, dict):
        for k, v in value.items():
            key = str(k).strip().lower()
            if key in sensitive:
                return True
            if _payload_contains_sensitive_wallet_keys(v):
                return True
        return False
    if isinstance(value, list):
        return any(_payload_contains_sensitive_wallet_keys(item) for item in value)
    return False


# ============================================================================
# CONTROL-PLANE PREFERENCES (server-enforced)
# ============================================================================

def _ensure_control_plane_pref_table() -> None:
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_control_plane_preferences (
                wallet_id TEXT PRIMARY KEY,
                hosted_ui_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                control_plane_mode TEXT NOT NULL DEFAULT 'hosted',
                external_control_plane_url TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _normalize_control_plane_mode(mode_value: str | None) -> str:
    mode = str(mode_value or "hosted").strip().lower()
    if mode not in {"hosted", "federated"}:
        return "hosted"
    return mode


def _get_control_plane_preferences(wallet_id: str) -> dict:
    _ensure_control_plane_pref_table()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT hosted_ui_enabled, control_plane_mode, external_control_plane_url
            FROM wallet_control_plane_preferences
            WHERE wallet_id = %s
            """,
            (wallet_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {
                "wallet_id": wallet_id,
                "hosted_ui_enabled": True,
                "control_plane_mode": "hosted",
                "external_control_plane_url": "",
            }
        hosted_ui_enabled, control_plane_mode, external_url = row
        return {
            "wallet_id": wallet_id,
            "hosted_ui_enabled": bool(hosted_ui_enabled),
            "control_plane_mode": _normalize_control_plane_mode(control_plane_mode),
            "external_control_plane_url": str(external_url or "").strip(),
        }
    finally:
        cursor.close()
        conn.close()


def _set_control_plane_preferences(
    wallet_id: str,
    hosted_ui_enabled: bool,
    control_plane_mode: str,
    external_control_plane_url: str = "",
) -> dict:
    _ensure_control_plane_pref_table()
    from api.database import get_db_connection

    mode = _normalize_control_plane_mode(control_plane_mode)
    external_url = str(external_control_plane_url or "").strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO wallet_control_plane_preferences (
                wallet_id, hosted_ui_enabled, control_plane_mode, external_control_plane_url, updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (wallet_id)
            DO UPDATE SET
                hosted_ui_enabled = EXCLUDED.hosted_ui_enabled,
                control_plane_mode = EXCLUDED.control_plane_mode,
                external_control_plane_url = EXCLUDED.external_control_plane_url,
                updated_at = NOW()
            """,
            (wallet_id, bool(hosted_ui_enabled), mode, external_url or None),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return _get_control_plane_preferences(wallet_id)


def _ensure_firewall_runtime_table() -> None:
    ensure_agent_ops_schema()


def _normalize_runtime_field(value: str | None, fallback: str, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_", ".", ":"})
    cleaned = cleaned[:max_len]
    return cleaned or fallback


def _tenant_context_from_request(payload: dict | None = None) -> tuple[str, str]:
    body = payload if isinstance(payload, dict) else {}
    org_id = _normalize_runtime_field(
        body.get("org_id") or request.headers.get("X-Lemma-Org-Id"),
        "org_default",
        max_len=120,
    )
    environment = _normalize_runtime_field(
        body.get("environment") or request.headers.get("X-Lemma-Environment"),
        "prod",
        max_len=32,
    )
    if environment not in {"dev", "staging", "prod"}:
        environment = "prod"
    return org_id, environment


def _normalize_root_type(value: str | None) -> str:
    candidate = _normalize_runtime_field(value, "passkey_root", max_len=32)
    if candidate in {"passkey_root", "workload_root", "policy_root"}:
        return candidate
    return "passkey_root"


def _default_firewall_risk_defaults() -> dict:
    return {
        "low": "proof_required",
        "high": "step_up_required",
        "critical": "deny_until_approved",
    }


def _upsert_firewall_runtime(
    *,
    wallet_id: str,
    runtime_id: str,
    agent_id: str,
    workspace_id: str,
    display_name: str,
    policy_profile: str,
    risk_defaults: dict,
    kill_switch_enabled: bool,
    org_id: str,
    environment: str,
    root_type: str,
) -> dict:
    return upsert_agent_ops_runtime(
        runtime_id=runtime_id,
        agent_id=agent_id,
        workspace_id=workspace_id or None,
        display_name=display_name or None,
        policy_profile=policy_profile,
        risk_defaults=risk_defaults,
        kill_switch_enabled=bool(kill_switch_enabled),
        owner_wallet_id=wallet_id,
        owner_ppid=_resolve_wallet_ppid(wallet_id),
        org_id=org_id,
        environment=environment,
        root_type=root_type,
    )


def _get_firewall_runtime(*, wallet_id: str, runtime_id: str, org_id: str, environment: str) -> dict:
    return get_agent_ops_runtime(runtime_id=runtime_id, wallet_id=wallet_id, org_id=org_id, environment=environment)


def _list_firewall_runtimes(*, wallet_id: str, org_id: str, environment: str) -> list[dict]:
    return list_agent_ops_runtimes(
        wallet_id=wallet_id,
        ppid=_resolve_wallet_ppid(wallet_id),
        org_id=org_id,
        environment=environment,
    )


def _wallet_ids_for_ppid(ppid: str) -> list[str]:
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            WITH ids AS (
                SELECT wallet_id
                FROM platform_users
                WHERE user_did = %s
                  AND COALESCE(status, 'active') = 'active'
                  AND wallet_id IS NOT NULL
                  AND wallet_id <> ''

                UNION

                SELECT wallet_id
                FROM customers
                WHERE customer_did = %s
                  AND COALESCE(status, 'active') = 'active'
                  AND wallet_id IS NOT NULL
                  AND wallet_id <> ''
            )
            SELECT wallet_id
            FROM ids
            """,
            (ppid, ppid),
        )
        return [str(row[0] or "").strip() for row in (cursor.fetchall() or []) if row and str(row[0] or "").strip()]
    finally:
        cursor.close()
        conn.close()


def _runtime_record_for_ppid(*, ppid: str, runtime_id: str, org_id: str, environment: str) -> dict:
    return get_agent_ops_runtime(runtime_id=runtime_id, ppid=ppid, org_id=org_id, environment=environment)


def _agent_audit_metadata(raw_value) -> dict:
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _decision_reason_code(*, metadata: dict, status_code: int | None, success: bool | None) -> str:
    reason_code = str(metadata.get('reason_code') or '').strip().upper()
    if reason_code:
        return reason_code
    if bool(success):
        return 'ALLOW'
    if int(status_code or 0) == 401:
        return 'AUTH_REQUIRED'
    if int(status_code or 0) == 403:
        return 'POLICY_DENY'
    if int(status_code or 0) >= 500:
        return 'UPSTREAM_ERROR'
    return 'DENY'


def _alert_severity_rank(severity: str) -> int:
    if severity == 'critical':
        return 3
    if severity == 'warning':
        return 2
    if severity == 'info':
        return 1
    return 0


def _max_severity(*values: str) -> str:
    best = 'ok'
    best_rank = 0
    for value in values:
        rank = _alert_severity_rank(value)
        if rank > best_rank:
            best = value
            best_rank = rank
    return best


def _kill_firewall_runtime(*, wallet_id: str, runtime_id: str, reason: str, org_id: str, environment: str) -> bool:
    return kill_agent_ops_runtime(
        wallet_id=wallet_id,
        runtime_id=runtime_id,
        reason=reason,
        ppid=_resolve_wallet_ppid(wallet_id),
        org_id=org_id,
        environment=environment,
    )


def _resolve_wallet_ppid(wallet_id: str) -> str | None:
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            WITH candidates AS (
                SELECT user_did AS ppid, COALESCE(last_seen, created_at) AS seen_at
                FROM platform_users
                WHERE wallet_id = %s
                  AND COALESCE(status, 'active') = 'active'
                  AND user_did LIKE 'did:lemma:ppid_%%'

                UNION ALL

                SELECT customer_did AS ppid, created_at AS seen_at
                FROM customers
                WHERE wallet_id = %s
                  AND COALESCE(status, 'active') = 'active'
                  AND customer_did LIKE 'did:lemma:ppid_%%'
            )
            SELECT ppid
            FROM candidates
            ORDER BY seen_at DESC NULLS LAST
            LIMIT 1
            """,
            (wallet_id, wallet_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        ppid = str(row[0] or "").strip()
        return ppid if ppid.startswith("did:lemma:ppid_") else None
    finally:
        cursor.close()
        conn.close()


def _normalize_ppid_claim(value) -> str | None:
    candidate = str(value or "").strip()
    return candidate if candidate.startswith("did:lemma:ppid_") else None


def _parse_lemma_credential_header() -> dict | None:
    raw = str(request.headers.get("X-Lemma-Credential") or "").strip()
    if not raw:
        return None
    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    try:
        padded = raw + ("=" * ((4 - (len(raw) % 4)) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
    except Exception:
        parsed = None
    return parsed if isinstance(parsed, dict) else None


def _extract_ppid_from_lemma_header() -> str | None:
    """
    Best-effort PPID extraction from X-Lemma-Credential.

    Header may be either:
    - raw JSON credential
    - base64url-encoded JSON credential
    """
    parsed = _parse_lemma_credential_header()
    if not isinstance(parsed, dict):
        return None

    claims = parsed.get("claims") or parsed.get("credentialSubject") or {}
    ppid = (
        claims.get("sub")
        or claims.get("subject")
        or claims.get("ppid")
        or parsed.get("subject")
        or parsed.get("sub")
        or parsed.get("ppid")
    )
    return _normalize_ppid_claim(ppid)


def _extract_lemma_trust_claims() -> dict:
    parsed = _parse_lemma_credential_header() or {}
    claims = parsed.get("claims") or parsed.get("credentialSubject") or {}
    scope_raw = claims.get("scope") or []
    if isinstance(scope_raw, str):
        scope = [item.strip() for item in scope_raw.replace(";", ",").split(",") if item.strip()]
    elif isinstance(scope_raw, list):
        scope = [str(item).strip() for item in scope_raw if str(item).strip()]
    else:
        scope = []
    taint_epoch_raw = claims.get("taint_epoch")
    try:
        taint_epoch = int(taint_epoch_raw) if taint_epoch_raw is not None else None
    except (TypeError, ValueError):
        taint_epoch = None
    return {
        "trust_state": str(claims.get("trust_state") or "").strip().lower() or None,
        "taint_epoch": taint_epoch,
        "step_up_required": bool(claims.get("step_up_required")) if claims.get("step_up_required") is not None else None,
        "scope": scope,
        "credential_id": str(parsed.get("id") or "").strip() or None,
        "root_type": _normalize_root_type(claims.get("root_type") or parsed.get("root_type")),
    }


def _runtime_authorize_privileged_request(payload: dict, trust_claims: dict) -> bool:
    if bool(payload.get("privileged")):
        return True
    risk = str(payload.get("risk") or "").strip().lower()
    if risk in {"high", "critical"}:
        return True
    action = str(payload.get("action") or payload.get("requested_action") or "").strip().lower()
    privileged_actions = {"fs.write", "shell.exec", "api.internal.admin", "secrets.read"}
    if action in privileged_actions:
        return True
    scope = trust_claims.get("scope") if isinstance(trust_claims.get("scope"), list) else []
    return any(item in privileged_actions for item in scope)


def _normalize_runtime_authorize_descriptor(payload: dict) -> tuple[dict, str | None]:
    action = str(payload.get("action") or payload.get("requested_action") or "").strip().lower()
    resource = str(payload.get("resource") or payload.get("target") or payload.get("path") or "").strip()
    risk = str(payload.get("risk") or "").strip().lower()
    if not action:
        return {}, "deny_operation_descriptor_invalid"
    if not risk:
        if action in {"shell.exec", "secrets.read", "api.internal.admin"}:
            risk = "critical"
        elif action in {"fs.write", "browser.interact", "api.call.write"}:
            risk = "high"
        else:
            risk = "low"
    if risk not in {"low", "high", "critical"}:
        return {}, "deny_operation_descriptor_invalid"
    requires_resource = action in {"fs.read", "fs.write", "secrets.read", "api.call.read", "api.call.write"}
    if requires_resource and not resource:
        return {}, "deny_operation_descriptor_invalid"
    normalized = {
        "action": action,
        "resource": resource or None,
        "risk": risk,
    }
    return normalized, None


def _record_runtime_authorize_decision(
    *,
    ppid: str | None,
    runtime_id: str,
    decision: str,
    reason_code: str,
    status_code: int,
    trust_state: str | None,
    taint_epoch: int | None,
    credential_ref: str | None,
    org_id: str,
    environment: str,
    root_type: str | None = None,
) -> None:
    if not ppid:
        return
    try:
        record_agent_ops_decision_logs(
            [
                {
                    "token_id": credential_ref or "",
                    "action": "runtime.authorize",
                    "resource": runtime_id,
                    "method": str(request.method or "POST").upper(),
                    "path": str(request.path or ""),
                    "status_code": int(status_code),
                    "success": decision == "allow",
                    "metadata_json": {
                        "reason_code": reason_code,
                        "runtime_id": runtime_id,
                        "delegated_by_ppid": ppid,
                        "request_correlation_id": request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID"),
                        "trust_state": trust_state,
                        "taint_epoch": taint_epoch,
                        "policy_profile": "runtime_default_v1",
                        "org_id": org_id,
                        "environment": environment,
                        "root_type": _normalize_root_type(root_type),
                    },
                }
            ]
        )
    except Exception:
        logger.debug("runtime authorize decision logging failed", exc_info=True)


def _resolve_firewall_identity_ppid(wallet_id: str) -> str | None:
    """
    Resolve canonical identity for Lemma Firewall authz responses.

    Prefer PPID asserted by proof header when present, then fall back to wallet mapping.
    """
    header_ppid = _extract_ppid_from_lemma_header()
    if header_ppid:
        return header_ppid
    return _resolve_wallet_ppid(wallet_id)


def _build_firewall_proof_chain_artifact(
    *,
    permission_lemma: dict,
    ppid: str,
    site_id: str,
    policy_version: str,
    agent_key_id: str,
    root_type: str,
    org_id: str,
    environment: str,
) -> dict:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise RuntimeError(f"ed25519_unavailable: {exc}") from exc

    claims = permission_lemma.get('claims') if isinstance(permission_lemma.get('claims'), dict) else {}
    scope_raw = claims.get('scope') or claims.get('permissions') or claims.get('permission') or ['read']
    if isinstance(scope_raw, str):
        scope = [part.strip() for part in scope_raw.replace(';', ',').split(',') if part.strip()]
    elif isinstance(scope_raw, list):
        scope = [str(item).strip() for item in scope_raw if str(item).strip()]
    else:
        scope = ['read']
    now_ts = int(time.time())
    root_expires_at = now_ts + (30 * 24 * 3600)
    # Keep delegated proofs short-lived for safer reuse/attenuation.
    delegated_ttl_s = max(300, int(os.getenv("LEMMA_DELEGATED_PROOF_TTL_SECONDS", "28800") or "28800"))
    delegated_expires_at = min(root_expires_at, now_ts + delegated_ttl_s)
    root_proof_id = str(permission_lemma.get('id') or f"root_{uuid.uuid4().hex}")
    root_grant_id = str(claims.get('root_grant_id') or f"rgr_{uuid.uuid4().hex}")
    delegated_proof_id = f"dpf_{uuid.uuid4().hex}"
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    agent_private_key = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip("=")
    agent_public_key = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip("=")
    root_proof = {
        'proof_id': root_proof_id,
        'parent_proof_id': None,
        'root_type': root_type,
        'root_grant_id': root_grant_id,
        'subject_ppid': ppid,
        'org_id': org_id,
        'environment': environment,
        'scope': scope,
        'delegation_depth': 0,
        'aud': site_id,
        'issued_at': now_ts,
        'expires_at': root_expires_at,
        'revocation_epoch': int(claims.get('revocation_epoch') or 0),
        'ancestor_ids': [root_proof_id, root_grant_id],
        'issuer': permission_lemma.get('issuer'),
        'subject': permission_lemma.get('subject'),
        'claims': claims,
        'proof': permission_lemma.get('proof'),
        'id': root_proof_id,
    }
    delegated_proof = {
        'proof_id': delegated_proof_id,
        'parent_proof_id': root_proof_id,
        'root_type': root_type,
        'root_grant_id': root_grant_id,
        'acting_for_ppid': ppid,
        'org_id': org_id,
        'environment': environment,
        'agent_key_id': agent_key_id,
        'agent_key_alg': 'Ed25519',
        'agent_public_key': agent_public_key,
        'scope': scope,
        'aud': site_id,
        'delegation_depth': 1,
        'issued_at': now_ts,
        'expires_at': delegated_expires_at,
        'revocation_epoch': int(claims.get('revocation_epoch') or 0),
        'ancestor_ids': [delegated_proof_id, root_proof_id, root_grant_id],
        'issuer': permission_lemma.get('issuer'),
        'subject': permission_lemma.get('subject'),
        'proof': permission_lemma.get('proof'),
    }
    return {
        'version': 'authz_profile_v2',
        'root_type': root_type,
        'policy_version': policy_version,
        'proof_id': delegated_proof_id,
        'root_grant_id': root_grant_id,
        'org_id': org_id,
        'environment': environment,
        'agent_key_id': agent_key_id,
        'agent_key_alg': 'Ed25519',
        'agent_public_key': agent_public_key,
        'agent_private_key': agent_private_key,
        'root_proof': root_proof,
        'delegated_proof': delegated_proof,
        'proof_chain': [root_proof, delegated_proof],
    }


def _load_wallet_agent_overview(ppid: str, limit: int = 20) -> list[dict]:
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT token_id, agent_name, scope, issued_at, expires_at, revoked,
                   last_used_at, use_count, max_operations, task_deviation_count
            FROM agent_credentials
            WHERE authorized_by_ppid = %s
            ORDER BY COALESCE(last_used_at, issued_at) DESC
            LIMIT %s
            """,
            (ppid, int(limit)),
        )
        rows = cursor.fetchall()
        agents = {}
        for row in rows:
            token_id = str(row[0] or "").strip()
            if not token_id:
                continue
            scope_raw = row[2]
            if isinstance(scope_raw, list):
                scope = [str(s) for s in scope_raw]
            else:
                try:
                    scope = json.loads(scope_raw or "[]")
                except Exception:
                    scope = []
            expires_at = row[4]
            revoked = bool(row[5])
            expired = bool(expires_at and expires_at < datetime.now(timezone.utc))
            status = "revoked" if revoked else ("expired" if expired else "active")
            agents[token_id] = {
                "token_id": token_id,
                "agent_name": str(row[1] or "Agent").strip() or "Agent",
                "scope": scope if isinstance(scope, list) else [],
                "issued_at": row[3].isoformat() + "Z" if row[3] else None,
                "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
                "last_used_at": row[6].isoformat() + "Z" if row[6] else None,
                "use_count": int(row[7] or 0),
                "max_operations": row[8],
                "task_deviation_count": int(row[9] or 0),
                "status": status,
                "last_action": None,
            }

        token_ids = list(agents.keys())
        if token_ids:
            cursor.execute(
                """
                SELECT DISTINCT ON (al.token_id)
                    al.token_id, al.method, al.path, al.status_code, al.timestamp
                FROM agent_audit_log al
                JOIN agent_credentials ac ON ac.id = al.credential_id
                WHERE ac.authorized_by_ppid = %s
                  AND al.token_id = ANY(%s)
                ORDER BY al.token_id, al.timestamp DESC
                """,
                (ppid, token_ids),
            )
            for row in cursor.fetchall():
                token_id = str(row[0] or "").strip()
                if token_id in agents:
                    agents[token_id]["last_action"] = {
                        "method": str(row[1] or "").upper(),
                        "path": str(row[2] or ""),
                        "status_code": row[3],
                        "timestamp": row[4].isoformat() + "Z" if row[4] else None,
                    }
        return list(agents.values())
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# WALLET AUTH DECORATORS
# ============================================================================

def _extract_unlock_token() -> str | None:
    token = request.headers.get('X-Lemma-Unlock')
    if token:
        return token.strip()
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.replace('Bearer ', '').strip()
    return None


def _get_wallet_lemmas() -> List[Dict]:
    """Get wallet lemmas from headers or request body."""
    lemmas = []
    header_val = request.headers.get('X-Wallet-Lemmas')
    if header_val:
        try:
            lemmas = json.loads(header_val)
        except Exception:
            lemmas = []
    if not lemmas:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            lemmas = payload.get('wallet_lemmas') or payload.get('user_lemmas') or []
    return lemmas if isinstance(lemmas, list) else []


def _verify_lemmas_rust(lemmas: List[Dict]) -> List[Dict]:
    """Verify lemmas using Rust engine and return valid ones."""
    try:
        from lemma_crypto import PyOptimizedVerifier
    except Exception as e:
        logger.error(f"Rust verifier not available: {e}")
        raise RuntimeError("rust_verifier_unavailable")
    
    verifier = PyOptimizedVerifier()
    valid = []
    for lemma in lemmas:
        try:
            credential_json = json.dumps(lemma)
            if verifier.verify_credential_json(credential_json):
                valid.append(lemma)
        except Exception:
            continue
    return valid


def _extract_permissions_from_lemma(lemma: Dict) -> List[str]:
    claims = lemma.get('claims') or lemma.get('credentialSubject', {})
    if claims.get('packageType') and claims.get('packageType') != 'permission':
        return []
    permissions = []
    if 'permission' in claims:
        permissions.append(claims['permission'])
    if 'role' in claims:
        permissions.append(claims['role'])
    if 'permissions' in claims:
        if isinstance(claims['permissions'], list):
            permissions.extend(claims['permissions'])
        else:
            permissions.append(claims['permissions'])
    return [p for p in permissions if isinstance(p, str)]


def require_wallet_auth(f):
    """Decorator that requires server-signed wallet unlock state."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Prefer signed session cookie (server-issued) for unlock state
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        session_data = validate_session_token(session_token) if session_token else None
        
        # Fallback: short-lived unlock token (server-issued)
        unlock_data = None
        if not session_data:
            unlock_token = _extract_unlock_token()
            if unlock_token:
                try:
                    unlock_data = validate_unlock_token(unlock_token)
                except Exception:
                    unlock_data = None
        
        if not session_data and not unlock_data:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'Unlock your wallet to access this resource'
            }), 401
        
        wallet_id = (session_data or unlock_data).get('wallet_id')
        g.user_id = wallet_id
        g.wallet_id = wallet_id
        g.auth_method = 'wallet_passkey'
        g.permissions = []
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_permission(permission_id: str):
    """Decorator that requires a specific permission lemma."""
    def decorator(f):
        @wraps(f)
        @require_wallet_auth
        def decorated_function(*args, **kwargs):
            try:
                lemmas = _get_wallet_lemmas()
                valid_lemmas = _verify_lemmas_rust(lemmas)
                permissions = []
                for lemma in valid_lemmas:
                    permissions.extend(_extract_permissions_from_lemma(lemma))
                g.permissions = permissions
            except RuntimeError:
                return jsonify({
                    'success': False,
                    'error': 'verification_unavailable',
                    'message': 'Rust verifier required for permission checks'
                }), 503
            
            if permission_id not in g.permissions:
                return jsonify({
                    'success': False,
                    'error': 'Permission denied',
                    'required_permission': permission_id
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_wallet_auth_proof(auth_proof: dict) -> dict:
    """Validate a wallet auth proof."""
    try:
        required = ['type', 'method', 'walletId', 'unlockedAt', 'expiresAt']
        for field in required:
            if field not in auth_proof:
                return {'valid': False, 'error': f'Missing field: {field}'}
        
        if auth_proof['type'] != 'wallet_auth':
            return {'valid': False, 'error': 'Invalid auth type'}
        
        expires_at = auth_proof['expiresAt']
        if isinstance(expires_at, (int, float)):
            if expires_at < datetime.utcnow().timestamp() * 1000:
                return {'valid': False, 'error': 'Auth proof expired'}
        
        wallet_id = auth_proof['walletId']
        user_id = auth_proof.get('userId', wallet_id)
        
        permissions = []
        if 'lemma' in auth_proof:
            lemma = auth_proof['lemma']
            claims = lemma.get('claims', {})
            if 'permission' in claims:
                permissions.append(claims['permission'])
            if 'role' in claims:
                permissions.append(claims['role'])
            if 'permissions' in claims:
                permissions.extend(claims['permissions'])
        
        return {
            'valid': True,
            'user_id': user_id,
            'wallet_id': wallet_id,
            'permissions': permissions,
            'lemma': auth_proof.get('lemma')
        }
        
    except Exception as e:
        return {'valid': False, 'error': str(e)}


# ============================================================================
# PPID DERIVATION (from wallet_first_auth)
# ============================================================================

def derive_user_ppid(site_id: str, wallet_secret: str = None, passkey_credential_id: str = None) -> str:
    """Derive the user's PPID for a specific site."""
    from api.ppid import derive_ppid_from_passkey, derive_ppid_from_wallet_secret, canonicalize_rp_id
    
    site = canonicalize_rp_id(site_id)
    
    if wallet_secret:
        return derive_ppid_from_wallet_secret(wallet_secret, site)
    
    if passkey_credential_id:
        return derive_ppid_from_passkey(passkey_credential_id, site)
    
    logger.warning("No wallet_secret or passkey - generating random PPID")
    random_secret = secrets.token_hex(32)
    return derive_ppid_from_wallet_secret(random_secret, site)


def issue_permission_lemma(subject_ppid: str, site_id: str = 'lemma.id',
                          permissions: list = None, granted_by: str = 'system',
                          track_in_db: bool = True, permission_id: Optional[str] = None,
                          scope: Optional[List[str]] = None,
                          account_type: Optional[str] = None,
                          custom_claims: Optional[Dict] = None) -> dict:
    """Issue a permission lemma for direct wallet storage."""
    try:
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        site_issuer = issuer_manager.get_iam_issuer(site_id)
        
        perm_list = permissions or ['read', 'write']
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(days=30)
        
        perm_id = permission_id or (perm_list[0] if perm_list else 'read')
        scope_list = list(scope or perm_list or ['read'])
        account_type_value = account_type or (
            'admin' if 'admin' in scope_list else ('developer' if 'developer' in scope_list else 'user')
        )

        claims = {
            'type': 'permission',
            'siteId': site_id,
            'permissionId': perm_id,
            'permissions': ','.join(perm_list),
            'scope': ','.join(scope_list),
            'accountType': account_type_value,
            'issuedAt': issued_at.isoformat() + 'Z',
            'expiresAt': expires_at.isoformat() + 'Z',
            'credentialScope': 'site_specific',
            'deviceBound': 'true',
            'passkey_verified_at': str(int(time.time())),
        }
        if custom_claims:
            claims.update(custom_claims)

        if 'actions' not in claims and 'actions' not in (custom_claims or {}):
            from api.action_taxonomy import build_default_actions
            claims['actions'] = json.dumps(build_default_actions(scope_list))

        credential_json = site_issuer.issue_credential(subject_ppid, claims)
        credential = json.loads(credential_json)
        
        credential['packageType'] = 'permission'
        credential['credentialScope'] = 'site_specific'
        credential['deviceBound'] = True
        credential['issuerInfo'] = {
            'did': site_issuer.get_did(),
            'publicKey': site_issuer.get_public_key_hex(),
            'name': f'{site_id} IAM',
            'verified': True
        }
        
        if track_in_db:
            try:
                _track_permission_grant(
                    site_id=site_id,
                    user_did=subject_ppid,
                    permission_id=','.join(perm_list),
                    credential_id=credential.get('id', ''),
                    granted_by=granted_by,
                    expires_at=expires_at
                )
            except Exception as db_err:
                logger.warning(f"Failed to track permission in DB: {db_err}")
        
        return credential
        
    except Exception as e:
        logger.error(f"Failed to issue permission lemma: {e}")
        raise


def _role_to_permission_profile(role: str) -> Dict[str, object]:
    role_norm = (role or '').strip().lower()
    if role_norm in {'owner', 'admin', 'super_admin', 'superadmin', 'site_admin', 'platform_admin'}:
        return {
            'role': 'admin',
            'permission_id': 'admin_access',
            'permissions': ['admin', 'write', 'read', 'access', 'developer'],
            'scope': ['admin', 'write', 'read', 'developer'],
        }
    if role_norm in {'developer', 'dev'}:
        return {
            'role': 'developer',
            'permission_id': 'developer_access',
            'permissions': ['developer', 'write', 'read', 'access'],
            'scope': ['developer', 'write', 'read'],
        }
    return {
        'role': 'user',
        'permission_id': 'customer_access',
        'permissions': ['read', 'access'],
        'scope': ['read'],
    }


def _resolve_platform_role_for_ppid(ppid: str, site_id: str = 'lemma.id') -> Dict[str, object]:
    """
    Resolve the canonical platform role for a PPID from DB state.
    Priority:
      1) site_admins (active)
      2) platform_users.account_type
      3) platform_user_sites (active) for site-scoped role
      4) site_users (active)
      5) default user
    """
    from api.database import get_db, SiteAdmin, SiteUser, PlatformUserSite, PlatformUser
    from api.platform_owner import cap_platform_role_profile

    def _finalize(profile_dict: Dict[str, object]) -> Dict[str, object]:
        return cap_platform_role_profile(ppid, site_id, profile_dict)

    profile = _role_to_permission_profile('user')
    source = 'default'
    db = get_db()
    try:
        site_admin = db.query(SiteAdmin).filter(
            SiteAdmin.site_id == site_id,
            SiteAdmin.admin_did == ppid,
            SiteAdmin.is_active == True  # noqa: E712
        ).order_by(SiteAdmin.id.desc()).first()
        if site_admin:
            return _finalize({
                **_role_to_permission_profile(site_admin.admin_role or 'admin'),
                'source': 'site_admins',
            })

        account = db.query(PlatformUser).filter(PlatformUser.user_did == ppid).first()
        if account and getattr(account, 'account_type', None):
            return _finalize({
                **_role_to_permission_profile(str(account.account_type)),
                'source': 'platform_accounts',
            })

        pus = db.query(PlatformUserSite).filter(
            PlatformUserSite.site_id == site_id,
            PlatformUserSite.user_did == ppid
        ).order_by(PlatformUserSite.id.desc()).first()
        if pus and (pus.status or 'active').lower() in {'active', 'enabled'}:
            return _finalize({
                **_role_to_permission_profile(pus.role or 'user'),
                'source': 'platform_user_sites',
            })

        site_user = db.query(SiteUser).filter(
            SiteUser.site_id == site_id,
            SiteUser.user_did == ppid
        ).order_by(SiteUser.id.desc()).first()
        if site_user and (site_user.user_status or 'active').lower() not in {'suspended', 'banned'}:
            return _finalize({
                **_role_to_permission_profile(site_user.user_role or 'user'),
                'source': 'site_users',
            })
    except Exception as role_err:
        logger.warning(f"Role restore lookup failed for {site_id} {ppid[:16]}...: {role_err}")
    finally:
        db.close()

    return _finalize({**profile, 'source': source})


def _has_platform_membership(ppid: str, site_id: str = 'lemma.id') -> bool:
    """True when the PPID has intentional lemma.id platform entitlement."""
    from api.platform_membership import has_registered_platform_membership

    return has_registered_platform_membership(ppid, site_id=site_id)


def _deny_unregistered_platform_login(ppid: str, site_id: str = 'lemma.id'):
    """Fail closed when wallet PPID has no platform signup / entitlement record."""
    if _has_platform_membership(ppid, site_id=site_id):
        return None
    return jsonify(
        {
            'success': False,
            'error': 'platform_membership_required',
            'message': (
                'Register for lemma.id platform access before signing in with this wallet. '
                'Developer credentials are issued only after signup.'
            ),
        }
    ), 403


def _upsert_platform_membership(
    ppid: str,
    site_id: str,
    role: str,
    wallet_id: Optional[str] = None,
    replace_wallet_id: bool = False,
    passkey_credential_id: Optional[str] = None,
) -> None:
    """Ensure canonical platform account + site membership reflect latest state."""
    try:
        from api.platform_account import upsert_platform_account

        upsert_platform_account(
            ppid,
            site_id=site_id,
            site_role=role,
            wallet_id=wallet_id,
            replace_wallet_id=replace_wallet_id,
            passkey_credential_id=passkey_credential_id,
        )
    except Exception as sync_err:
        logger.warning(f"Platform membership upsert failed for {site_id} {ppid[:16]}...: {sync_err}")


def _track_permission_grant(site_id: str, user_did: str, permission_id: str,
                           credential_id: str, granted_by: str, expires_at: datetime):
    """Track permission grant in database."""
    from api.database import get_db_connection
    
    conn = None
    try:
        conn = get_db_connection(site_id=site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM permission_types WHERE site_id = %s AND name = %s
        """, (site_id, permission_id))
        result = cursor.fetchone()
        
        if result:
            permission_type_id = result[0]
        else:
            cursor.execute("""
                INSERT INTO permission_types (site_id, name, type, description, active)
                VALUES (%s, %s, 'role', %s, TRUE)
                RETURNING id
            """, (site_id, permission_id, f'{permission_id.title()} access'))
            permission_type_id = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO permission_instances
            (permission_type_id, site_id, email, credential_did, granted_at, granted_by, expires_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            permission_type_id,
            site_id,
            '',
            user_did,
            datetime.utcnow(),
            granted_by,
            expires_at,
            json.dumps({'credential_id': credential_id}) if credential_id else '{}'
        ))
        
        conn.commit()
        cursor.close()
        
    except Exception as e:
        logger.error(f"Database tracking failed: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


# ============================================================================
# WALLET RETRIEVAL SERVICE (from wallet_retrieval_flow)
# ============================================================================

class WalletRetrievalManager:
    """Manages PoH verification to wallet retrieval connection."""
    
    def __init__(self):
        from api.config import get_wallet_salt, get_hpke_server_key
        self.issuer_secret_salt = get_wallet_salt()
        self.r_vault = get_hpke_server_key()
    
    def extract_kyc_from_poh_verification(self, stripe_session_data: Dict) -> Optional[Dict]:
        if not stripe_session_data:
            return None
        
        return {
            'jurisdiction_code': stripe_session_data.get('country', 'US').upper(),
            'doc_type': stripe_session_data.get('document_type', 'unknown').lower(),
            'doc_number_norm': stripe_session_data.get('document_number', '').replace(" ", "").replace("-", "").upper(),
            'surname_norm': stripe_session_data.get('last_name', '').lower().strip(),
            'dob_yyyymmdd': stripe_session_data.get('date_of_birth', ''),
            'liveness_template_hash': hashlib.sha256(
                stripe_session_data.get('selfie_data', '').encode()
            ).hexdigest()[:32] if stripe_session_data.get('selfie_data') else ''
        }
    
    def derive_rid_from_kyc(self, kyc_data: Dict) -> bytes:
        try:
            from lemma_crypto import AdvancedWalletCrypto, KYCTuple
            
            kyc_tuple = KYCTuple(
                jurisdiction_code=kyc_data['jurisdiction_code'],
                doc_type=kyc_data['doc_type'],
                doc_number_norm=kyc_data['doc_number_norm'],
                surname_norm=kyc_data['surname_norm'],
                dob_yyyymmdd=kyc_data['dob_yyyymmdd'],
                liveness_template_hash=kyc_data['liveness_template_hash']
            )
            
            kyc_cbor = AdvancedWalletCrypto.normalize_kyc_tuple(kyc_tuple)
            adv_secrets = AdvancedWalletCrypto.generate_secrets()
            crypto = AdvancedWalletCrypto(adv_secrets[0], adv_secrets[1], adv_secrets[2])
            rid = crypto.derive_rid(kyc_cbor)
            return bytes(rid)
            
        except ImportError:
            kyc_string = f"{kyc_data['jurisdiction_code']}|{kyc_data['doc_type']}|{kyc_data['doc_number_norm']}|{kyc_data['surname_norm']}|{kyc_data['dob_yyyymmdd']}|{kyc_data['liveness_template_hash']}"
            combined = kyc_string.encode() + self.issuer_secret_salt
            return hashlib.blake2b(combined, digest_size=32).digest()
    
    def derive_vid_from_rid(self, rid: bytes) -> str:
        try:
            from lemma_crypto import AdvancedWalletCrypto
            adv_secrets = AdvancedWalletCrypto.generate_secrets()
            crypto = AdvancedWalletCrypto(adv_secrets[0], adv_secrets[1], list(self.r_vault))
            vid_bytes = crypto.derive_vid(list(rid))
            return bytes(vid_bytes).hex()
        except ImportError:
            combined = self.r_vault + rid
            return hashlib.blake2b(combined, digest_size=32).digest().hex()
    
    def connect_poh_to_wallet_retrieval(self, poh_credential: Dict) -> Dict:
        try:
            claims = poh_credential.get('claims') or poh_credential.get('credentialSubject', {})
            stripe_session_id = claims.get('stripe_session_id')
            
            if not stripe_session_id:
                return {'success': False, 'error': 'no_stripe_session'}
            
            stripe_data = {
                'session_id': stripe_session_id,
                'country': 'US',
                'document_type': 'passport',
                'document_number': 'P123456789',
                'last_name': 'TestUser',
                'date_of_birth': '1990-01-01',
                'selfie_data': f'selfie_hash_{stripe_session_id}',
                'verification_status': 'verified'
            }
            
            kyc_data = self.extract_kyc_from_poh_verification(stripe_data)
            if not kyc_data:
                return {'success': False, 'error': 'kyc_extraction_failed'}
            
            rid = self.derive_rid_from_kyc(kyc_data)
            vid = self.derive_vid_from_rid(rid)
            
            session['user_rid'] = rid.hex()
            session['user_vid'] = vid
            session['kyc_verified'] = True
            
            return {
                'success': True,
                'rid_available': True,
                'vid_available': True,
                'wallet_retrieval_enabled': True
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


_retrieval_manager = None


def get_retrieval_manager() -> WalletRetrievalManager:
    global _retrieval_manager
    if _retrieval_manager is None:
        _retrieval_manager = WalletRetrievalManager()
    return _retrieval_manager


# ============================================================================
# REVOCATION HELPERS (from wallet_revocation)
# ============================================================================

def await_network_revocation(credential_id: str, reason: str) -> bool:
    try:
        from api.sdk_api import distribute_revocation_to_network
        
        bloom_hash = hashlib.sha256(credential_id.encode()).hexdigest()
        
        return distribute_revocation_to_network(
            credential_id=credential_id,
            bloom_hash=bloom_hash,
            reason=reason
        )
    except Exception as e:
        logger.warning(f"Network revocation failed: {e}")
        return False


def await_site_revocation(credential_id: str, reason: str, site_domain: str = None) -> bool:
    try:
        from api.database import get_db, RevocationList
        
        db_session = get_db()
        try:
            existing = db_session.query(RevocationList).filter_by(lemma_id=credential_id).first()
            if existing:
                return True
            
            revocation = RevocationList(
                lemma_id=credential_id,
                credential_id=credential_id,
                lemma_type='permission',
                site_id=site_domain or 'unknown',
                user_did='user_requested',
                revoked_by='user_self_revoke',
                revoked_at=datetime.utcnow(),
                reason=reason,
                bloom_filter_updated=False
            )
            
            db_session.add(revocation)
            db_session.commit()

            # Immediately sync this revocation into bloom path.
            bloom_synced = False
            try:
                from api.permission_verification import sync_revocation_keys
                bloom_synced = bool(sync_revocation_keys(credential_id))
            except Exception as sync_err:
                logger.warning(f"Local bloom sync failed for {credential_id}: {sync_err}")

            if bloom_synced:
                revocation.bloom_filter_updated = True
                db_session.commit()
            else:
                logger.warning(f"Revocation stored but bloom_filter_updated remains false for {credential_id}")

            try:
                from api.bloom_snapshot import invalidate_bloom_filter_cache

                invalidate_bloom_filter_cache()
            except Exception:
                pass

            return True
            
        finally:
            db_session.close()
        
    except Exception as e:
        logger.warning(f"Site revocation failed: {e}")
        return False


# ============================================================================
# TRANSFER SESSION CLASS
# ============================================================================

class TransferSession:
    def __init__(self, source_device_id: str, wallet_data=None):
        self.session_id = str(uuid.uuid4())[:12]
        self.source_device_id = source_device_id
        self.transfer_key = hashlib.sha256(f"{self.session_id}_{time.time()}".encode()).hexdigest()[:32]
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(minutes=5)
        self.wallet_data = wallet_data
        self.status = 'waiting'
        self.target_device_id = None
    
    def to_qr_data(self) -> dict:
        return {
            'type': 'lemma_transfer_token',
            'session_id': self.session_id,
            'transfer_key': self.transfer_key,
            'expires_at': int(self.expires_at.timestamp() * 1000),
            'source_device': self.source_device_id[:8]
        }
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


# ============================================================================
# ROUTES: WALLET-FIRST AUTHENTICATION
# ============================================================================

# Platform site IDs that are always allowed from same-origin/allowed origins
_PLATFORM_SITE_IDS = {'lemma.id', 'lemma_platform', 'lemma_federated', 'lemma_iam'}

def _validate_issuance_request(site_id: str):
    """
    Validate that a lemma issuance request is authorized.
    
    Security checks:
    1. Platform site IDs: only from same-origin or allowed origins
    2. Third-party site IDs: site must be registered in database
    3. Cross-origin requests: Origin must match the requested site domain
       (prevents site A from requesting lemmas for site B)
    
    Returns: (allowed: bool, error_message: str or None)
    """
    origin = request.headers.get('Origin')
    
    # Platform site IDs: allow from same-origin or allowed origins
    if site_id in _PLATFORM_SITE_IDS:
        if not origin or _origin_allowed(origin):
            return True, None
        logger.warning(f"Platform issuance blocked from origin: {origin}")
        return False, 'Platform issuance not allowed from this origin'
    
    # Third-party site: must be registered in database
    try:
        from api.database import SessionLocal, Site
        db = SessionLocal()
        try:
            site = db.query(Site).filter(
                (Site.site_id == site_id) | (Site.site_domain == site_id)
            ).first()
        finally:
            db.close()
        
        if not site:
            logger.warning(f"Issuance blocked for unregistered site: {site_id}")
            return False, f'Site not registered: {site_id}'
        
        # Cross-origin requests: origin must match the site domain
        if origin:
            origin_hostname = (urlparse(origin).hostname or '').lower()
            site_domain = (site.site_domain or '').lower()
            
            # Allow if origin matches site domain (exact or subdomain)
            if origin_hostname == site_domain or origin_hostname.endswith('.' + site_domain):
                return True, None
            
            # Allow if origin is lemma.id (developer setup page making requests)
            if _origin_allowed(origin):
                return True, None
            
            logger.warning(f"Origin mismatch: {origin} requesting issuance for {site_domain}")
            return False, f'Origin does not match site domain'
        
        # No origin header (same-origin from lemma.id): allow for registered sites
        return True, None
        
    except Exception as e:
        logger.error(f"Issuance validation error: {e}")
        return False, 'Unable to validate site registration'


# Import rate limiter (Redis-backed in production)
try:
    from api.rate_limiter import rate_limit as _redis_rate_limit
    _rate_limit_available = True
except ImportError:
    _rate_limit_available = False


@wallet_service_bp.route('/api/wallet-auth/issue', methods=['POST'])
def issue_to_wallet():
    """Issue a permission lemma directly to the user's wallet.
    
    Accepts two authentication methods (in order of preference):
    1. ppid, client-derived PPID (PREFERRED: wallet_secret stays in browser)
    2. passkey_credential_id, server-side PPID derivation from passkey
    
    Security: Rate limited (20/min per IP), requires registered site,
    cross-origin requests must match site domain.
    """
    try:
        data = request.get_json() or {}
        rejected = _reject_wallet_secret_payload(data)
        if rejected:
            return rejected
        
        from api.validation import validate_site_id, ValidationError
        try:
            site_id = validate_site_id(data.get('site_id'), required=False, allow_lemma_default=True)
        except ValidationError as ve:
            return jsonify({'success': False, 'error': 'validation_error', 'message': str(ve)}), 400
        
        # Validate issuance is authorized for this site/origin
        allowed, error_msg = _validate_issuance_request(site_id)
        if not allowed:
            return jsonify({
                'success': False,
                'error': 'issuance_not_authorized',
                'message': error_msg
            }), 403
        
        # Accept client-derived PPID directly (preferred: wallet_secret never leaves browser)
        client_ppid = data.get('ppid')
        passkey_credential_id = data.get('passkey_credential_id')
        
        from api.config import reject_client_ppid_issuance, warn_client_ppid_issuance
        from api.platform_owner import is_platform_site

        if client_ppid:
            if reject_client_ppid_issuance() and not is_platform_site(site_id):
                return jsonify({
                    'success': False,
                    'error': 'client_ppid_deprecated',
                    'message': 'Use IsHumanVerifier.verifyForBackend() and verify the signed presentation on your backend.',
                }), 410
            if warn_client_ppid_issuance():
                logger.warning(
                    "Deprecated bare client_ppid issuance for site=%s origin=%s",
                    site_id,
                    request.headers.get('Origin', ''),
                )
            # Validate PPID format: did:lemma:ppid_<64-hex-chars>
            import re
            if not re.match(r'^did:lemma:ppid_[0-9a-f]{64}$', client_ppid):
                return jsonify({'success': False, 'error': 'Invalid PPID format'}), 400
            ppid = client_ppid
        elif passkey_credential_id:
            ppid = derive_user_ppid(site_id, passkey_credential_id=passkey_credential_id)
        else:
            return jsonify({
                'success': False,
                'error': 'ppid_or_passkey_required',
                'message': 'ppid or passkey_credential_id required',
            }), 400

        if is_platform_site(site_id):
            denied_membership = _deny_unregistered_platform_login(ppid, site_id=site_id)
            if denied_membership:
                return denied_membership
            role_profile = _resolve_platform_role_for_ppid(ppid, site_id=site_id)
            permission_lemma = issue_permission_lemma(
                subject_ppid=ppid,
                site_id=site_id,
                permissions=role_profile['permissions'],
                scope=role_profile['scope'],
                permission_id=role_profile['permission_id'],
                account_type=role_profile['role'],
                granted_by='wallet_auth',
            )
        else:
            permission_lemma = issue_permission_lemma(
                subject_ppid=ppid,
                site_id=site_id,
                permissions=['read', 'write', 'access'],
                granted_by='wallet_auth'
            )

        response = jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'permission_lemma': permission_lemma
        })
        if client_ppid and warn_client_ppid_issuance():
            response.headers['Deprecation'] = 'true'
            response.headers['Link'] = '</docs/integration/ISHUMAN_AGENT_INTEGRATION.md>; rel="deprecation"'

        return response
        
    except Exception as e:
        logger.error(f"Wallet issue failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Apply rate limiting if available (20 requests per minute per IP)
if _rate_limit_available:
    issue_to_wallet = _redis_rate_limit(20, 60)(issue_to_wallet)


@wallet_service_bp.route('/api/wallet-auth/register-and-issue', methods=['POST'])
def register_and_issue():
    """Combined: Register passkey + Issue permission.
    
    Security: Rate limited (20/min per IP), requires registered site,
    cross-origin requests must match site domain.
    """
    try:
        data = request.get_json() or {}
        rejected = _reject_wallet_secret_payload(data)
        if rejected:
            return rejected

        site_id = data.get('site_id', 'lemma.id')
        
        # Validate issuance is authorized for this site/origin
        allowed, error_msg = _validate_issuance_request(site_id)
        if not allowed:
            return jsonify({
                'success': False,
                'error': 'issuance_not_authorized',
                'message': error_msg
            }), 403
        
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not passkey_credential_id:
            return jsonify({
                'success': False,
                'error': 'passkey_required',
                'message': 'passkey_credential_id required',
            }), 400
        
        ppid = derive_user_ppid(site_id, passkey_credential_id=passkey_credential_id)
        
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=['read', 'write', 'access']
        )
        
        # Return PPID and permission_lemma - client stores in wallet
        # No server-side session needed (session-free architecture)
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'is_new_user': True,
            'permission_lemma': permission_lemma
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Apply rate limiting if available (20 requests per minute per IP)
if _rate_limit_available:
    register_and_issue = _redis_rate_limit(20, 60)(register_and_issue)


@wallet_service_bp.route('/api/wallet-auth/verify-session', methods=['POST'])
def verify_wallet_session():
    """Verify wallet unlock and check permissions."""
    try:
        data = request.get_json() or {}
        rejected = _reject_wallet_secret_payload(data)
        if rejected:
            return rejected

        site_id = data.get('site_id', 'lemma.id')
        passkey_credential_id = data.get('passkey_credential_id')
        permissions = data.get('permissions', [])
        
        if not passkey_credential_id:
            return jsonify({
                'success': False,
                'error': 'passkey_required',
                'message': 'passkey_credential_id required',
            }), 400
        
        ppid = derive_user_ppid(site_id, passkey_credential_id=passkey_credential_id)
        
        from api.ppid import canonicalize_rp_id
        site_canonical = canonicalize_rp_id(site_id)
        has_site_permission = any(site_canonical in p for p in permissions)
        
        # Return authentication status - no server-side session needed
        # Client uses PPID for subsequent requests (session-free architecture)
        return jsonify({
            'success': True,
            'authenticated': True,
            'ppid': ppid,
            'site_id': site_id,
            'has_permission': has_site_permission
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-auth/platform-login', methods=['POST'])
def platform_login():
    """
    Platform developer login with wallet_id sync for cross-device support.
    
    This endpoint is specifically for lemma.id platform developers (not end-users).
    It handles:
    1. PPID derivation for the platform
    2. Wallet_id sync (store or return canonical wallet_id)
    3. Permission lemma issuance
    4. Global session setup
    """
    try:
        from api.platform_owner import enforce_platform_login_wallet

        data = request.get_json() or {}
        rejected = _reject_wallet_secret_payload(data)
        if rejected:
            return rejected

        passkey_credential_id = data.get('passkey_credential_id')
        client_ppid = data.get('ppid')
        client_wallet_id = data.get('wallet_id')  # SDK's local wallet_id

        ppid, denied = enforce_platform_login_wallet(
            client_ppid=client_ppid,
            wallet_id=client_wallet_id,
            passkey_credential_id=passkey_credential_id,
        )
        if denied:
            return jsonify(denied[0]), denied[1]

        # A wallet id may replace an existing internal-IAM wallet link only
        # after IDV bound it to a LemmaPerson. This is the recovery authority;
        # the client-supplied PPID by itself is never sufficient.
        person_root_wallet_verified = False
        if client_wallet_id:
            from api.database import get_db as get_identity_db
            from api.ishuman import _resolve_person_id_for_wallet

            identity_db = get_identity_db()
            try:
                person_root_wallet_verified = bool(
                    _resolve_person_id_for_wallet(identity_db, client_wallet_id)
                )
            finally:
                identity_db.close()

        denied_membership = _deny_unregistered_platform_login(ppid, site_id='lemma.id')
        if denied_membership:
            return denied_membership
        
        site_id = 'lemma.id'
        
        # Find or create Customer record for this developer
        from api.database import get_db, Customer
        import secrets
        
        db = get_db()
        canonical_wallet_id = None
        is_new_user = False
        
        try:
            # Try to find customer by PPID or wallet_id
            customer = db.query(Customer).filter(Customer.customer_did == ppid).first()
            
            if not customer:
                # Look by wallet_id if client provided one
                if client_wallet_id:
                    customer = db.query(Customer).filter(
                        Customer.wallet_id == client_wallet_id
                    ).first()
            
            if customer:
                # Existing user - use stored wallet_id or store client's
                if (
                    client_wallet_id
                    and person_root_wallet_verified
                    and customer.wallet_id != client_wallet_id
                ):
                    old_wallet_id = customer.wallet_id
                    customer.wallet_id = client_wallet_id
                    canonical_wallet_id = client_wallet_id
                    db.commit()
                    logger.info(
                        "Platform recovery: rebound person-root account wallet %s... -> %s...",
                        (old_wallet_id or "")[:12],
                        client_wallet_id[:12],
                    )
                elif customer.wallet_id:
                    canonical_wallet_id = customer.wallet_id
                    logger.info(f"Platform login: using stored wallet_id {canonical_wallet_id[:12]}...")
                elif client_wallet_id:
                    customer.wallet_id = client_wallet_id
                    canonical_wallet_id = client_wallet_id
                    db.commit()
                    logger.info(f"Platform login: stored client wallet_id {canonical_wallet_id[:12]}...")
            else:
                is_new_user = True
                canonical_wallet_id = client_wallet_id or f"wallet_{secrets.token_hex(16)}"
                logger.info(
                    "Platform login: no customer record for %s; membership gate required",
                    ppid[:24],
                )
                
        finally:
            db.close()
        
        role_profile = _resolve_platform_role_for_ppid(ppid, site_id=site_id)
        _upsert_platform_membership(
            ppid=ppid,
            site_id=site_id,
            role=role_profile['role'],
            wallet_id=canonical_wallet_id,
            replace_wallet_id=bool(
                person_root_wallet_verified
                and client_wallet_id
                and canonical_wallet_id == client_wallet_id
            ),
            passkey_credential_id=passkey_credential_id,
        )

        # Issue permission lemma based on resolved role for this PPID.
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=role_profile['permissions'],
            scope=role_profile['scope'],
            permission_id=role_profile['permission_id'],
            account_type=role_profile['role'],
            granted_by='platform_auth_restore'
        )
        
        # Store global session for cross-device sync
        if canonical_wallet_id:
            try:
                from api.wallet_session_sync import _store_global_session
                import time
                _store_global_session(
                    wallet_id=canonical_wallet_id,
                    unlocked_at=int(time.time() * 1000),
                    expires_at=int(time.time()) + 86400,  # 24h
                    profile_id='default',
                    profile_name='Developer'
                )
                logger.info(f"Platform login: set global session for {canonical_wallet_id[:12]}...")
            except Exception as e:
                logger.warning(f"Failed to set global session: {e}")
        
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'is_new_user': is_new_user,
            'restored_role': role_profile['role'],
            'restored_from': role_profile['source'],
            'permission_lemma': permission_lemma,
            # CRITICAL: Return canonical wallet_id so client can sync
            'wallet_id': canonical_wallet_id,
            'wallet_id_synced': canonical_wallet_id != client_wallet_id if client_wallet_id else False
        })
        
    except Exception as e:
        logger.error(f"Platform login failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-auth/restore-site-access', methods=['POST'])
def restore_site_access():
    """
    Restore role-based access for a PPID on a site.
    Intended for first sign-in on newly linked devices.
    """
    try:
        data = request.get_json(silent=True) or {}
        rejected = _reject_wallet_secret_payload(data)
        if rejected:
            return rejected

        passkey_credential_id = data.get('passkey_credential_id')
        client_ppid = data.get('ppid')
        client_wallet_id = data.get('wallet_id')
        site_id = (data.get('site_id') or 'lemma.id').strip().lower()

        from api.platform_owner import enforce_platform_login_wallet, is_platform_site

        if is_platform_site(site_id):
            ppid, denied = enforce_platform_login_wallet(
                client_ppid=client_ppid,
                wallet_id=client_wallet_id,
                passkey_credential_id=passkey_credential_id,
            )
            if denied:
                return jsonify(denied[0]), denied[1]
            denied_membership = _deny_unregistered_platform_login(ppid, site_id=site_id)
            if denied_membership:
                return denied_membership
        elif client_ppid:
            ppid = client_ppid
        elif passkey_credential_id:
            ppid = derive_user_ppid(site_id, passkey_credential_id=passkey_credential_id)
        else:
            return jsonify({
                'success': False,
                'error': 'ppid_or_passkey_required',
                'message': 'ppid or passkey_credential_id required',
            }), 400
        role_profile = _resolve_platform_role_for_ppid(ppid, site_id=site_id)
        _upsert_platform_membership(
            ppid=ppid,
            site_id=site_id,
            role=role_profile['role'],
            wallet_id=None,
            passkey_credential_id=passkey_credential_id,
        )

        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=role_profile['permissions'],
            scope=role_profile['scope'],
            permission_id=role_profile['permission_id'],
            account_type=role_profile['role'],
            granted_by='restore_site_access'
        )

        return jsonify({
            'success': True,
            'site_id': site_id,
            'ppid': ppid,
            'restored_role': role_profile['role'],
            'restored_from': role_profile['source'],
            'permission_lemma': permission_lemma
        })
    except Exception as e:
        logger.error(f"Restore site access failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ROUTES: SESSION SYNC
# ============================================================================

@wallet_service_bp.route('/api/wallet/session-sync', methods=['POST', 'OPTIONS'])
def session_sync():
    """Sync wallet session across sites."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_token:
        return cross_origin_response({
            'success': False,
            'error': 'no_session',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        }, 401)
    
    session_data = validate_session_token(session_token)
    
    if not session_data:
        return cross_origin_response({
            'success': False,
            'error': 'session_expired',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        }, 401)
    
    return cross_origin_response({
        'success': True,
        'session': {
            'valid': True,
            'wallet_id': session_data['wallet_id'],
            'unlocked_at': session_data['unlocked_at'],
            'expires_at': session_data['expires_at'],
            'time_remaining': session_data['expires_at'] - int(time.time())
        },
        'credentials': [],
        'synced_at': int(time.time() * 1000)
    })


# NOTE: set-session endpoint is defined in wallet_session_sync.py
# (includes global session storage for cross-device "one passkey per day")

# NOTE: clear-session endpoint is defined in wallet_session_sync.py
# (includes global session clearing for cross-device lock detection)


# ============================================================================
# ROUTES: WALLET RETRIEVAL
# ============================================================================

@wallet_service_bp.route('/api/wallet/connect-poh', methods=['POST'])
@require_wallet_auth
def connect_poh_to_wallet():
    """Connect PoH verification to wallet retrieval."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'invalid_request'}), 400
        
        poh_credential = data.get('poh_credential')
        if not poh_credential:
            return jsonify({'success': False, 'error': 'missing_credential'}), 400
        
        manager = get_retrieval_manager()
        result = manager.connect_poh_to_wallet_retrieval(poh_credential)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/retrieve', methods=['POST'])
@require_wallet_auth
def retrieve_wallet():
    """Retrieve wallet using RID/VID from PoH verification."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'invalid_request'}), 400
        
        user_vid = session.get('user_vid')
        kyc_verified = session.get('kyc_verified', False)
        
        if not user_vid or not kyc_verified:
            return jsonify({
                'success': False,
                'error': 'poh_connection_required',
                'required_endpoint': '/api/wallet/connect-poh'
            }), 400
        
        recovery_factors = data.get('recovery_factors', {})
        if not recovery_factors.get('passphrase'):
            return jsonify({'success': False, 'error': 'missing_passphrase'}), 400
        
        from api.recovery_vault import get_vault_manager
        vault_manager = get_vault_manager()
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        envelope_result = vault_manager.get_envelope(user_vid, client_ip)
        
        if not envelope_result['success']:
            return jsonify({'success': False, 'error': 'wallet_not_found'}), 404
        
        return jsonify({
            'success': True,
            'wallet_found': True,
            'envelope_counter': envelope_result['counter']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/status', methods=['GET'])
def get_wallet_status():
    """Get wallet retrieval status."""
    return jsonify({
        'success': True,
        'status': {
            'poh_connected': session.get('kyc_verified', False),
            'rid_available': bool(session.get('user_rid')),
            'vid_available': bool(session.get('user_vid')),
            'session_active': True
        }
    })


@wallet_service_bp.route('/api/wallet/control-plane/preferences', methods=['GET', 'POST'])
@require_wallet_auth
def wallet_control_plane_preferences():
    """Get/update hosted control-plane routing preferences for this wallet."""
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401

    if request.method == 'GET':
        prefs = _get_control_plane_preferences(wallet_id)
        return jsonify({'success': True, 'preferences': prefs})

    data = request.get_json(silent=True) or {}
    hosted_ui_enabled = bool(data.get('hosted_ui_enabled', True))
    control_plane_mode = _normalize_control_plane_mode(data.get('control_plane_mode'))
    external_url = str(data.get('external_control_plane_url') or '').strip()
    if control_plane_mode == 'federated' and external_url:
        # Basic URL sanity check for external CP routing.
        parsed = _parse_origin(external_url)
        if not parsed:
            return jsonify({'success': False, 'error': 'invalid_external_control_plane_url'}), 400

    prefs = _set_control_plane_preferences(
        wallet_id=wallet_id,
        hosted_ui_enabled=hosted_ui_enabled,
        control_plane_mode=control_plane_mode,
        external_control_plane_url=external_url,
    )
    return jsonify({'success': True, 'preferences': prefs})


@wallet_service_bp.route('/api/wallet/control-plane/launch', methods=['GET'])
@require_wallet_auth
def wallet_control_plane_launch():
    """
    Resolve where the wallet should route control-plane UX.
    This endpoint is server-enforced and can disable hosted UI per wallet.
    """
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401

    prefs = _get_control_plane_preferences(wallet_id)
    mode = prefs.get('control_plane_mode', 'hosted')
    hosted_enabled = bool(prefs.get('hosted_ui_enabled', True))
    external_url = str(prefs.get('external_control_plane_url') or '').strip()

    if mode == 'federated' and external_url:
        return jsonify({
            'success': True,
            'mode': 'federated',
            'launch_url': external_url,
            'server_enforced': True,
        })

    if not hosted_enabled:
        return jsonify({
            'success': False,
            'error': 'hosted_control_plane_disabled',
            'message': 'Hosted control plane is disabled for this wallet. Configure federated URL or re-enable hosted mode.',
            'server_enforced': True,
        }), 403

    return jsonify({
        'success': True,
        'mode': 'hosted',
        'launch_url': '/developer',
        'server_enforced': True,
    })


_LEGACY_FIREWALL_PREFIX = '/api/wallet/firewall/'
_RUNTIME_SUCCESSOR_DOC = 'https://lemma.id/docs'
_DEFAULT_FIREWALL_SUNSET = 'Wed, 30 Sep 2026 00:00:00 GMT'
_LEGACY_POLICY_PROFILE_ID = 'lemma_firewall_default_v1'
_RUNTIME_POLICY_PROFILE_ID = 'runtime_default_v1'


def _with_runtime_deprecation_headers(response):
    flask_response = make_response(response)
    if request.path.startswith(_LEGACY_FIREWALL_PREFIX):
        flask_response.headers['Deprecation'] = 'true'
        flask_response.headers['Sunset'] = os.getenv(
            'LEMMA_FIREWALL_ROUTE_SUNSET',
            _DEFAULT_FIREWALL_SUNSET,
        )
        flask_response.headers['Link'] = (
            f'<{_RUNTIME_SUCCESSOR_DOC}>; rel="successor-version"'
        )
    return flask_response


def runtime_endpoint_compat(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        return _with_runtime_deprecation_headers(func(*args, **kwargs))

    return wrapped


def _normalize_policy_profile_for_storage(profile_id: str | None) -> str:
    normalized = _normalize_runtime_field(profile_id, _RUNTIME_POLICY_PROFILE_ID, max_len=120)
    if normalized == _RUNTIME_POLICY_PROFILE_ID:
        return _LEGACY_POLICY_PROFILE_ID
    return normalized


def _normalize_policy_profile_for_response(profile_id: str | None) -> str:
    normalized = str(profile_id or '').strip()
    if not normalized:
        return _RUNTIME_POLICY_PROFILE_ID
    if normalized == _LEGACY_POLICY_PROFILE_ID:
        return _RUNTIME_POLICY_PROFILE_ID
    return normalized


def _runtime_to_response_shape(runtime_record: dict | None) -> dict:
    runtime_record = dict(runtime_record or {})
    runtime_record['policy_profile'] = _normalize_policy_profile_for_response(runtime_record.get('policy_profile'))
    return runtime_record


def _decision_to_response_shape(decision_record: dict | None) -> dict:
    decision_record = dict(decision_record or {})
    decision_record['policy_profile'] = _normalize_policy_profile_for_response(decision_record.get('policy_profile'))
    return decision_record


def _policy_profile_to_response_shape(profile_record: dict | None) -> dict:
    profile_record = dict(profile_record or {})
    profile_record['policy_profile_id'] = _normalize_policy_profile_for_response(profile_record.get('policy_profile_id'))
    return profile_record


@wallet_service_bp.route('/api/wallet/runtimes/bootstrap', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/bootstrap', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_bootstrap():
    """
    Bootstrap Lemma Firewall runtime defaults for a wallet.

    This endpoint is designed for "connect runtime" onboarding, so users do not
    need to register a separate Lemma site per Lemma Firewall agent/runtime.
    """
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401

    payload = request.get_json(silent=True) or {}
    org_id, environment = _tenant_context_from_request(payload)
    root_type = _normalize_root_type(payload.get("root_type"))
    runtime_id = _normalize_runtime_field(payload.get('runtime_id'), 'lemma-firewall-default', max_len=80)
    agent_id = _normalize_runtime_field(payload.get('agent_id'), 'main', max_len=80)
    workspace_id = _normalize_runtime_field(payload.get('workspace_id'), 'default', max_len=120)
    display_name = str(payload.get('display_name') or 'Lemma Firewall Runtime').strip()[:160]
    policy_profile = _normalize_policy_profile_for_storage(payload.get('policy_profile'))

    supplied_risk_defaults = payload.get('risk_defaults')
    risk_defaults = _default_firewall_risk_defaults()
    if isinstance(supplied_risk_defaults, dict):
        for risk_key in ('low', 'high', 'critical'):
            decision = str(supplied_risk_defaults.get(risk_key) or '').strip().lower()
            if decision:
                risk_defaults[risk_key] = decision
    kill_switch_enabled = bool(payload.get('kill_switch_enabled', True))

    cp_mode = _normalize_control_plane_mode(payload.get('control_plane_mode'))
    external_url = str(payload.get('external_control_plane_url') or '').strip()
    if cp_mode == 'federated' and external_url:
        parsed = _parse_origin(external_url)
        if not parsed:
            return jsonify({'success': False, 'error': 'invalid_external_control_plane_url'}), 400

    try:
        runtime = _upsert_firewall_runtime(
            wallet_id=str(wallet_id),
            runtime_id=runtime_id,
            agent_id=agent_id,
            workspace_id=workspace_id,
            display_name=display_name,
            policy_profile=policy_profile,
            risk_defaults=risk_defaults,
            kill_switch_enabled=kill_switch_enabled,
            org_id=org_id,
            environment=environment,
            root_type=root_type,
        )
        prefs = _set_control_plane_preferences(
            wallet_id=str(wallet_id),
            hosted_ui_enabled=True,
            control_plane_mode=cp_mode,
            external_control_plane_url=external_url,
        )
        ppid = _resolve_firewall_identity_ppid(str(wallet_id))
        return jsonify({
            'success': True,
            'ppid': ppid,
            'runtime': _runtime_to_response_shape(runtime),
            'org_id': org_id,
            'environment': environment,
            'control_plane_preferences': prefs,
            'server_enforced_defaults': {
                'proof_required_by_default': True,
                'kill_switch_enabled': kill_switch_enabled,
                'risk_defaults': risk_defaults,
            },
        })
    except Exception as exc:
        logger.error("wallet_firewall_bootstrap failed: %s", exc)
        return jsonify({'success': False, 'error': 'firewall_bootstrap_failed'}), 500


@wallet_service_bp.route('/api/wallet/runtimes/issue-proof', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/issue-proof', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_issue_proof():
    """
    Issue a wallet-authenticated permission lemma for Lemma Firewall proof-first setup.

    This is wallet/browser-first onboarding (no break-glass self-issue required).
    """
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401

    payload = request.get_json(silent=True) or {}
    site_id = str(payload.get('site_id') or 'lemma.id').strip().lower()
    granted_by = str(payload.get('granted_by') or 'firewall_wallet_issue').strip()[:120]
    task_id = str(payload.get('task_id') or '').strip()[:120]
    runtime_id = str(payload.get('runtime_id') or '').strip()[:120]
    if task_id and granted_by.startswith('agent_ops'):
        granted_by = f"{granted_by}:{task_id}"[:120]
    agent_key_id = str(
        payload.get('agent_key_id') or runtime_id or 'lemma-firewall-agent-key'
    ).strip()[:120] or 'lemma-firewall-agent-key'
    policy_version = str(payload.get('policy_version') or 'authz_policy_v2').strip()[:120] or 'authz_policy_v2'
    root_type = _normalize_root_type(payload.get('root_type'))
    org_id, environment = _tenant_context_from_request(payload)

    ppid = _resolve_firewall_identity_ppid(str(wallet_id))
    if not ppid:
        return jsonify({
            'success': False,
            'error': 'ppid_not_linked',
            'message': 'No lemma PPID linked to this wallet. Complete platform login/unlock first.',
        }), 404

    try:
        role_profile = _resolve_platform_role_for_ppid(ppid, site_id=site_id)
        from api.real_iam_manager import get_site_manager, get_or_create_site_manager
        site_manager = get_site_manager(site_id, site_id)
        if not site_manager:
            site_manager = get_or_create_site_manager(site_id, site_id)
        permission_id = str(role_profile.get('permission_id') or '').strip() or 'read'
        permission_scope = role_profile.get('scope') or role_profile.get('permissions') or ['read']
        if permission_id not in (site_manager.permissions or {}):
            site_manager.add_permission({
                'permission_id': permission_id,
                'display_name': permission_id.replace('_', ' ').title(),
                'scope': list(permission_scope) if isinstance(permission_scope, list) else [str(permission_scope)],
                'conditions': [],
                'priority': 100 if 'admin' in permission_id else 50,
            })
        custom_claims = {
            'accountType': role_profile['role'],
            'permission_level': role_profile['role'],
            'issued_via': granted_by,
            'intendedPlatform': 'lemma.id',
            'useCase': 'lemma_firewall_runtime' if not granted_by.startswith('agent_ops') else 'agent_ops_runtime',
        }
        if runtime_id:
            custom_claims['runtime_id'] = runtime_id
        if task_id:
            custom_claims['task_id'] = task_id
        metadata = payload.get('metadata')
        if isinstance(metadata, dict):
            for key in ('trust_state', 'taint_epoch', 'resource_bounds', 'constraints', 'scope_preview'):
                if metadata.get(key) is not None:
                    custom_claims[f'agentOps_{key}'] = metadata[key]
        permission_lemma = site_manager.issue_permission_lemma(
            user_did=ppid,
            permission_id=permission_id,
            expiry_days=30,
            custom_claims=custom_claims,
        )
        proof_artifact = _build_firewall_proof_chain_artifact(
            permission_lemma=permission_lemma if isinstance(permission_lemma, dict) else {},
            ppid=ppid,
            site_id=site_id,
            policy_version=policy_version,
            agent_key_id=agent_key_id,
            root_type=root_type,
            org_id=org_id,
            environment=environment,
        )
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'restored_role': role_profile['role'],
            'restored_from': role_profile['source'],
            'credential': permission_lemma,
            'root_proof': proof_artifact.get('root_proof'),
            'delegated_proof': proof_artifact.get('delegated_proof'),
            'proof_chain': proof_artifact.get('proof_chain'),
            'proof_artifact': proof_artifact,
            'root_type': root_type,
            'org_id': org_id,
            'environment': environment,
        })
    except Exception as exc:
        logger.error("wallet_firewall_issue_proof failed: %s", exc)
        return jsonify({
            'success': False,
            'error': 'firewall_issue_proof_failed',
            'message': str(exc),
        }), 500


@wallet_service_bp.route('/api/wallet/runtimes', methods=['GET'])
@wallet_service_bp.route('/api/wallet/firewall/runtimes', methods=['GET'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_runtimes():
    """List Lemma Firewall runtimes connected by this wallet."""
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    org_id, environment = _tenant_context_from_request()
    try:
        runtimes = _list_firewall_runtimes(wallet_id=str(wallet_id), org_id=org_id, environment=environment)
        runtimes_out = [_runtime_to_response_shape(rt) for rt in (runtimes or [])]
        ppid = _resolve_firewall_identity_ppid(str(wallet_id))
        return jsonify({'success': True, 'ppid': ppid, 'org_id': org_id, 'environment': environment, 'runtimes': runtimes_out})
    except Exception as exc:
        logger.error("wallet_firewall_runtimes failed: %s", exc)
        return jsonify({'success': False, 'error': 'firewall_runtime_list_failed'}), 500


@wallet_service_bp.route('/api/wallet/runtimes/<runtime_id>/kill', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/runtimes/<runtime_id>/kill', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_kill(runtime_id: str):
    """Kill switch for an Lemma Firewall runtime connected by this wallet."""
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    normalized_runtime_id = _normalize_runtime_field(runtime_id, 'lemma-firewall-default', max_len=80)
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get('reason') or 'Killed from wallet AIM').strip()[:240]
    org_id, environment = _tenant_context_from_request(payload)
    try:
        changed = _kill_firewall_runtime(
            wallet_id=str(wallet_id),
            runtime_id=normalized_runtime_id,
            reason=reason or 'Killed from wallet AIM',
            org_id=org_id,
            environment=environment,
        )
        if not changed:
            return jsonify({'success': False, 'error': 'runtime_not_found'}), 404
        ppid = _resolve_firewall_identity_ppid(str(wallet_id))
        return jsonify({
            'success': True,
            'runtime_id': normalized_runtime_id,
            'ppid': ppid,
            'org_id': org_id,
            'environment': environment,
            'message': 'Lemma Firewall runtime killed successfully.',
        })
    except Exception as exc:
        logger.error("wallet_firewall_kill failed: %s", exc)
        return jsonify({'success': False, 'error': 'firewall_runtime_kill_failed'}), 500


@wallet_service_bp.route('/api/wallet/runtimes/<runtime_id>/authorize', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/runtimes/<runtime_id>/authorize', methods=['POST'])
@runtime_endpoint_compat
def wallet_firewall_runtime_authorize(runtime_id: str):
    """
    Data-plane runtime authorization gate for proof-first requests.

    Accepts a Lemma credential header, resolves PPID, and confirms the runtime
    is still active for that identity before privileged execution.
    """
    normalized_runtime_id = _normalize_runtime_field(runtime_id, 'lemma-firewall-default', max_len=80)
    payload = request.get_json(silent=True) or {}
    descriptor, descriptor_error = _normalize_runtime_authorize_descriptor(payload)
    if descriptor_error:
        return jsonify({
            'success': False,
            'error': descriptor_error,
            'message': 'Provide a valid action/risk/resource operation descriptor.',
        }), 403
    payload['action'] = descriptor.get('action')
    payload['risk'] = descriptor.get('risk')
    payload['resource'] = descriptor.get('resource')
    org_id, environment = _tenant_context_from_request(payload)
    ppid = _extract_ppid_from_lemma_header()
    trust_claims = _extract_lemma_trust_claims()
    root_type = _normalize_root_type(trust_claims.get("root_type") or payload.get("root_type"))
    credential_ref = str(trust_claims.get("credential_id") or "").strip() or None
    if not ppid:
        _record_runtime_authorize_decision(
            ppid=None,
            runtime_id=normalized_runtime_id,
            decision="deny",
            reason_code="missing_lemma_credential",
            status_code=401,
            trust_state=None,
            taint_epoch=None,
            credential_ref=credential_ref,
            org_id=org_id,
            environment=environment,
            root_type=root_type,
        )
        return jsonify({
            'success': False,
            'error': 'missing_lemma_credential',
            'message': 'Provide X-Lemma-Credential with a valid PPID subject.',
        }), 401
    try:
        runtime = _runtime_record_for_ppid(
            ppid=ppid,
            runtime_id=normalized_runtime_id,
            org_id=org_id,
            environment=environment,
        )
        if not runtime:
            _record_runtime_authorize_decision(
                ppid=ppid,
                runtime_id=normalized_runtime_id,
                decision="deny",
                reason_code="runtime_not_found",
                status_code=404,
                trust_state=None,
                taint_epoch=None,
                credential_ref=credential_ref,
                org_id=org_id,
                environment=environment,
                root_type=root_type,
            )
            return jsonify({
                'success': False,
                'error': 'runtime_not_found',
                'runtime_id': normalized_runtime_id,
                'ppid': ppid,
            }), 404
        if not bool(runtime.get('active')):
            _record_runtime_authorize_decision(
                ppid=ppid,
                runtime_id=normalized_runtime_id,
                decision="deny",
                reason_code="deny_runtime_killed",
                status_code=403,
                trust_state=str(runtime.get('trust_state') or 'clean_internal'),
                taint_epoch=int(runtime.get('taint_epoch') or 0),
                credential_ref=credential_ref,
                org_id=org_id,
                environment=environment,
                root_type=root_type,
            )
            return jsonify({
                'success': False,
                'error': 'runtime_inactive',
                'runtime_id': normalized_runtime_id,
                'ppid': ppid,
                'killed_at': runtime.get('killed_at'),
                'kill_reason': runtime.get('kill_reason'),
            }), 403
        runtime_trust_state = str(runtime.get('trust_state') or 'clean_internal').strip().lower()
        runtime_taint_epoch = int(runtime.get('taint_epoch') or 0)
        privileged = _runtime_authorize_privileged_request(payload, trust_claims)
        if privileged and runtime_trust_state in {'tainted_external', 'privileged_reauth_required'}:
            proof_taint_epoch = trust_claims.get('taint_epoch')
            proof_step_up_required = trust_claims.get('step_up_required')
            if proof_taint_epoch is None or int(proof_taint_epoch) != runtime_taint_epoch:
                _record_runtime_authorize_decision(
                    ppid=ppid,
                    runtime_id=normalized_runtime_id,
                    decision="deny",
                    reason_code="deny_taint_epoch_stale",
                    status_code=403,
                    trust_state=runtime_trust_state,
                    taint_epoch=runtime_taint_epoch,
                    credential_ref=credential_ref,
                    org_id=org_id,
                    environment=environment,
                    root_type=root_type,
                )
                return jsonify({
                    'success': False,
                    'error': 'deny_taint_epoch_stale',
                    'runtime_id': normalized_runtime_id,
                    'ppid': ppid,
                    'trust_state': runtime_trust_state,
                    'taint_epoch': runtime_taint_epoch,
                }), 403
            if proof_step_up_required is not False:
                _record_runtime_authorize_decision(
                    ppid=ppid,
                    runtime_id=normalized_runtime_id,
                    decision="deny",
                    reason_code="deny_trust_state_step_up_required",
                    status_code=403,
                    trust_state=runtime_trust_state,
                    taint_epoch=runtime_taint_epoch,
                    credential_ref=credential_ref,
                    org_id=org_id,
                    environment=environment,
                    root_type=root_type,
                )
                return jsonify({
                    'success': False,
                    'error': 'deny_trust_state_step_up_required',
                    'runtime_id': normalized_runtime_id,
                    'ppid': ppid,
                    'trust_state': runtime_trust_state,
                    'taint_epoch': runtime_taint_epoch,
                }), 403
        _record_runtime_authorize_decision(
            ppid=ppid,
            runtime_id=normalized_runtime_id,
            decision="allow",
            reason_code="allow_runtime_authorized",
            status_code=200,
            trust_state=runtime_trust_state,
            taint_epoch=runtime_taint_epoch,
            credential_ref=credential_ref,
            org_id=org_id,
            environment=environment,
            root_type=root_type,
        )
        return jsonify({
            'success': True,
            'allowed': True,
            'runtime_id': normalized_runtime_id,
            'ppid': ppid,
            'action': payload.get('action'),
            'risk': payload.get('risk'),
            'resource': payload.get('resource'),
            'policy_profile': _normalize_policy_profile_for_response(runtime.get('policy_profile')),
            'risk_defaults': runtime.get('risk_defaults', {}),
            'trust_state': runtime_trust_state,
            'taint_epoch': runtime_taint_epoch,
        })
    except Exception as exc:
        logger.error("wallet_firewall_runtime_authorize failed: %s", exc)
        return jsonify({'success': False, 'error': 'runtime_authorize_failed'}), 500


@wallet_service_bp.route('/api/wallet/runtimes/decisions', methods=['GET'])
@wallet_service_bp.route('/api/wallet/firewall/decisions', methods=['GET'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_decisions():
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404

    runtime_id = _normalize_runtime_field(request.args.get('runtime_id'), '')
    org_id, environment = _tenant_context_from_request()
    delegator_ppid = str(request.args.get('delegator_ppid') or '').strip()
    if delegator_ppid and delegator_ppid != ppid:
        return jsonify({'success': False, 'error': 'delegator_scope_forbidden'}), 403
    effective_ppid = delegator_ppid or ppid
    limit = min(max(int(request.args.get('limit', 100)), 1), 500)
    try:
        decisions = list_agent_ops_decisions(
            delegator_ppid=effective_ppid,
            runtime_id=runtime_id or None,
            limit=limit,
            org_id=org_id,
            environment=environment,
        )
        return jsonify({
            'success': True,
            'ppid': ppid,
            'runtime_id': runtime_id or None,
            'org_id': org_id,
            'environment': environment,
            'delegator_ppid': effective_ppid,
            'decisions': [_decision_to_response_shape(d) for d in (decisions or [])],
        })
    except Exception as exc:
        logger.error("wallet_firewall_decisions failed: %s", exc)
        return jsonify({'success': False, 'error': 'decision_query_failed'}), 500


@wallet_service_bp.route('/api/wallet/runtimes/decisions/export', methods=['GET'])
@wallet_service_bp.route('/api/wallet/firewall/decisions/export', methods=['GET'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_decisions_export():
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404

    runtime_id = _normalize_runtime_field(request.args.get('runtime_id'), '')
    org_id, environment = _tenant_context_from_request()
    delegator_ppid = str(request.args.get('delegator_ppid') or '').strip()
    if delegator_ppid and delegator_ppid != ppid:
        return jsonify({'success': False, 'error': 'delegator_scope_forbidden'}), 403
    effective_ppid = delegator_ppid or ppid

    limit = min(max(int(request.args.get('limit', 500)), 1), 1000)
    export_format = str(request.args.get('format') or 'json').strip().lower()
    if export_format not in {'json', 'csv'}:
        return jsonify({'success': False, 'error': 'invalid_export_format'}), 400

    try:
        decisions = list_agent_ops_decisions(
            delegator_ppid=effective_ppid,
            runtime_id=runtime_id or None,
            limit=limit,
            org_id=org_id,
            environment=environment,
        )
        allow_count = 0
        deny_count = 0
        for decision in decisions:
            decision_value = str(decision.get('decision') or 'deny')
            if decision_value == 'allow':
                allow_count += 1
            else:
                deny_count += 1
    except Exception as exc:
        logger.error("wallet_firewall_decisions_export failed: %s", exc)
        return jsonify({'success': False, 'error': 'decision_export_failed'}), 500

    generated_at = datetime.utcnow().isoformat() + 'Z'
    bundle = {
        'success': True,
        'ppid': ppid,
        'generated_at': generated_at,
        'filters': {
            'runtime_id': runtime_id or None,
            'org_id': org_id,
            'environment': environment,
            'delegator_ppid': effective_ppid,
            'limit': limit,
        },
        'summary': {
            'total': len(decisions),
            'allow': allow_count,
            'deny': deny_count,
        },
        'decisions': [_decision_to_response_shape(d) for d in (decisions or [])],
    }
    if export_format == 'json':
        return jsonify(bundle), 200

    csv_rows = io.StringIO()
    fieldnames = [
        'decision_id',
        'timestamp',
        'credential_ref',
        'action',
        'resource',
        'method',
        'path',
        'status_code',
        'decision',
        'reason_code',
        'policy_profile',
        'runtime_id',
        'delegator_ppid',
        'request_correlation_id',
        'delegation_lineage',
    ]
    writer = csv.DictWriter(csv_rows, fieldnames=fieldnames)
    writer.writeheader()
    for decision in [_decision_to_response_shape(d) for d in (decisions or [])]:
        writer.writerow({name: decision.get(name) for name in fieldnames})

    response = make_response(csv_rows.getvalue(), 200)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=lemma-firewall-decisions-{int(time.time())}.csv'
    return response


@wallet_service_bp.route('/api/wallet/runtimes/decisions/<int:decision_id>/explain', methods=['GET'])
@wallet_service_bp.route('/api/wallet/firewall/decisions/<int:decision_id>/explain', methods=['GET'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_decision_explain(decision_id: int):
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404
    org_id, environment = _tenant_context_from_request()
    try:
        decision = get_agent_ops_decision(
            decision_id=int(decision_id),
            delegator_ppid=ppid,
            org_id=org_id,
            environment=environment,
        )
        if not decision:
            return jsonify({'success': False, 'error': 'decision_not_found'}), 404
        metadata = decision.get('metadata') or {}
        runtime_id = str(decision.get('runtime_id') or '').strip()
        runtime_snapshot = (
            _runtime_record_for_ppid(ppid=ppid, runtime_id=runtime_id, org_id=org_id, environment=environment)
            if runtime_id
            else {}
        )
        status_code = decision.get('status_code')
        reason_code = str(decision.get('reason_code') or '')
        policy_profile = _normalize_policy_profile_for_response(
            str(decision.get('policy_profile') or runtime_snapshot.get('policy_profile') or '')
        )
        explanation = {
            'decision': str(decision.get('decision') or 'deny'),
            'reason_code': reason_code,
            'rule_source': 'runtime_kill_switch' if reason_code in {'POLICY_DENY', 'DENY'} and runtime_snapshot and not runtime_snapshot.get('active') else 'policy_profile',
            'summary': (
                "Runtime is inactive; kill switch denied privileged execution."
                if runtime_snapshot and not runtime_snapshot.get('active')
                else "Decision derived from proof validation, scope checks, and runtime policy state."
            ),
        }
        return jsonify({
            'success': True,
            'ppid': ppid,
            'org_id': org_id,
            'environment': environment,
            'decision': {
                'decision_id': int(decision['decision_id']),
                'timestamp': decision.get('timestamp'),
                'credential_ref': str(decision.get('credential_ref') or ''),
                'action': str(decision.get('action') or ''),
                'resource': str(decision.get('resource') or ''),
                'method': str(decision.get('method') or '').upper(),
                'path': str(decision.get('path') or ''),
                'status_code': status_code,
                'decision': explanation['decision'],
                'reason_code': reason_code,
                'policy_profile': policy_profile,
                'runtime_id': runtime_id or None,
                'request_correlation_id': str(decision.get('request_correlation_id') or ''),
            },
            'policy_snapshot': {
                'policy_profile': policy_profile,
                'runtime': _runtime_to_response_shape(runtime_snapshot) if runtime_snapshot else None,
                'risk_tier': metadata.get('risk_tier'),
                'risk_defaults': runtime_snapshot.get('risk_defaults', {}) if runtime_snapshot else {},
            },
            'explanation': explanation,
        })
    except Exception as exc:
        logger.error("wallet_firewall_decision_explain failed: %s", exc)
        return jsonify({'success': False, 'error': 'decision_explain_failed'}), 500


def wallet_firewall_policy_profiles():
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404
    payload = request.get_json(silent=True) or {}
    org_id, environment = _tenant_context_from_request(payload)
    if request.method == 'GET':
        profiles = list_agent_ops_policy_profiles(org_id=org_id, environment=environment)
        profiles_out = [_policy_profile_to_response_shape(profile) for profile in (profiles or [])]
        return jsonify({'success': True, 'org_id': org_id, 'environment': environment, 'policy_profiles': profiles_out})
    profile_id = _normalize_policy_profile_for_storage(payload.get('policy_profile_id'))
    profile = upsert_agent_ops_policy_profile(
        policy_profile_id=profile_id,
        display_name=str(payload.get('display_name') or profile_id).strip()[:255],
        description=str(payload.get('description') or '').strip()[:2000] or None,
        policy_document=payload.get('policy_document') if isinstance(payload.get('policy_document'), dict) else {},
        policy_version=_normalize_runtime_field(payload.get('policy_version'), 'v1', max_len=64),
        root_type=_normalize_root_type(payload.get('root_type')),
        org_id=org_id,
        environment=environment,
        actor_ref=ppid,
    )
    return jsonify({'success': True, 'org_id': org_id, 'environment': environment, 'policy_profile': _policy_profile_to_response_shape(profile)})


@wallet_service_bp.route('/api/wallet/runtimes/policies', methods=['GET', 'POST'])
@wallet_service_bp.route('/api/wallet/firewall/policies', methods=['GET', 'POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_policies():
    return wallet_firewall_policy_profiles()


@wallet_service_bp.route('/api/wallet/runtimes/policies/<policy_profile_id>/publish', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/policies/<policy_profile_id>/publish', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_policy_publish(policy_profile_id: str):
    payload = request.get_json(silent=True) or {}
    org_id, environment = _tenant_context_from_request(payload)
    policy_version = _normalize_runtime_field(payload.get('policy_version'), 'v1', max_len=64)
    resolved_policy_profile_id = _normalize_policy_profile_for_storage(policy_profile_id)
    changed = publish_agent_ops_policy_profile(
        policy_profile_id=resolved_policy_profile_id,
        policy_version=policy_version,
        org_id=org_id,
        environment=environment,
    )
    if not changed:
        return jsonify({'success': False, 'error': 'policy_profile_not_found'}), 404
    return jsonify({'success': True, 'policy_profile_id': _normalize_policy_profile_for_response(resolved_policy_profile_id), 'policy_version': policy_version, 'org_id': org_id, 'environment': environment})


@wallet_service_bp.route('/api/wallet/runtimes/policies/<policy_profile_id>/rollback', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/policies/<policy_profile_id>/rollback', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_policy_rollback(policy_profile_id: str):
    payload = request.get_json(silent=True) or {}
    org_id, environment = _tenant_context_from_request(payload)
    resolved_policy_profile_id = _normalize_policy_profile_for_storage(policy_profile_id)
    changed = rollback_agent_ops_policy_profile(
        policy_profile_id=resolved_policy_profile_id,
        org_id=org_id,
        environment=environment,
    )
    if not changed:
        return jsonify({'success': False, 'error': 'policy_profile_not_found'}), 404
    return jsonify({'success': True, 'policy_profile_id': _normalize_policy_profile_for_response(resolved_policy_profile_id), 'org_id': org_id, 'environment': environment})


@wallet_service_bp.route('/api/wallet/runtimes/admin/controls', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/admin/controls', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_admin_controls():
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    payload = request.get_json(silent=True) or {}
    org_id, environment = _tenant_context_from_request(payload)
    controls = upsert_agent_ops_org_controls(
        org_id=org_id,
        environment=environment,
        emergency_stop_enabled=bool(payload.get('emergency_stop_enabled', False)),
        quota_json=payload.get('quota_json') if isinstance(payload.get('quota_json'), dict) else {},
        updated_by=ppid or str(wallet_id),
    )
    return jsonify({'success': True, 'controls': controls})


@wallet_service_bp.route('/api/wallet/runtimes/decisions/webhook', methods=['POST'])
@wallet_service_bp.route('/api/wallet/firewall/decisions/webhook', methods=['POST'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_decisions_webhook():
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404
    payload = request.get_json(silent=True) or {}
    org_id, environment = _tenant_context_from_request(payload)
    runtime_id = _normalize_runtime_field(payload.get('runtime_id'), '')
    limit = min(max(int(payload.get('limit') or 100), 1), 1000)
    decisions = list_agent_ops_decisions(
        delegator_ppid=ppid,
        runtime_id=runtime_id or None,
        limit=limit,
        org_id=org_id,
        environment=environment,
    )
    destination_url = str(payload.get('destination_url') or os.getenv('LEMMA_AGENT_OPS_WEBHOOK_URL') or '').strip()
    if not destination_url:
        return jsonify({'success': False, 'error': 'destination_url_required'}), 400
    body = {
        'success': True,
        'org_id': org_id,
        'environment': environment,
        'delegator_ppid': ppid,
        'runtime_id': runtime_id or None,
        'count': len(decisions),
        'decisions': decisions,
    }
    encoded = json.dumps(body).encode('utf-8')
    req = urllib_request.Request(destination_url, method='POST', data=encoded)
    req.add_header('Content-Type', 'application/json')
    secret = str(payload.get('shared_secret') or os.getenv('LEMMA_AGENT_OPS_WEBHOOK_SECRET') or '').strip()
    if secret:
        signature = hmac.new(secret.encode('utf-8'), encoded, hashlib.sha256).hexdigest()
        req.add_header('X-Lemma-Signature-Sha256', signature)
    try:
        with urllib_request.urlopen(req, timeout=5.0) as resp:  # nosec B310
            status_code = int(resp.status or 200)
    except Exception as exc:
        return jsonify({'success': False, 'error': 'webhook_delivery_failed', 'message': str(exc)}), 502
    return jsonify({'success': True, 'status_code': status_code, 'destination_url': destination_url, 'count': len(decisions)})


@wallet_service_bp.route('/api/wallet/runtimes/alerts/summary', methods=['GET'])
@wallet_service_bp.route('/api/wallet/firewall/alerts/summary', methods=['GET'])
@runtime_endpoint_compat
@require_wallet_auth
def wallet_firewall_alerts_summary():
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404

    runtime_id = _normalize_runtime_field(request.args.get('runtime_id'), '')
    deny_window_minutes = min(max(int(request.args.get('deny_window_minutes', 5)), 1), 60)
    baseline_window_minutes = min(max(int(request.args.get('baseline_window_minutes', 60)), 10), 24 * 60)
    target_lag_seconds = float(request.args.get('revocation_target_seconds', 1.0) or 1.0)
    hard_max_lag_seconds = float(request.args.get('revocation_hard_max_seconds', 5.0) or 5.0)

    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        deny_filters = [
            "(COALESCE(ac.authorized_by_ppid, al.metadata->>'delegated_by_ppid') = %s)",
        ]
        deny_params = [ppid]
        if runtime_id:
            deny_filters.append("(al.metadata->>'runtime_id' = %s)")
            deny_params.append(runtime_id)
        deny_query = f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE al.timestamp >= NOW() - (%s * INTERVAL '1 minute')
                ) AS recent_total,
                COUNT(*) FILTER (
                    WHERE al.timestamp >= NOW() - (%s * INTERVAL '1 minute')
                      AND (al.success = FALSE OR COALESCE(al.status_code, 0) >= 400)
                ) AS recent_denies,
                COUNT(*) FILTER (
                    WHERE al.timestamp >= NOW() - ((%s + %s) * INTERVAL '1 minute')
                      AND al.timestamp < NOW() - (%s * INTERVAL '1 minute')
                ) AS baseline_total,
                COUNT(*) FILTER (
                    WHERE al.timestamp >= NOW() - ((%s + %s) * INTERVAL '1 minute')
                      AND al.timestamp < NOW() - (%s * INTERVAL '1 minute')
                      AND (al.success = FALSE OR COALESCE(al.status_code, 0) >= 400)
                ) AS baseline_denies
            FROM agent_audit_log al
            LEFT JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE {' AND '.join(deny_filters)}
        """
        cursor.execute(
            deny_query,
            (
                int(deny_window_minutes),
                int(deny_window_minutes),
                int(deny_window_minutes),
                int(baseline_window_minutes),
                int(deny_window_minutes),
                int(deny_window_minutes),
                int(baseline_window_minutes),
                int(deny_window_minutes),
                *deny_params,
            ),
        )
        deny_row = cursor.fetchone() or (0, 0, 0, 0)
        recent_total = int(deny_row[0] or 0)
        recent_denies = int(deny_row[1] or 0)
        baseline_total = int(deny_row[2] or 0)
        baseline_denies = int(deny_row[3] or 0)
        recent_deny_rate = (recent_denies / recent_total) if recent_total > 0 else 0.0
        baseline_deny_rate = (baseline_denies / baseline_total) if baseline_total > 0 else 0.0
        deny_ratio_vs_baseline = (
            (recent_deny_rate / baseline_deny_rate)
            if baseline_deny_rate > 0
            else (2.0 if recent_deny_rate >= 0.30 else 1.0)
        )
        deny_severity = 'ok'
        if recent_total >= 20 and recent_deny_rate >= 0.60:
            deny_severity = 'critical'
        elif (
            (recent_total >= 10 and recent_deny_rate >= 0.35)
            or (recent_total >= 10 and deny_ratio_vs_baseline >= 2.0 and recent_deny_rate >= 0.25)
        ):
            deny_severity = 'warning'

        revocation_query = """
            SELECT
                COUNT(*) FILTER (WHERE bloom_filter_updated = FALSE) AS pending_count,
                COALESCE(
                    MAX(EXTRACT(EPOCH FROM (NOW() - revoked_at))) FILTER (WHERE bloom_filter_updated = FALSE),
                    0
                ) AS max_pending_lag_seconds,
                COALESCE(
                    AVG(EXTRACT(EPOCH FROM (NOW() - revoked_at))) FILTER (WHERE bloom_filter_updated = FALSE),
                    0
                ) AS avg_pending_lag_seconds
            FROM revocation_list
            WHERE (COALESCE(ppid, '') = %s OR COALESCE(user_did, '') = %s)
        """
        try:
            cursor.execute(revocation_query, (ppid, ppid))
        except Exception:
            # Compatibility fallback for environments where ppid column migration is lagging.
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE bloom_filter_updated = FALSE) AS pending_count,
                    COALESCE(
                        MAX(EXTRACT(EPOCH FROM (NOW() - revoked_at))) FILTER (WHERE bloom_filter_updated = FALSE),
                        0
                    ) AS max_pending_lag_seconds,
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (NOW() - revoked_at))) FILTER (WHERE bloom_filter_updated = FALSE),
                        0
                    ) AS avg_pending_lag_seconds
                FROM revocation_list
                WHERE COALESCE(user_did, '') = %s
                """,
                (ppid,),
            )
        rev_row = cursor.fetchone() or (0, 0, 0)
        pending_count = int(rev_row[0] or 0)
        max_pending_lag_seconds = float(rev_row[1] or 0.0)
        avg_pending_lag_seconds = float(rev_row[2] or 0.0)
        revocation_severity = 'ok'
        if max_pending_lag_seconds > hard_max_lag_seconds:
            revocation_severity = 'critical'
        elif max_pending_lag_seconds > target_lag_seconds:
            revocation_severity = 'warning'

        overall = _max_severity(deny_severity, revocation_severity)
        alerts = []
        if deny_severity != 'ok':
            alerts.append({
                'type': 'deny_spike',
                'severity': deny_severity,
                'message': f"Recent deny rate is {recent_deny_rate:.1%} over last {deny_window_minutes}m.",
            })
        if revocation_severity != 'ok':
            alerts.append({
                'type': 'revocation_lag',
                'severity': revocation_severity,
                'message': (
                    f"Pending revocation lag max={max_pending_lag_seconds:.3f}s "
                    f"(target={target_lag_seconds:.3f}s, hard_max={hard_max_lag_seconds:.3f}s)."
                ),
            })

        return jsonify({
            'success': True,
            'wallet_id': wallet_id,
            'ppid': ppid,
            'runtime_id': runtime_id or None,
            'overall_severity': overall,
            'alerts': alerts,
            'deny_spike': {
                'severity': deny_severity,
                'window_minutes': deny_window_minutes,
                'baseline_window_minutes': baseline_window_minutes,
                'recent_total': recent_total,
                'recent_denies': recent_denies,
                'recent_deny_rate': round(recent_deny_rate, 6),
                'baseline_total': baseline_total,
                'baseline_denies': baseline_denies,
                'baseline_deny_rate': round(baseline_deny_rate, 6),
                'ratio_vs_baseline': round(float(deny_ratio_vs_baseline), 6),
            },
            'revocation_lag': {
                'severity': revocation_severity,
                'pending_count': pending_count,
                'max_pending_lag_seconds': round(max_pending_lag_seconds, 6),
                'avg_pending_lag_seconds': round(avg_pending_lag_seconds, 6),
                'target_seconds': target_lag_seconds,
                'hard_max_seconds': hard_max_lag_seconds,
            },
        })
    except Exception as exc:
        logger.error("wallet_firewall_alerts_summary failed: %s", exc)
        return jsonify({'success': False, 'error': 'firewall_alerts_summary_failed'}), 500
    finally:
        cursor.close()
        conn.close()


@wallet_service_bp.route('/api/wallet/agents/overview', methods=['GET'])
@require_wallet_auth
def wallet_agents_overview():
    """List agents delegated by the wallet owner with recent activity context."""
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({
            'success': False,
            'error': 'ppid_not_linked',
            'message': 'No Lemma PPID found for this wallet yet. Issue at least one agent delegation first.',
        }), 404

    limit = min(max(int(request.args.get('limit', 20)), 1), 100)
    try:
        agents = _load_wallet_agent_overview(ppid=ppid, limit=limit)
        return jsonify({
            'success': True,
            'wallet_id': wallet_id,
            'ppid': ppid,
            'agents': agents,
        })
    except Exception as exc:
        logger.error("wallet_agents_overview failed: %s", exc)
        return jsonify({'success': False, 'error': 'agent_overview_failed'}), 500


@wallet_service_bp.route('/api/wallet/agents/<token_id>/kill', methods=['POST'])
@require_wallet_auth
def wallet_kill_agent(token_id: str):
    """Kill switch: revoke a delegated agent credential by token ID."""
    wallet_id = getattr(g, 'wallet_id', None) or getattr(g, 'user_id', None)
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_context_required'}), 401
    ppid = _resolve_wallet_ppid(str(wallet_id))
    if not ppid:
        return jsonify({'success': False, 'error': 'ppid_not_linked'}), 404

    reason = str((request.get_json(silent=True) or {}).get('reason') or 'Killed from wallet agent monitor').strip()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE agent_credentials
            SET revoked = TRUE, revoked_at = NOW(), revoked_reason = %s
            WHERE token_id = %s AND authorized_by_ppid = %s
            RETURNING id
            """,
            (reason, token_id, ppid),
        )
        updated = cursor.fetchone()
        conn.commit()
        if not updated:
            return jsonify({'success': False, 'error': 'agent_not_found'}), 404
        return jsonify({
            'success': True,
            'token_id': token_id,
            'message': 'Agent revoked successfully.',
        })
    except Exception as exc:
        conn.rollback()
        logger.error("wallet_kill_agent failed: %s", exc)
        return jsonify({'success': False, 'error': 'agent_kill_failed'}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# ROUTES: REVOCATION
# ============================================================================

@wallet_service_bp.route('/api/wallet/revoke', methods=['POST'])
@require_wallet_auth
def revoke_credential():
    """Revoke credential from wallet."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'invalid_request'}), 400
        
        credential_id = data.get('credential_id')
        credential_type = data.get('credential_type', 'unknown')
        credential_scope = data.get('credential_scope', 'site_specific')
        site_domain = data.get('site_domain')
        reason = data.get('reason', 'user_requested')
        
        if not credential_id:
            return jsonify({'success': False, 'error': 'missing_credential_id'}), 400
        
        if credential_scope == 'cross_site' or credential_type == 'poh':
            network_success = await_network_revocation(credential_id, reason)
            
            try:
                from api.revocation_sync import trigger_revocation_sync
                trigger_revocation_sync(credential_id, credential_type, site_id=None)
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'network_wide',
                'network_propagated': network_success
            })
        
        elif _is_site_scoped_credential(credential_type, credential_scope):
            site_success = await_site_revocation(credential_id, reason, site_domain)

            if not site_success:
                return jsonify({
                    'success': False,
                    'error': 'revocation_persist_failed',
                    'credential_id': credential_id,
                    'revocation_type': 'site_specific',
                    'site_domain': site_domain,
                    'message': 'Failed to persist site-specific revocation'
                }), 500
            
            try:
                from api.revocation_sync import trigger_revocation_sync
                trigger_revocation_sync(credential_id, credential_type or 'permission', site_id=site_domain)
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'site_specific',
                'site_updated': site_success,
                'site_domain': site_domain,
                'registry_updated': site_success,
                'bloom_filter_synced': True,
            })
        
        return jsonify({
            'success': True,
            'credential_id': credential_id,
            'revocation_type': 'local_only'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/revocation-status', methods=['GET'])
def get_revocation_status():
    """Get revocation status for credentials."""
    credential_ids = request.args.getlist('credential_ids')
    
    if not credential_ids:
        return jsonify({'success': False, 'error': 'no_credentials'}), 400

    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        statuses = {}
        for cred_id in credential_ids:
            cursor.execute("""
                SELECT
                    COALESCE(credential_id, lemma_id) as cred_id,
                    revoked_at,
                    reason,
                    site_id,
                    lemma_type
                FROM revocation_list
                WHERE COALESCE(credential_id, lemma_id) = %s
                ORDER BY revoked_at DESC
                LIMIT 1
            """, (cred_id,))

            row = cursor.fetchone()
            if row:
                _, revoked_at, reason, site_id, lemma_type = row
                scope = 'global' if lemma_type == 'poh' else 'site_specific'
                statuses[cred_id] = {
                    'revoked': True,
                    'revocation_time': revoked_at.isoformat() if revoked_at else None,
                    'reason': reason,
                    'scope': scope,
                    'site_id': site_id
                }
            else:
                statuses[cred_id] = {
                    'revoked': False,
                    'revocation_time': None,
                    'reason': None,
                    'scope': 'unknown',
                    'site_id': None
                }
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': True, 'statuses': statuses})


@wallet_service_bp.route('/api/wallet/revoke-user', methods=['POST'])
@require_wallet_auth
def revoke_user():
    """
    Revoke ALL credentials for a user (PPID) on ONE SITE across ALL devices.
    
    This adds the user's PPID to the Bloom filter, which invalidates
    ALL credentials for that user on that site regardless of which device they're on.
    
    Use this when:
    - Site admin bans a user from their site
    - User requests access removal from a specific site
    
    For global revocation (all sites), use /api/wallet/revoke-wallet instead.
    
    Request body:
        ppid: The user's PPID (site-specific identifier)
        site_id: The site this PPID belongs to
        reason: Reason for revocation
    """
    try:
        data = request.get_json() or {}
        ppid = data.get('ppid')
        site_id = data.get('site_id')
        reason = data.get('reason', 'user_revocation')
        
        if not ppid:
            return jsonify({'success': False, 'error': 'ppid required'}), 400
        
        if not site_id:
            return jsonify({'success': False, 'error': 'site_id required'}), 400

        from api.database import get_db
        from api.site_ppid_revocation import revoke_site_bound_ppid

        db = get_db()
        try:
            result = revoke_site_bound_ppid(
                db,
                site_id=site_id,
                ppid=ppid,
                reason=reason,
                revoked_by='api',
            )

            already_revoked = not result.get("block_created") and not result.get("revocation_created")
            logger.info(f"🚫 User revoked: PPID {ppid[:12]}... for site {site_id}")

            return jsonify({
                'success': True,
                'already_revoked': already_revoked,
                'ppid': ppid,
                'site_id': site_id,
                'revocation_type': 'user',
                'event_published': result.get('event_published', False),
                'message': (
                    'User already revoked for this site'
                    if already_revoked
                    else 'User revoked across all devices for this site.'
                ),
                'note': 'Connected clients can receive revocation events immediately; hourly sync remains fallback.'
            })

        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"User revocation failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/revoke-wallet', methods=['POST'])
def revoke_wallet():
    """
    Revoke ALL credentials for a wallet across ALL sites and ALL devices.
    
    This is the nuclear option - use for:
    - Account deletion requests
    - Compromised wallet (device lost with passkey deleted)
    - Security incidents requiring immediate full lockout
    
    This adds the wallet_id to the global Bloom filter, which invalidates
    ALL credentials for that wallet on EVERY site.
    
    Request body:
        wallet_id: The wallet identifier to revoke
        reason: Reason for revocation
        
    Security: Requires authenticated session OR admin API key
    """
    try:
        data = request.get_json() or {}
        wallet_id = data.get('wallet_id')
        reason = data.get('reason', 'wallet_revocation')
        
        if not wallet_id:
            return jsonify({'success': False, 'error': 'wallet_id required'}), 400
        
        # Security: Verify caller is authorized
        # Wallet-level bans are SERIOUS - only allow:
        # 1. Wallet owner (self-revoke for account deletion)
        # 2. Lemma.id platform admin (fraud/abuse cases)
        
        session_wallet_id = None
        try:
            session_token = request.cookies.get(SESSION_COOKIE_NAME)
            if session_token:
                session_data = validate_session_token(session_token)
                if session_data:
                    session_wallet_id = session_data.get('wallet_id')
        except:
            pass
        
        # Check for platform admin - requires LEMMA_ADMIN_KEY env var match
        admin_key = os.environ.get('LEMMA_ADMIN_KEY', '')
        provided_key = request.headers.get('X-Admin-Key', '')
        is_admin = admin_key and provided_key and hmac.compare_digest(admin_key, provided_key)
        
        # Wallet owner can self-revoke (account deletion)
        is_owner = session_wallet_id == wallet_id
        
        if not is_admin and not is_owner:
            logger.warning(f"🚫 Unauthorized wallet revocation attempt for {wallet_id[:12]}...")
            return jsonify({
                'success': False, 
                'error': 'Unauthorized - wallet-level bans require owner session or platform admin'
            }), 403
        
        # Log who is doing the ban
        if is_admin:
            logger.warning(f"⚠️ ADMIN wallet ban initiated for {wallet_id[:12]}... Reason: {reason}")
        
        # Add wallet_id to revocation list with revocation_type='wallet'
        from api.database import get_db, RevocationList
        from datetime import datetime
        
        db = get_db()
        try:
            # Check if already revoked
            existing = db.query(RevocationList).filter(
                RevocationList.wallet_id == wallet_id,
                RevocationList.revocation_type == 'wallet'
            ).first()
            
            if existing:
                return jsonify({
                    'success': True,
                    'already_revoked': True,
                    'message': 'Wallet already revoked globally'
                })
            
            # Create new revocation entry. Admin/governance bans are sticky
            # (is_amnesty_eligible=False) so a fresh IDV cannot self-lift a
            # coordinated-fraud kill; owner self-revocations stay amnesty-eligible
            # so the owner can recover by re-proving identity.
            revocation = RevocationList(
                lemma_id=f"wallet:{wallet_id}",
                credential_id=f"wallet:{wallet_id}",
                wallet_id=wallet_id,
                revocation_type='wallet',  # Wallet-level revocation (all sites)
                reason=reason,
                revoked_at=datetime.utcnow(),
                revoked_by='owner' if is_owner else 'admin',
                is_amnesty_eligible=bool(is_owner),
            )
            
            db.add(revocation)
            db.commit()
            
            logger.info(f"🔐 GLOBAL REVOCATION: Wallet {wallet_id[:12]}... revoked across ALL sites")
            
            # Audit log
            try:
                from api.audit_logger import log_event, AuditEvent
                log_event(
                    AuditEvent.CREDENTIAL_REVOKED,
                    details={
                        'wallet_id': wallet_id,
                        'revocation_type': 'wallet',
                        'scope': 'global',
                        'reason': reason
                    }
                )
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'wallet_id': wallet_id,
                'revocation_type': 'wallet',
                'scope': 'global',
                'message': 'Wallet revoked globally. ALL credentials on ALL sites are now invalid.',
                'note': 'Bloom filter will sync within 1 hour. Immediate effect on new verifications.'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Wallet revocation failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ROUTES: WALLET TRANSFER
# ============================================================================

@wallet_service_bp.route('/api/wallet/transfer/create-session', methods=['POST', 'OPTIONS'])
def create_transfer_session():
    """Create a new wallet transfer session."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not validate_session_token(session_token):
        return cross_origin_response({'success': False, 'error': 'not_authenticated'}, 401)
    
    if not _validate_csrf():
        return cross_origin_response({'success': False, 'error': 'csrf_missing_or_invalid'}, 403)
    
    data = request.get_json()
    if not data or 'device_id' not in data:
        return cross_origin_response({'success': False, 'error': 'Missing device_id'}, 400)
    
    transfer = TransferSession(data['device_id'], data.get('wallet_data'))
    
    session_data = {
        'session_id': transfer.session_id,
        'source_device_id': transfer.source_device_id,
        'transfer_key': transfer.transfer_key,
        'created_at': transfer.created_at.isoformat(),
        'expires_at': transfer.expires_at.isoformat(),
        'wallet_data': transfer.wallet_data,
        'status': transfer.status,
        'target_device_id': transfer.target_device_id
    }
    
    if not _storage.set_session(transfer.session_id, session_data):
        return cross_origin_response({'success': False, 'error': 'Failed to store session'}, 500)
    
    return cross_origin_response({
        'success': True,
        'session_id': transfer.session_id,
        'qr_data': transfer.to_qr_data(),
        'expires_at': int(transfer.expires_at.timestamp() * 1000)
    })


@wallet_service_bp.route('/api/wallet/transfer/set-wallet', methods=['POST', 'OPTIONS'])
def set_wallet_data():
    """Set wallet data for transfer session."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not validate_session_token(session_token):
        return cross_origin_response({'success': False, 'error': 'not_authenticated'}, 401)
    
    if not _validate_csrf():
        return cross_origin_response({'success': False, 'error': 'csrf_missing_or_invalid'}, 403)
    
    data = request.get_json()
    if not data or 'session_id' not in data or 'wallet_data' not in data:
        return cross_origin_response({'success': False, 'error': 'Missing session_id or wallet_data'}, 400)

    wallet_data = data.get('wallet_data')
    payload_len = len(json.dumps(wallet_data, default=str)) if wallet_data is not None else 0
    max_payload = _wallet_transfer_max_payload_bytes()
    if payload_len > max_payload:
        logger.warning("wallet transfer payload rejected: size=%s max=%s", payload_len, max_payload)
        return cross_origin_response({'success': False, 'error': 'wallet_data_too_large'}, 413)

    if not _wallet_transfer_plaintext_allowed():
        if _payload_contains_sensitive_wallet_keys(wallet_data):
            logger.warning("wallet transfer payload rejected: sensitive keys present while plaintext disabled")
            return cross_origin_response({'success': False, 'error': 'wallet_data_plaintext_not_allowed'}, 400)
    
    session_data = _storage.get_session(data['session_id'])
    if not session_data:
        return cross_origin_response({'success': False, 'error': 'Transfer session not found'}, 404)
    
    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if datetime.now() > expires_at:
        _storage.delete_session(data['session_id'])
        return cross_origin_response({'success': False, 'error': 'Transfer session expired'}, 410)
    
    session_data['wallet_data'] = wallet_data
    session_data['status'] = 'ready'
    _storage.set_session(data['session_id'], session_data)
    
    return cross_origin_response({'success': True, 'status': 'ready'})


@wallet_service_bp.route('/api/wallet/transfer/get-wallet', methods=['POST', 'OPTIONS'])
def get_wallet_data():
    """Get wallet data from transfer session."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    data = request.get_json()
    if not data or 'session_id' not in data or 'transfer_key' not in data:
        return cross_origin_response({'success': False, 'error': 'Missing session_id or transfer_key'}, 400)
    
    session_data = _storage.get_session(data['session_id'])
    if not session_data:
        return cross_origin_response({'success': False, 'error': 'Transfer session not found'}, 404)
    
    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if datetime.now() > expires_at:
        _storage.delete_session(data['session_id'])
        return cross_origin_response({'success': False, 'error': 'Transfer session expired'}, 410)
    
    if session_data['transfer_key'] != data['transfer_key']:
        return cross_origin_response({'success': False, 'error': 'Invalid transfer key'}, 403)
    
    if not session_data['wallet_data']:
        return cross_origin_response({'success': False, 'error': 'Wallet data not ready yet'}, 202)

    if (not _wallet_transfer_plaintext_allowed()) and _payload_contains_sensitive_wallet_keys(session_data['wallet_data']):
        logger.warning("wallet transfer retrieval blocked: sensitive payload present while plaintext disabled")
        return cross_origin_response({'success': False, 'error': 'wallet_data_plaintext_not_allowed'}, 400)
    
    session_data['status'] = 'completed'
    session_data['target_device_id'] = data.get('target_device_id', 'unknown')
    _storage.set_session(data['session_id'], session_data)
    
    return cross_origin_response({
        'success': True,
        'wallet_data': session_data['wallet_data'],
        'transfer_completed': True
    })


# ============================================================================
# ROUTES: PIN RESET
# ============================================================================

@wallet_service_bp.route('/api/wallet/pin-reset/request', methods=['POST'])
def request_pin_reset():
    """Request PIN reset - sends email with reset link."""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        
        if not email or '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'invalid_email'}), 400
        
        from api.ppid import derive_ppid_did
        user_did = derive_ppid_did(email, "lemma.id")
        
        reset_token = secrets.token_urlsafe(32)
        _reset_tokens[reset_token] = {
            'email': email,
            'user_did': user_did,
            'created_at': int(time.time())
        }
        
        reset_url = f"{request.host_url}wallet/reset-pin?token={reset_token}"
        
        from api.email_service import send_email
        html = f"""
        <html><body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px;">
            <h1>Lemma Wallet PIN Reset</h1>
            <p>You requested to reset your Lemma Wallet PIN.</p>
            <a href="{reset_url}" style="display: inline-block; background: #2563eb; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px;">Reset Your PIN</a>
            <p style="margin-top: 24px; color: #666;">This link expires in 1 hour.</p>
        </body></html>
        """
        
        result = send_email(to=email, subject='Lemma Wallet PIN Reset', html=html, text=f'Reset your PIN: {reset_url}')
        
        if result['success']:
            return jsonify({'success': True, 'message': 'Reset email sent'})
        return jsonify({'success': False, 'error': 'email_send_failed'}), 500
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/pin-reset/verify', methods=['POST'])
def verify_reset_token():
    """Verify reset token is valid."""
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    
    if not token or token not in _reset_tokens:
        return jsonify({'success': False, 'error': 'invalid_token'}), 400
    
    token_data = _reset_tokens[token]
    if int(time.time()) - token_data['created_at'] > TOKEN_EXPIRY:
        del _reset_tokens[token]
        return jsonify({'success': False, 'error': 'token_expired'}), 400
    
    return jsonify({
        'success': True,
        'email': token_data['email'],
        'user_did': token_data['user_did']
    })


@wallet_service_bp.route('/api/wallet/pin-reset/complete', methods=['POST'])
def complete_pin_reset():
    """Complete PIN reset."""
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    new_pin = data.get('new_pin', '').strip()
    
    if not token or not new_pin:
        return jsonify({'success': False, 'error': 'missing_fields'}), 400
    
    if len(new_pin) != 4 or not new_pin.isdigit():
        return jsonify({'success': False, 'error': 'invalid_pin'}), 400
    
    if token not in _reset_tokens:
        return jsonify({'success': False, 'error': 'invalid_token'}), 400
    
    token_data = _reset_tokens[token]
    if int(time.time()) - token_data['created_at'] > TOKEN_EXPIRY:
        del _reset_tokens[token]
        return jsonify({'success': False, 'error': 'token_expired'}), 400
    
    del _reset_tokens[token]
    
    return jsonify({
        'success': True,
        'message': 'PIN reset successful',
        'email': token_data['email']
    })


# ============================================================================
# ROUTES: MULTI-LEMMA SYNC
# ============================================================================

@wallet_service_bp.route('/api/wallet-sync/create-qr-auth', methods=['POST'])
def create_qr_auth_lemma():
    """Create QR Authentication Lemma for device sync."""
    if not MULTI_LEMMA_AVAILABLE:
        return jsonify({'success': False, 'error': 'multi_lemma_engine_not_available'}), 500
    
    try:
        import qrcode
        
        data = request.get_json()
        mobile_device_did = data.get('mobile_device_did')
        requesting_device_did = data.get('requesting_device_did')
        requested_scope = data.get('requested_scope', ['federated_identity'])
        requested_duration = data.get('requested_duration', 86400)
        device_fingerprint = data.get('device_fingerprint', 'unknown')
        
        if not mobile_device_did or not requesting_device_did:
            return jsonify({'success': False, 'error': 'missing_required_fields'}), 400
        
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        mobile_issuer = issuer_manager.get_multi_lemma_issuer('qr_authentication')
        qr_sync_manager = PyQRSyncManager()
        
        qr_start = time.perf_counter_ns()
        qr_lemma_json = qr_sync_manager.create_qr_auth_lemma(
            mobile_issuer, requesting_device_did, requested_scope,
            requested_duration, device_fingerprint
        )
        qr_time_ns = time.perf_counter_ns() - qr_start
        
        qr_data = qr_sync_manager.generate_qr_data(qr_lemma_json)
        
        qr_img = qrcode.QRCode(version=1, box_size=10, border=5)
        qr_img.add_data(qr_data)
        qr_img.make(fit=True)
        
        img = qr_img.make_image(fill_color="black", back_color="white")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        qr_lemma = json.loads(qr_lemma_json)
        
        return jsonify({
            'success': True,
            'qr_auth_lemma': qr_lemma,
            'qr_data': qr_data,
            'qr_image_base64': f"data:image/png;base64,{img_base64}",
            'creation_time_ns': qr_time_ns
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-sync/verify-qr-auth', methods=['POST'])
def verify_qr_auth_lemma():
    """Verify QR Authentication Lemma."""
    if not MULTI_LEMMA_AVAILABLE:
        return jsonify({'success': False, 'error': 'multi_lemma_engine_not_available'}), 500
    
    try:
        data = request.get_json()
        qr_data = data.get('qr_data')
        
        if not qr_data:
            return jsonify({'success': False, 'error': 'qr_data_required'}), 400
        
        qr_sync_manager = PyQRSyncManager()
        qr_lemma_json = qr_sync_manager.parse_qr_data(qr_data)
        qr_result = qr_sync_manager.verify_qr_auth_lemma(qr_lemma_json)
        
        if qr_result.valid and qr_result.sync_authorized:
            delegation_lemma = None
            if qr_result.delegation_lemma_json:
                delegation_lemma = json.loads(qr_result.delegation_lemma_json)
            
            return jsonify({
                'success': True,
                'qr_verification': {
                    'valid': qr_result.valid,
                    'sync_authorized': qr_result.sync_authorized
                },
                'delegation_lemma': delegation_lemma
            })
        
        return jsonify({
            'success': False,
            'error': 'qr_verification_failed',
            'reason': qr_result.reason
        }), 401
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-sync/health', methods=['GET'])
def wallet_sync_health():
    """Health check for multi-lemma sync."""
    return jsonify({
        'status': 'ready' if MULTI_LEMMA_AVAILABLE else 'unavailable',
        'multi_lemma_engine': MULTI_LEMMA_AVAILABLE
    })


# ============================================================================
# EXPORTS
# ============================================================================

# Export for backwards compatibility
def get_wallet_auth_script():
    """Returns JavaScript for auto-attaching wallet auth."""
    return '''
<script>
(function() {
    const originalFetch = window.fetch;
    window.fetch = async function(url, options = {}) {
        if (url.startsWith('/api/') && window.lemmaWallet?.isUnlocked?.()) {
            try {
                const authProof = await window.lemmaWallet.getAuthProof();
                options.headers = options.headers || {};
                options.headers['X-Wallet-Auth'] = JSON.stringify(authProof);
            } catch (e) {}
        }
        return originalFetch(url, options);
    };
})();
</script>
'''
