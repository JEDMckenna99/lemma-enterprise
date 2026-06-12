"""
Agent Credentials API
Enables passkey-authorized, time-limited access for AI coding agents.

SECURITY MODEL:
1. Human authenticates with passkey (cannot be faked by AI)
2. Human issues credential with scope and TTL
3. Agent includes credential in X-Agent-Token header
4. Server validates on every request
5. Human can revoke at any time

WHY THIS IS SECURE:
- Passkey = hardware-bound biometric proof of human presence
- Time-limited = credentials auto-expire
- Scoped = agents can only do what's explicitly allowed
- Task-bound = agents can only access paths relevant to their task
- Audited = every agent action is logged with deviation tracking
- Revocable = human maintains kill switch
"""

import os
import re
import json
import base64
import secrets
import hashlib
import hmac
import logging
import html
import queue
import threading
import time
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, g, session, make_response
from api.authz_engine import extract_user_lemma_principal
from api.authz_policy import get_policy_for_request
from api.authz.mode_policy import evaluate_mode_policy
from api.authz.replay import validate_pop_replay
from api.authz.verifier import evaluate_proof_native
from api.authz.freshness import is_fresh_enough
from auth.redis_store import (
    store as redis_store,
    get as redis_get,
    delete as redis_delete,
    get_redis_client,
)

from auth.rate_limiter import rate_limit, credential_issue_limit, get_issuance_identifier
from api.agent_ops_store import (
    owned_sites_for_principal,
    record_decision_logs,
    record_delegation,
    record_revocation,
    revoke_delegation_for_token,
)

logger = logging.getLogger(__name__)

agent_credentials_bp = Blueprint('agent_credentials', __name__)


def _tenant_value(value: str | None, fallback: str, max_len: int = 120) -> str:
    cleaned = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"-", "_", "."})
    cleaned = cleaned[:max_len]
    return cleaned or fallback


@agent_credentials_bp.before_request
def _enforce_agent_tenant_context():
    g.org_id = _tenant_value(request.headers.get("X-Lemma-Org-Id") or request.args.get("org_id"), "org_default", 120)
    env = _tenant_value(request.headers.get("X-Lemma-Environment") or request.args.get("environment"), "prod", 32)
    g.environment = env if env in {"dev", "staging", "prod"} else "prod"

DEFAULT_DELEGATION_ALLOWED_PERMISSIONS = 'admin_access,super_admin_access'
DEFAULT_DELEGATION_ALLOWED_ROLES = 'admin,super_admin'
CLI_LOGIN_RESULT_TTL_SECONDS = 600
CLI_LOGIN_RESULT_KEY_PREFIX = "agent_cli_login:result"
DEFAULT_ADMIN_ALLOWED_PATHS = [
    '/api/agent/**',
    '/api/admin/**',
    '/api/developer/**',
    '/api/v1/iam/**',
    '/api/platform/**',
]
DEFAULT_ADMIN_MAX_OPERATIONS = 500
_TOKEN_VALIDATION_CACHE: dict[str, dict] = {}
_TOKEN_VALIDATION_CACHE_LOCK = threading.Lock()
_TOKEN_VALIDATION_CACHE_MAX = 5000
_AUDIT_QUEUE_MAX = 5000
_AUDIT_BATCH_SIZE = 50
_AUDIT_BATCH_WAIT_SECONDS = 0.25
_AUDIT_QUEUE: "queue.Queue[dict]" = queue.Queue(maxsize=_AUDIT_QUEUE_MAX)
_AUDIT_WORKER_STARTED = False
_AUDIT_WORKER_LOCK = threading.Lock()
_PROOF_REVOCATION_CACHE: dict[str, dict] = {}
_PROOF_REVOCATION_CACHE_LOCK = threading.Lock()


def _revocation_id_shape(value: str) -> tuple[str | None, str | None]:
    ref = str(value or "").strip()
    lowered = ref.lower()
    if not ref:
        return None, None
    if lowered.startswith(("dpf_", "prf_", "proof_")):
        return ref, None
    if lowered.startswith(("rgr_", "wkr_", "plr_", "root_grant_")):
        return None, ref
    if ":" in ref:
        prefix, _, suffix = ref.partition(":")
        normalized = suffix.strip()
        prefix_l = prefix.strip().lower()
        if prefix_l == "proof" and normalized:
            return normalized, None
        if prefix_l in {"root_grant", "grant", "workload_root", "policy_root"} and normalized:
            return None, normalized
    return None, None


def _proof_revocation_context(org_id: str, environment: str) -> tuple[set[str], set[str], int]:
    cache_key = f"{str(org_id or 'org_default').strip().lower()}::{str(environment or 'prod').strip().lower()}"
    now_mono = time.monotonic()
    with _PROOF_REVOCATION_CACHE_LOCK:
        cached = _PROOF_REVOCATION_CACHE.get(cache_key)
        if isinstance(cached, dict) and float(cached.get("expires_monotonic") or 0.0) > now_mono:
            return (
                set(cached.get("revoked_proof_ids") or set()),
                set(cached.get("revoked_root_grant_ids") or set()),
                int(cached.get("min_revocation_epoch") or 0),
            )
    revoked_proof_ids: set[str] = set()
    revoked_root_grant_ids: set[str] = set()
    min_revocation_epoch = 0
    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, COALESCE(credential_id, lemma_id) AS credential_ref
                FROM revocation_list
                ORDER BY id DESC
                LIMIT 1000
                """
            )
            for row in cursor.fetchall() or []:
                row_id = int(row[0] or 0)
                if row_id > min_revocation_epoch:
                    min_revocation_epoch = row_id
                proof_id, root_grant_id = _revocation_id_shape(str(row[1] or "").strip())
                if proof_id:
                    revoked_proof_ids.add(proof_id)
                if root_grant_id:
                    revoked_root_grant_ids.add(root_grant_id)
            cursor.execute(
                """
                SELECT id, subject_ref
                FROM agent_ops_revocations
                WHERE org_id = %s AND environment = %s
                ORDER BY id DESC
                LIMIT 1000
                """,
                (cache_key.split("::", 1)[0], cache_key.split("::", 1)[1]),
            )
            for row in cursor.fetchall() or []:
                row_id = int(row[0] or 0)
                if row_id > min_revocation_epoch:
                    min_revocation_epoch = row_id
                proof_id, root_grant_id = _revocation_id_shape(str(row[1] or "").strip())
                if proof_id:
                    revoked_proof_ids.add(proof_id)
                if root_grant_id:
                    revoked_root_grant_ids.add(root_grant_id)
        finally:
            cursor.close()
            conn.close()
    except Exception:
        logger.debug("proof revocation context query failed", exc_info=True)

    ttl_seconds = max(1, int(os.environ.get("LEMMA_PROOF_REVOCATION_CACHE_SECONDS", "5") or "5"))
    with _PROOF_REVOCATION_CACHE_LOCK:
        _PROOF_REVOCATION_CACHE[cache_key] = {
            "revoked_proof_ids": set(revoked_proof_ids),
            "revoked_root_grant_ids": set(revoked_root_grant_ids),
            "min_revocation_epoch": int(min_revocation_epoch),
            "expires_monotonic": now_mono + ttl_seconds,
        }
    return revoked_proof_ids, revoked_root_grant_ids, min_revocation_epoch


def _agent_auth_fast_path_ttl_ms() -> int:
    raw = str(os.environ.get('LEMMA_AGENT_AUTH_FAST_PATH_TTL_MS', '0') or '0').strip()
    try:
        value = int(raw)
    except ValueError:
        value = 0
    return max(0, value)


def _evict_cached_agent_token(token_hash: str) -> None:
    if not token_hash:
        return
    with _TOKEN_VALIDATION_CACHE_LOCK:
        _TOKEN_VALIDATION_CACHE.pop(token_hash, None)


def _get_cached_agent_token(token_hash: str):
    ttl_ms = _agent_auth_fast_path_ttl_ms()
    if ttl_ms <= 0 or not token_hash:
        return None
    now_mono = time.monotonic()
    now_utc = datetime.now(timezone.utc)
    with _TOKEN_VALIDATION_CACHE_LOCK:
        entry = _TOKEN_VALIDATION_CACHE.get(token_hash)
        if not entry:
            return None
        if float(entry.get('expires_monotonic', 0.0)) <= now_mono:
            _TOKEN_VALIDATION_CACHE.pop(token_hash, None)
            return None
        cached = entry.get('credential_info')
    if not isinstance(cached, dict):
        return None
    expires_at = cached.get('expires_at')
    if isinstance(expires_at, datetime):
        expires_utc = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if expires_utc <= now_utc:
            _evict_cached_agent_token(token_hash)
            return None
    hydrated = dict(cached)
    hydrated['validation_cache_hit'] = True
    return hydrated


def _set_cached_agent_token(token_hash: str, credential_info: dict) -> None:
    ttl_ms = _agent_auth_fast_path_ttl_ms()
    if ttl_ms <= 0 or not token_hash or not isinstance(credential_info, dict):
        return
    now_utc = datetime.now(timezone.utc)
    now_mono = time.monotonic()
    effective_ttl_ms = ttl_ms
    expires_at = credential_info.get('expires_at')
    if isinstance(expires_at, datetime):
        expires_utc = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        remaining_ms = int((expires_utc - now_utc).total_seconds() * 1000)
        effective_ttl_ms = min(effective_ttl_ms, max(0, remaining_ms - 1000))
    if effective_ttl_ms <= 0:
        return
    item = {
        'expires_monotonic': now_mono + (effective_ttl_ms / 1000.0),
        'credential_info': dict(credential_info),
    }
    with _TOKEN_VALIDATION_CACHE_LOCK:
        if len(_TOKEN_VALIDATION_CACHE) >= _TOKEN_VALIDATION_CACHE_MAX:
            _TOKEN_VALIDATION_CACHE.clear()
        _TOKEN_VALIDATION_CACHE[token_hash] = item


def _set_cached_agent_token_runtime(token_hash: str, credential_info: dict) -> None:
    ttl_ms = _agent_auth_fast_path_ttl_ms()
    if ttl_ms <= 0 or not token_hash or not isinstance(credential_info, dict):
        return
    with _TOKEN_VALIDATION_CACHE_LOCK:
        entry = _TOKEN_VALIDATION_CACHE.get(token_hash)
        if not entry:
            return
        entry['credential_info'] = dict(credential_info)


def _apply_operation_quota(credential_info: dict) -> tuple[dict | None, str | None]:
    info = dict(credential_info or {})
    current_use_count = int(info.get('use_count') or 0)
    max_operations = info.get('max_operations')
    if max_operations is None:
        info['use_count'] = current_use_count + 1
        info['quota_source'] = 'local'
        return info, None

    credential_id = info.get('credential_id')
    base_use_count = int(info.get('base_use_count') or current_use_count)
    redis_client = get_redis_client()
    if redis_client and credential_id:
        key = f"lemma:agent_usage_delta:{credential_id}"
        try:
            delta = int(redis_client.incr(key))
            if delta == 1:
                expires_at = info.get('expires_at')
                ttl_seconds = 3600
                if isinstance(expires_at, datetime):
                    expires_utc = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
                    ttl_seconds = max(60, int((expires_utc - datetime.now(timezone.utc)).total_seconds()) + 120)
                redis_client.expire(key, ttl_seconds)
            effective_use_count = base_use_count + delta
            if effective_use_count > int(max_operations):
                return None, 'max_operations_exceeded'
            info['use_count'] = effective_use_count
            info['quota_source'] = 'redis'
            return info, None
        except Exception as exc:
            logger.warning(f"Redis usage counter failed; falling back to local counter: {exc}")

    effective_use_count = current_use_count + 1
    if effective_use_count > int(max_operations):
        return None, 'max_operations_exceeded'
    info['use_count'] = effective_use_count
    info['quota_source'] = 'local'
    return info, None


def _attach_authz_timing_headers(
    response,
    started_at: float,
    credential_info: dict | None = None,
    elapsed_ms_override: float | None = None,
):
    if elapsed_ms_override is None:
        elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
    else:
        elapsed_ms = max(0.0, float(elapsed_ms_override))
    response.headers['X-Lemma-Authz-Latency-Ms'] = f"{elapsed_ms:.3f}"
    cache_hit = bool((credential_info or {}).get('validation_cache_hit'))
    response.headers['X-Lemma-Authz-Cache'] = 'hit' if cache_hit else 'miss'
    response.headers['Server-Timing'] = f"lemma_authz;dur={elapsed_ms:.2f}"
    return response


def _async_audit_enabled() -> bool:
    raw = str(os.environ.get('LEMMA_ASYNC_AUDIT_LOGGING', '1') or '1').strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def _shadow_proof_eval_enabled() -> bool:
    raw = str(os.environ.get('LEMMA_AUTHZ_PROOF_SHADOW', '1') or '1').strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def _proof_base_url() -> str:
    return str(os.environ.get('LEMMA_BASE_URL') or os.environ.get('PUBLIC_BASE_URL') or 'https://lemma.id').strip()


def _write_agent_audit_events(events: list[dict]) -> None:
    if not events:
        return
    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO agent_audit_log
            (credential_id, token_id, action, resource, method, path, status_code, success,
             path_allowed, task_deviation, deviation_reason, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    event.get('credential_id'),
                    event.get('token_id'),
                    event.get('action'),
                    event.get('resource'),
                    event.get('method'),
                    event.get('path'),
                    event.get('status_code'),
                    event.get('success'),
                    event.get('path_allowed'),
                    event.get('task_deviation'),
                    event.get('deviation_reason'),
                    event.get('metadata_json'),
                )
                for event in events
            ],
        )
        conn.commit()
        cursor.close()
        conn.close()
        record_decision_logs(events)
    except Exception as exc:
        logger.warning(f"Failed to write agent audit batch ({len(events)} events): {exc}")


def _audit_worker_loop() -> None:
    pending: list[dict] = []
    while True:
        try:
            first = _AUDIT_QUEUE.get(timeout=_AUDIT_BATCH_WAIT_SECONDS)
            pending.append(first)
        except queue.Empty:
            pass
        try:
            while len(pending) < _AUDIT_BATCH_SIZE:
                pending.append(_AUDIT_QUEUE.get_nowait())
        except queue.Empty:
            pass
        if pending:
            _write_agent_audit_events(pending)
            pending = []


def _ensure_audit_worker_started() -> None:
    global _AUDIT_WORKER_STARTED
    if _AUDIT_WORKER_STARTED:
        return
    with _AUDIT_WORKER_LOCK:
        if _AUDIT_WORKER_STARTED:
            return
        worker = threading.Thread(target=_audit_worker_loop, daemon=True, name='lemma-audit-worker')
        worker.start()
        _AUDIT_WORKER_STARTED = True


def _enqueue_audit_event(event: dict) -> bool:
    if not _async_audit_enabled():
        return False
    _ensure_audit_worker_started()
    try:
        _AUDIT_QUEUE.put_nowait(event)
        return True
    except queue.Full:
        logger.warning("Agent audit queue full; falling back to sync write")
        return False


def _decision_receipt_secret() -> str:
    return (
        os.environ.get('LEMMA_DECISION_RECEIPT_SECRET')
        or os.environ.get('SESSION_SECRET')
        or os.environ.get('SECRET_KEY')
        or 'lemma-decision-dev-secret'
    )


def _build_decision_receipt(
    *,
    outcome: str,
    reason: str,
    credential_info: dict | None = None,
    status_code: int | None = None,
) -> dict:
    issued_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    receipt = {
        'decision_id': f"dec_{secrets.token_urlsafe(9)}",
        'issued_at': issued_at,
        'outcome': str(outcome or 'deny'),
        'reason': str(reason or 'policy_decision'),
        'method': request.method,
        'path': request.path,
        'status_code': status_code,
        'token_id': (credential_info or {}).get('token_id'),
        'delegated_by_ppid': (credential_info or {}).get('authorized_by_ppid'),
        'acting_for_ppid': (credential_info or {}).get('acting_for_ppid') or (credential_info or {}).get('authorized_by_ppid'),
        'requested_by_ppid': (credential_info or {}).get('requested_by_ppid'),
        'delegation_id': (credential_info or {}).get('delegation_id'),
        'delegated_by_user_ref': (credential_info or {}).get('delegated_by_user_ref'),
        'acting_for_user_ref': (credential_info or {}).get('acting_for_user_ref'),
        'requested_by_user_ref': (credential_info or {}).get('requested_by_user_ref'),
    }
    payload = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
    signature = hmac.new(
        _decision_receipt_secret().encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    receipt['signature'] = signature
    return receipt


def _attach_decision_headers(response, receipt: dict | None):
    if not receipt:
        return response
    response.headers['X-Lemma-Decision-Id'] = str(receipt.get('decision_id') or '')
    response.headers['X-Lemma-Decision-Signature'] = str(receipt.get('signature') or '')
    return response


def _error_with_decision(
    *,
    status_code: int,
    error: str,
    message: str,
    reason: str,
    credential_info: dict | None = None,
    extra: dict | None = None,
):
    receipt = _build_decision_receipt(
        outcome='deny',
        reason=reason,
        credential_info=credential_info,
        status_code=status_code,
    )
    payload = {
        'success': False,
        'error': error,
        'message': message,
        'decision': receipt,
    }
    if isinstance(extra, dict):
        payload.update(extra)
    response = make_response(jsonify(payload), status_code)
    return _attach_decision_headers(response, receipt)


def _is_cors_origin_allowed(origin: str | None) -> bool:
    """Allowlist-based CORS check aligned with global app policy."""
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except Exception:
        return False

    hostname = (parsed.hostname or '').lower()
    origin_lc = origin.strip().lower()
    if not hostname:
        return False

    allowed_origins = {
        o.strip().lower()
        for o in os.environ.get('LEMMA_ALLOWED_ORIGINS', '').split(',')
        if o.strip()
    }
    if origin_lc in allowed_origins:
        return True

    allowed_suffixes = [
        s.strip().lower().lstrip('.')
        for s in os.environ.get('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '').split(',')
        if s.strip()
    ]
    if any(hostname.endswith(suffix) for suffix in allowed_suffixes):
        return True

    allow_dev = os.environ.get('LEMMA_ALLOW_DEV_ORIGINS', '1') != '0'
    if allow_dev and hostname in {'localhost', '127.0.0.1'}:
        return True

    return False


def restricted_cross_origin(*, supports_credentials: bool = False):
    """
    Apply CORS headers only for allowlisted origins.
    Prevents wildcard ACAO on privileged agent/admin endpoints.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # OPTIONS is primarily handled by app-level preflight middleware.
            if request.method == 'OPTIONS':
                response = make_response()
            else:
                response = make_response(f(*args, **kwargs))

            origin = request.headers.get('Origin')
            if origin and _is_cors_origin_allowed(origin):
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-Lemma-CSRF, X-CSRF-Token'
                response.headers['Vary'] = 'Origin'
                if supports_credentials:
                    response.headers['Access-Control-Allow-Credentials'] = 'true'
            return response
        return wrapped
    return decorator


def _cli_login_result_key(state: str) -> str:
    return f"{CLI_LOGIN_RESULT_KEY_PREFIX}:{state}"


def _store_cli_login_result(state: str, payload: dict) -> bool:
    if not state or not isinstance(payload, dict):
        return False
    return redis_store(_cli_login_result_key(state), payload, ttl_seconds=CLI_LOGIN_RESULT_TTL_SECONDS)


def _consume_cli_login_result(state: str) -> dict | None:
    if not state:
        return None
    key = _cli_login_result_key(state)
    payload = redis_get(key)
    if not payload:
        return None
    redis_delete(key)
    return payload if isinstance(payload, dict) else None


def _normalize_site_identifier(value: str | None) -> str | None:
    """Normalize host/site identifiers for consistent policy checks."""
    if not value:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    if '://' in text:
        parsed = urlparse(text)
        text = parsed.hostname or ''
    else:
        text = text.split('/')[0]
        text = text.split(':')[0]

    if text.startswith('www.'):
        text = text[4:]

    return text or None


def _get_owned_sites_for_delegator(authorized_by_ppid: str | None, authorized_by_email: str | None) -> set[str]:
    """
    Resolve the set of sites the delegating principal actively owns/administers.
    Security boundary: delegated agent tokens must never exceed this set.
    """
    try:
        return owned_sites_for_principal(
            ppid=(authorized_by_ppid or '').strip() or None,
            email=(authorized_by_email or '').strip().lower() or None,
        )
    except Exception as e:
        logger.error("Failed to resolve owned sites for delegator: %s", e)
        return set()


def _validate_allowed_sites_against_ownership(
    *,
    allowed_sites: list[str],
    authorized_by_ppid: str | None,
    authorized_by_email: str | None,
) -> tuple[bool, list[str], set[str]]:
    """
    Ensure requested allowed_sites are strictly within delegator ownership.
    """
    owned_sites = _get_owned_sites_for_delegator(authorized_by_ppid, authorized_by_email)
    internal_aliases = {'lemma.id', 'lemma_platform'}
    owned_sites_norm = {
        s for s in (_normalize_site_identifier(site) for site in (owned_sites or set())) if s
    }
    if owned_sites_norm.intersection(internal_aliases):
        owned_sites_norm.update(internal_aliases)
    allowed_norm = [
        s for s in (_normalize_site_identifier(site) for site in (allowed_sites or [])) if s
    ]
    if (
        allowed_norm
        and set(allowed_norm).issubset(internal_aliases)
        and _is_lemma_platform_operator(authorized_by_ppid, authorized_by_email)
    ):
        return True, [], owned_sites_norm | internal_aliases
    invalid = [site for site in sorted(set(allowed_norm)) if site not in owned_sites_norm]
    return len(invalid) == 0, invalid, owned_sites_norm


def _is_lemma_platform_operator(ppid: str | None, email: str | None) -> bool:
    """True when principal may delegate lemma.id-only operator plane tokens."""
    ppid = str(ppid or '').strip()
    email = str(email or '').strip().lower()
    if not ppid and not email:
        return False
    try:
        from api.database import SiteAdmin, get_db

        db = get_db()
        try:
            query = db.query(SiteAdmin).filter(
                SiteAdmin.site_id.in_(['lemma.id', 'lemma_platform']),
                SiteAdmin.is_active == True,  # noqa: E712
            )
            if ppid:
                row = query.filter(SiteAdmin.admin_did == ppid).first()
                if row:
                    return True
            if email:
                row = query.filter(SiteAdmin.admin_email == email).first()
                if row:
                    return True
        finally:
            db.close()
    except Exception as exc:
        logger.warning('lemma platform operator lookup failed: %s', exc)

    admin_ctx = _parse_admin_lemma_context()
    ctx_site = _normalize_site_identifier(admin_ctx.get('site_id') or '')
    platform_sites = {'lemma.id', 'lemma_platform'}
    if ctx_site in platform_sites:
        ctx_ppid = admin_ctx.get('ppid')
        if ppid and ctx_ppid and str(ctx_ppid) == ppid:
            perm = (admin_ctx.get('permission_id') or admin_ctx.get('role') or '').lower()
            if perm in {'admin_access', 'super_admin_access', 'admin', 'super_admin', 'owner'}:
                return True
    return False


def _normalize_ppid_claim(value) -> str | None:
    candidate = str(value or '').strip()
    if candidate.startswith('did:lemma:ppid_'):
        return candidate
    return None


def _encode_credential_description(
    description: str,
    audience: str | None = None,
    delegation_reason: str | None = None,
    delegation_id: str | None = None,
    acting_for_ppid: str | None = None,
    requested_by_ppid: str | None = None,
    delegated_by_user_ref: str | None = None,
    acting_for_user_ref: str | None = None,
    requested_by_user_ref: str | None = None,
) -> str:
    """
    Keep backward compatibility with plain-text description while allowing
    structured metadata needed by Lemma Firewall profile checks.
    """
    description_text = (description or '').strip()
    delegation_reason_text = str(delegation_reason or '').strip() or None
    delegation_id_text = str(delegation_id or '').strip() or None
    acting_for = _normalize_ppid_claim(acting_for_ppid)
    requested_by = _normalize_ppid_claim(requested_by_ppid)
    delegated_by_user_ref_text = str(delegated_by_user_ref or '').strip() or None
    acting_for_user_ref_text = str(acting_for_user_ref or '').strip() or None
    requested_by_user_ref_text = str(requested_by_user_ref or '').strip() or None
    if (
        not audience and not delegation_reason_text and not delegation_id_text
        and not acting_for and not requested_by
        and not delegated_by_user_ref_text and not acting_for_user_ref_text and not requested_by_user_ref_text
    ):
        return description_text
    return json.dumps({
        'description': description_text,
        'audience': str(audience).strip().lower() or None,
        'delegation_reason': delegation_reason_text,
        'delegation_id': delegation_id_text,
        'acting_for_ppid': acting_for,
        'requested_by_ppid': requested_by,
        'delegated_by_user_ref': delegated_by_user_ref_text,
        'acting_for_user_ref': acting_for_user_ref_text,
        'requested_by_user_ref': requested_by_user_ref_text,
    })


def _decode_credential_description(raw_description: str | None) -> dict:
    """Parse description metadata when stored as JSON; fallback to plain text."""
    if not raw_description:
        return {
            'description': '',
            'audience': None,
            'delegation_reason': None,
            'delegation_id': None,
            'acting_for_ppid': None,
            'requested_by_ppid': None,
            'delegated_by_user_ref': None,
            'acting_for_user_ref': None,
            'requested_by_user_ref': None,
        }

    if isinstance(raw_description, dict):
        return {
            'description': str(raw_description.get('description') or '').strip(),
            'audience': str(raw_description.get('audience') or '').strip().lower() or None,
            'delegation_reason': str(raw_description.get('delegation_reason') or '').strip() or None,
            'delegation_id': str(raw_description.get('delegation_id') or '').strip() or None,
            'acting_for_ppid': _normalize_ppid_claim(raw_description.get('acting_for_ppid')),
            'requested_by_ppid': _normalize_ppid_claim(raw_description.get('requested_by_ppid')),
            'delegated_by_user_ref': str(raw_description.get('delegated_by_user_ref') or '').strip() or None,
            'acting_for_user_ref': str(raw_description.get('acting_for_user_ref') or '').strip() or None,
            'requested_by_user_ref': str(raw_description.get('requested_by_user_ref') or '').strip() or None,
        }

    if not isinstance(raw_description, str):
        return {
            'description': str(raw_description),
            'audience': None,
            'delegation_reason': None,
            'delegation_id': None,
            'acting_for_ppid': None,
            'requested_by_ppid': None,
            'delegated_by_user_ref': None,
            'acting_for_user_ref': None,
            'requested_by_user_ref': None,
        }

    try:
        decoded = json.loads(raw_description)
        if isinstance(decoded, dict):
            return {
                'description': str(decoded.get('description') or '').strip(),
                'audience': str(decoded.get('audience') or '').strip().lower() or None,
                'delegation_reason': str(decoded.get('delegation_reason') or '').strip() or None,
                'delegation_id': str(decoded.get('delegation_id') or '').strip() or None,
                'acting_for_ppid': _normalize_ppid_claim(decoded.get('acting_for_ppid')),
                'requested_by_ppid': _normalize_ppid_claim(decoded.get('requested_by_ppid')),
                'delegated_by_user_ref': str(decoded.get('delegated_by_user_ref') or '').strip() or None,
                'acting_for_user_ref': str(decoded.get('acting_for_user_ref') or '').strip() or None,
                'requested_by_user_ref': str(decoded.get('requested_by_user_ref') or '').strip() or None,
            }
    except Exception:
        pass

    return {
        'description': raw_description,
        'audience': None,
        'delegation_reason': None,
        'delegation_id': None,
        'acting_for_ppid': None,
        'requested_by_ppid': None,
        'delegated_by_user_ref': None,
        'acting_for_user_ref': None,
        'requested_by_user_ref': None,
    }


def _store_agent_credential_record(
    *,
    token_id: str,
    token_hash: str,
    authorized_by: str,
    user_email: str | None,
    scope: list[str],
    allowed_sites: list[str] | None,
    expires_at,
    agent_name: str,
    description: str,
    task_description: str | None,
    task_hash_value: str | None,
    allowed_paths: list[str] | None,
    max_operations: int | None,
    delegation_id: str | None,
    delegation_reason: str | None,
    acting_for_ppid: str | None,
    requested_by_ppid: str | None,
    delegated_by_user_ref: str | None,
    acting_for_user_ref: str | None,
    requested_by_user_ref: str | None,
    audience: str | None,
    subject_ref: str | None = None,
    runtime_id: str | None = None,
) -> int:
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO agent_credentials
            (token_id, token_hash, authorized_by_ppid, authorized_by_email,
             scope, allowed_sites, expires_at, agent_name, description,
             task_description, task_hash, allowed_paths, max_operations)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            token_id,
            token_hash,
            authorized_by,
            user_email,
            json.dumps(scope),
            json.dumps(allowed_sites) if allowed_sites is not None else None,
            expires_at,
            agent_name,
            description,
            task_description,
            task_hash_value,
            json.dumps(allowed_paths) if allowed_paths else None,
            max_operations
        ))
        credential_id = int(cursor.fetchone()[0])
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    record_delegation(
        token_id=token_id,
        delegation_id=str(delegation_id or f"dlg_{token_id}"),
        delegator_ppid=authorized_by,
        delegated_by_user_ref=delegated_by_user_ref or user_email,
        acting_for_ppid=acting_for_ppid,
        acting_for_user_ref=acting_for_user_ref,
        requested_by_ppid=requested_by_ppid,
        requested_by_user_ref=requested_by_user_ref,
        subject_type='agent_credential',
        subject_ref=subject_ref or token_id,
        scope=scope,
        allowed_sites=allowed_sites,
        audience=audience,
        task_description=task_description,
        task_hash=task_hash_value,
        allowed_paths=allowed_paths,
        max_operations=max_operations,
        expires_at=expires_at,
        reason=delegation_reason,
        runtime_id=runtime_id,
        org_id=getattr(g, "org_id", "org_default"),
        environment=getattr(g, "environment", "prod"),
        root_type='passkey_root',
    )
    return credential_id


def _get_allowed_values(env_key: str, default_csv: str) -> set[str]:
    raw = os.environ.get(env_key, default_csv)
    return {item.strip().lower() for item in raw.split(',') if item.strip()}


def _parse_admin_lemma_context():
    """
    Parse optional admin lemma context from request payload or Authorization bearer JSON.
    This enables issuance checks based on possession of a locally-verified admin lemma.
    """
    payload = request.get_json(silent=True) or {}
    credential = payload.get('admin_credential') or payload.get('credential')

    if not credential:
        raw_header = request.headers.get('X-Lemma-Credential')
        if raw_header:
            try:
                import base64
                import json as _json

                text = str(raw_header).strip()
                if text.startswith('{'):
                    credential = _json.loads(text)
                else:
                    padded = text + ('=' * (-len(text) % 4))
                    credential = _json.loads(base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8'))
            except Exception:
                credential = None

    if not credential:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            raw = auth_header[7:]
            try:
                credential = json.loads(raw)
            except Exception:
                credential = None

    if not isinstance(credential, dict):
        return {
            'permission_id': None,
            'role': None,
            'site_id': None,
            'ppid': None
        }

    claims = credential.get('claims') or credential.get('credentialSubject') or {}
    permission_id = (
        claims.get('permissionId')
        or claims.get('permission_id')
        or claims.get('permission_level')
    )
    role = (
        claims.get('accountType')
        or claims.get('role')
        or claims.get('user_role')
        or claims.get('permission_level')
    )
    site_id = claims.get('siteId') or claims.get('site_id')
    ppid = (
        credential.get('subject')
        or credential.get('sub')
        or claims.get('sub')
        or claims.get('ppid')
        or claims.get('id')
    )

    return {
        'permission_id': (permission_id or '').strip().lower(),
        'role': (role or '').strip().lower(),
        'site_id': (site_id or '').strip().lower(),
        'ppid': ppid
    }


def _require_delegation_admin_session():
    """
    Require admin IAM with lemma-bound identity before allowing delegated credential issuance.

    Accepted admin context:
    1) Browser wallet session unlock + lemma PPID + allowed admin role/permission
    2) Internal lemma admin credential/token flow for lemma.id
    """
    session_permission_id = (session.get('permission_id') or '').strip().lower()
    session_user_role = (session.get('user_role') or '').strip().lower()
    admin_lemma_ctx = _parse_admin_lemma_context()

    allowed_permissions = _get_allowed_values(
        'AGENT_DELEGATION_ALLOWED_PERMISSIONS',
        DEFAULT_DELEGATION_ALLOWED_PERMISSIONS
    )
    allowed_roles = _get_allowed_values(
        'AGENT_DELEGATION_ALLOWED_ROLES',
        DEFAULT_DELEGATION_ALLOWED_ROLES
    )

    payload = request.get_json(silent=True) or {}
    intended_platform = (
        payload.get('intended_platform')
        or request.args.get('intended_platform')
        or 'lemma.id'
    ).strip().lower()
    intended_platform = _normalize_site_identifier(intended_platform) or 'lemma.id'

    internal_targets = {'lemma.id', 'lemma_platform'}
    lemma_site_id = _normalize_site_identifier(admin_lemma_ctx.get('site_id') or '')
    is_internal_alias_match = (
        lemma_site_id in internal_targets and intended_platform in internal_targets
    )
    if lemma_site_id and lemma_site_id != intended_platform and not is_internal_alias_match:
        return False, (
            jsonify({
                'success': False,
                'error': 'admin_lemma_site_mismatch',
                'message': f'Admin lemma is for {lemma_site_id}, but requested delegation is for {intended_platform}.'
            }),
            403
        )
    if intended_platform in internal_targets:
        # Accept admin-scoped machine principal for internal lemma-only issuance.
        agent_token_ctx = getattr(g, 'agent_credential', None)
        if not agent_token_ctx:
            raw_agent_token = (request.headers.get('X-Agent-Token') or '').strip()
            if raw_agent_token.startswith('lm_agent_'):
                agent_token_ctx = validate_agent_token(raw_agent_token)
        if agent_token_ctx:
            token_scope = agent_token_ctx.get('scope') or []
            if isinstance(token_scope, str):
                token_scope = [token_scope]
            token_scope = {str(s).strip().lower() for s in token_scope if s}
            token_ppid = agent_token_ctx.get('authorized_by_ppid') or agent_token_ctx.get('authorized_by')
            if 'admin' in token_scope and token_ppid and str(token_ppid).startswith('did:lemma:ppid_'):
                g.delegation_ppid = str(token_ppid)
                return True, None

        # Accept internal lemma admin VC context (no wallet cookie required).
        lemma_permission_id = (admin_lemma_ctx.get('permission_id') or '').strip().lower()
        lemma_role = (admin_lemma_ctx.get('role') or '').strip().lower()
        lemma_ppid = admin_lemma_ctx.get('ppid')
        has_allowed_ctx = (
            (lemma_permission_id and lemma_permission_id in allowed_permissions)
            or (lemma_role and lemma_role in allowed_roles)
        )
        if has_allowed_ctx and lemma_ppid and str(lemma_ppid).startswith('did:lemma:ppid_'):
            g.delegation_ppid = str(lemma_ppid)
            return True, None

    # Browser wallet session unlock anchor is mandatory for issuance.
    wallet_session_cookie = request.cookies.get('lemma_wallet_session')
    if not wallet_session_cookie:
        return False, (
            jsonify({
                'success': False,
                'error': 'wallet_unlock_required',
                'message': 'Unlock your lemma.id wallet for the day before issuing delegated agent credentials.'
            }),
            403
        )

    # Validate cookie cryptographically (prevents stale/forged session usage).
    try:
        from auth.session_manager import validate_session_token
        wallet_session_data = validate_session_token(wallet_session_cookie)
    except Exception:
        wallet_session_data = None

    if not wallet_session_data:
        return False, (
            jsonify({
                'success': False,
                'error': 'wallet_session_expired',
                'message': 'Your wallet unlock session is expired. Unlock lemma.id again.'
            }),
            403
        )

    # Require explicit lemma PPID identity for attribution.
    delegator_ppid = (
        _extract_ppid_from_lemma_header()
        or admin_lemma_ctx.get('ppid')
        or session.get('ppid')
    )
    if not delegator_ppid or not str(delegator_ppid).startswith('did:lemma:ppid_'):
        return False, (
            jsonify({
                'success': False,
                'error': 'ppid_required',
                'message': 'Delegation issuance requires a valid lemma PPID (did:lemma:ppid_...).'
            }),
            403
        )

    has_allowed_permission = False
    has_allowed_role = False

    # Session-derived IAM
    if session_permission_id and session_permission_id in allowed_permissions:
        has_allowed_permission = True
    if session_user_role and session_user_role in allowed_roles:
        has_allowed_role = True

    # Admin lemma-derived IAM (possession proof from client credential)
    lemma_permission_id = admin_lemma_ctx.get('permission_id')
    lemma_role = admin_lemma_ctx.get('role')
    if lemma_permission_id and lemma_permission_id in allowed_permissions:
        has_allowed_permission = True
    if lemma_role and lemma_role in allowed_roles:
        has_allowed_role = True

    if not (has_allowed_permission or has_allowed_role):
        return False, (
            jsonify({
                'success': False,
                'error': 'insufficient_permission',
                'message': 'Delegated agent credential issuance requires possession of an allowed admin role/permission.',
                'required_permissions': sorted(list(allowed_permissions)),
                'required_roles': sorted(list(allowed_roles))
            }),
            403
        )

    g.delegation_ppid = str(delegator_ppid)
    return True, None


# ============================================
# TASK-BOUND AUTHORIZATION HELPERS
# ============================================

def hash_task(task_description):
    """Create a SHA256 hash of the task description for verification."""
    if not task_description:
        return None
    return hashlib.sha256(task_description.strip().encode()).hexdigest()


def _apply_default_admin_bounds(scope, allowed_paths, max_operations):
    """
    Reduce blast radius for admin-scoped delegated credentials by default.
    Explicit caller-provided bounds still take precedence.
    """
    if not isinstance(scope, list):
        return allowed_paths, max_operations

    has_admin_scope = 'admin' in {str(s).strip().lower() for s in scope if s}
    if not has_admin_scope:
        return allowed_paths, max_operations

    if allowed_paths is None:
        allowed_paths = list(DEFAULT_ADMIN_ALLOWED_PATHS)
    if max_operations is None:
        max_operations = DEFAULT_ADMIN_MAX_OPERATIONS
    return allowed_paths, max_operations


def normalize_path(path: str) -> str:
    """
    Normalize a URL path to prevent path traversal attacks.

    SECURITY: This prevents attacks like:
    - /api/sites/../admin → /admin (traversal blocked)
    - /api/sites/./files → /api/sites/files (dot removal)
    - /api//sites///files → /api/sites/files (slash normalization)

    Returns the canonical path or raises ValueError if traversal detected.
    """
    if not path:
        return '/'

    # Split path into segments
    segments = path.split('/')
    normalized = []

    for segment in segments:
        if segment == '' or segment == '.':
            # Skip empty segments and current directory
            continue
        elif segment == '..':
            # SECURITY: Block parent directory traversal entirely
            # Rather than allowing it to go up, we reject the path
            raise ValueError(f"Path traversal detected in: {path}")
        else:
            normalized.append(segment)

    result = '/' + '/'.join(normalized)
    return result


def path_matches_pattern(path, pattern):
    """
    Check if a request path matches an allowed pattern.

    Patterns support:
    - Exact match: "/api/sites" matches only "/api/sites"
    - Wildcard segments: "/api/sites/*" matches "/api/sites/123"
    - Double wildcard: "/api/sites/**" matches "/api/sites/123/files/foo"
    - Glob patterns: "/api/*/credentials" matches "/api/agent/credentials"

    SECURITY: Paths are normalized before matching to prevent traversal attacks.

    Examples:
        path_matches_pattern("/api/sites/123", "/api/sites/*") -> True
        path_matches_pattern("/api/sites/123/files", "/api/sites/*") -> False
        path_matches_pattern("/api/sites/123/files", "/api/sites/**") -> True
        path_matches_pattern("/api/sites/../admin", "/api/sites/*") -> ValueError
    """
    if not pattern:
        return True  # No pattern = allow all

    # SECURITY: Normalize paths to prevent traversal attacks
    try:
        path = normalize_path(path)
    except ValueError:
        # Path traversal detected - reject immediately
        return False

    pattern = pattern.rstrip('/')

    # Convert pattern to regex
    # Escape special regex chars except *
    regex_pattern = re.escape(pattern)
    # Replace escaped ** with "match anything including /"
    regex_pattern = regex_pattern.replace(r'\*\*', '.*')
    # Replace escaped * with "match anything except /"
    regex_pattern = regex_pattern.replace(r'\*', '[^/]*')
    # Anchor the pattern
    regex_pattern = f'^{regex_pattern}$'

    return bool(re.match(regex_pattern, path))


def check_path_allowed(path, allowed_paths):
    """
    Check if a path is allowed by any of the allowed patterns.

    Args:
        path: The request path (e.g., "/api/sites/123")
        allowed_paths: List of allowed patterns, or None (allow all)

    Returns:
        (is_allowed, matching_pattern or None)
    """
    if allowed_paths is None:
        return True, None

    if not allowed_paths:
        return False, None

    for pattern in allowed_paths:
        if path_matches_pattern(path, pattern):
            return True, pattern

    return False, None


def infer_requested_site_ids():
    """
    Infer site identifiers referenced by the current request.

    Sources:
    - URL path segments (e.g. /api/sites/<site_id>/...)
    - Query params: site_id, siteId
    - JSON body: site_id, siteId, intended_platform

    Returns lowercased unique site ids.
    """
    site_ids = set()

    try:
        path = (request.path or '').strip('/').split('/')
        for i, seg in enumerate(path):
            if seg in ('sites', 'site') and i + 1 < len(path):
                candidate = _normalize_site_identifier(path[i + 1])
                if candidate:
                    site_ids.add(candidate)
    except Exception:
        pass

    host_site = _normalize_site_identifier(request.host)
    if host_site:
        site_ids.add(host_site)

    origin = request.headers.get('Origin')
    origin_site = _normalize_site_identifier(origin)
    if origin_site:
        site_ids.add(origin_site)

    for key in ('site_id', 'siteId'):
        val = request.args.get(key)
        if val:
            normalized = _normalize_site_identifier(val)
            if normalized:
                site_ids.add(normalized)

    payload = request.get_json(silent=True) or {}
    for key in ('site_id', 'siteId', 'intended_platform'):
        val = payload.get(key)
        if val:
            normalized = _normalize_site_identifier(val)
            if normalized:
                site_ids.add(normalized)

    return sorted(site_ids)


def check_site_allowed(credential_info):
    """
    Enforce allowed_sites restriction for the current request.
    Returns (is_allowed, blocked_site, allowed_sites_norm, requested_sites).
    """
    allowed_sites = credential_info.get('allowed_sites')
    owned_sites = credential_info.get('owned_sites')
    requested_sites = infer_requested_site_ids()

    if allowed_sites is None:
        return True, None, None, requested_sites

    allowed_sites_norm = {
        s for s in (_normalize_site_identifier(item) for item in allowed_sites) if s
    }
    if not allowed_sites_norm:
        return False, None, set(), requested_sites

    owned_sites_norm = None
    if owned_sites is not None:
        owned_sites_norm = {
            s for s in (_normalize_site_identifier(item) for item in owned_sites) if s
        }
        if not owned_sites_norm:
            return False, None, set(), requested_sites
        # Defense-in-depth: token scope cannot exceed ownership.
        off_scope = [s for s in allowed_sites_norm if s not in owned_sites_norm]
        if off_scope:
            return False, off_scope[0], allowed_sites_norm, requested_sites

    blocked_sites = [s for s in requested_sites if s not in allowed_sites_norm]
    if not blocked_sites and owned_sites_norm is not None:
        blocked_sites = [s for s in requested_sites if s not in owned_sites_norm]
    if blocked_sites:
        return False, blocked_sites[0], allowed_sites_norm, requested_sites

    return True, None, allowed_sites_norm, requested_sites

# ============================================
# SECURITY: Token Generation and Hashing
# ============================================

def generate_agent_token():
    """
    Generate a secure random token for agent authentication.
    Returns (token_id, plaintext_token, token_hash)
    
    - token_id: Short identifier for the token (for display/lookup)
    - plaintext_token: What the agent will use (shown once, never stored)
    - token_hash: What we store in the database (cannot be reversed)
    """
    token_id = f"agt_{secrets.token_urlsafe(8)}"
    plaintext_token = f"lm_agent_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
    
    return token_id, plaintext_token, token_hash


def hash_token(plaintext_token):
    """Hash a token for comparison with stored hash."""
    return hashlib.sha256(plaintext_token.encode()).hexdigest()


def _extract_api_key_from_request():
    """
    Extract API key from supported locations.
    Preferred order: X-API-Key header, api_key query param, Authorization Bearer token.
    """
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    if api_key:
        return api_key

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
        if token and not token.startswith('{') and not token.startswith('lm_agent_'):
            return token

    return None


def _parse_ppid_from_credential_dict(credential: dict | None) -> str | None:
    if not isinstance(credential, dict):
        return None
    claims = credential.get('claims') or credential.get('credentialSubject') or {}
    ppid = (
        credential.get('subject')
        or credential.get('sub')
        or claims.get('sub')
        or claims.get('ppid')
        or claims.get('id')
        or claims.get('subject')
    )
    if ppid and str(ppid).startswith('did:lemma:ppid_'):
        return str(ppid)
    return None


def _decode_lemma_header_credential() -> dict | None:
    raw = request.headers.get('X-Lemma-Credential')
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.startswith('{'):
            credential = json.loads(text)
        else:
            padded = text + ('=' * (-len(text) % 4))
            decoded = base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8')
            credential = json.loads(decoded)
    except Exception:
        return None
    return credential if isinstance(credential, dict) else None


def _extract_ppid_from_lemma_header(*, require_verification: bool = True):
    """
    Extract verified PPID from full credential header.
    Header format: X-Lemma-Credential = base64url(JSON credential) or raw JSON.
    """
    credential = _decode_lemma_header_credential()
    if not credential:
        return None

    if require_verification:
        try:
            from api.trusted_issuers import verify_credential_with_trust
            verification = verify_credential_with_trust(credential)
            if not verification.get('valid'):
                return None
        except Exception:
            return None

    return _parse_ppid_from_credential_dict(credential)


def _has_valid_wallet_unlock_session() -> bool:
    wallet_session_cookie = request.cookies.get('lemma_wallet_session')
    if not wallet_session_cookie:
        return False
    try:
        from auth.session_manager import validate_session_token
        return bool(validate_session_token(wallet_session_cookie))
    except Exception:
        return False


def _resolve_agent_owner_ppid():
    """
    Resolve the principal for agent credential list/manage browser flows.

    Prefers verified lemma credentials, then agent tokens and session anchors.
    When the wallet unlock cookie is valid, accepts a parseable lemma header PPID
    so admin pages can list tokens even if the auto-selected credential fails
    strict server verification (for example identity/isHuman package types).
    """
    agent_token = request.headers.get('X-Agent-Token')
    if agent_token:
        credential_info = validate_agent_token(agent_token)
        if credential_info:
            principal = credential_info.get('authorized_by_ppid') or credential_info.get('authorized_by_email')
            if principal:
                return principal, None

    try:
        from api.authz_engine import extract_user_lemma_principal
        principal, _error = extract_user_lemma_principal(request.headers)
        if principal and principal.ppid:
            return principal.ppid, None
    except Exception:
        pass

    ppid = _extract_ppid_from_lemma_header()
    if ppid:
        return ppid, None

    ppid = session.get('ppid')
    if ppid:
        return str(ppid), None

    customer_id = session.get('customer_id')
    if customer_id:
        return f"customer:{customer_id}", None

    if _has_valid_wallet_unlock_session():
        ppid = _parse_ppid_from_credential_dict(_decode_lemma_header_credential())
        if ppid:
            return ppid, None

    return None, 'Authentication required'


def _resolve_monitor_identity():
    """
    Resolve owner identity for monitoring endpoints.

    Supports:
    - X-Agent-Token (owner inferred from credential)
    - X-Lemma-Credential
    - Flask session customer_id
    - X-API-Key (for custom site dashboards)
    """
    agent_token = request.headers.get('X-Agent-Token')
    if agent_token:
        credential_info = validate_agent_token(agent_token)
        if not credential_info:
            return None, ('Invalid, expired, or revoked agent token', 401)

        principal = credential_info.get('authorized_by_ppid') or credential_info.get('authorized_by_email')
        if not principal:
            return None, ('Agent token missing authorized principal', 401)

        return {
            'auth_method': 'agent_token',
            'principal': principal
        }, None

    ppid = _extract_ppid_from_lemma_header() or session.get('ppid')
    if ppid:
        if not ppid.startswith('did:lemma:ppid_'):
            return None, ('Invalid PPID format', 400)
        return {
            'auth_method': 'ppid',
            'principal': ppid
        }, None

    customer_id = session.get('customer_id')
    if customer_id:
        return {
            'auth_method': 'session',
            'principal': f"customer:{customer_id}"
        }, None

    api_key = _extract_api_key_from_request()
    if api_key:
        try:
            from api.customer_accounts import customer_manager
            key_validation = customer_manager.validate_api_key(api_key)
            if not key_validation.get('valid'):
                return None, (key_validation.get('error', 'Invalid API key'), 401)

            customer_id = key_validation.get('customer_id')
            customer = customer_manager.get_customer(customer_id)
            return {
                'auth_method': 'api_key',
                'principal': f"customer:{customer_id}",
                'customer_email': getattr(customer, 'email', None)
            }, None
        except Exception as e:
            logger.error(f"API key validation failed for monitor endpoint: {e}")
            return None, ('Failed to validate API key', 500)

    return None, ('Authentication required', 401)


def _validate_request_api_key(api_key: str):
    """
    Validate API key for generic request auth paths.
    Accepts platform env keys and customer keys stored in database.
    Returns (is_valid, metadata_dict).
    """
    if not api_key:
        return False, {}

    platform_key = os.getenv('LEMMA_API_KEY') or os.getenv('LEMMA_PLATFORM_API_KEY')
    if platform_key and api_key == platform_key:
        return True, {'type': 'platform'}

    try:
        from api.customer_accounts import customer_manager
        validation = customer_manager.validate_api_key(api_key)
        if validation.get('valid'):
            return True, {
                'type': 'customer',
                'customer_id': validation.get('customer_id'),
                'site_id': validation.get('site_id'),
            }
    except Exception as e:
        logger.warning(f"API key validation failed in agent auth decorator: {e}")

    return False, {}


def _build_owner_filter(identity, alias='ac'):
    """
    Build SQL filter for ownership checks.
    Returns (clause, params)
    """
    principal = identity.get('principal')
    customer_email = identity.get('customer_email')

    clauses = [f"{alias}.authorized_by_ppid = %s", f"{alias}.authorized_by_email = %s"]
    params = [principal, principal]

    # For API-key auth, also allow matching by customer email when available.
    if identity.get('auth_method') == 'api_key' and customer_email:
        clauses.append(f"{alias}.authorized_by_email = %s")
        params.append(customer_email)

    return f"({' OR '.join(clauses)})", params


def _scope_rank(scope: str | None) -> int:
    table = {
        'read': 1,
        'write': 2,
        'admin': 3,
        'test': 4,
    }
    return table.get((scope or '').strip().lower(), 0)


def _normalize_scope_list(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip().lower() for part in value.split(',') if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip().lower() for part in value if str(part).strip()]
    return []


def _scope_satisfies(required_scope: str | None, provided_scopes) -> bool:
    required = (required_scope or '').strip().lower()
    if not required:
        return True

    scope_values = set(_normalize_scope_list(provided_scopes))
    if required in scope_values:
        return True
    if required == 'read' and ('write' in scope_values or 'admin' in scope_values):
        return True
    if required == 'write' and 'admin' in scope_values:
        return True
    return False


def _resolve_route_policy_scope(explicit_required_scope: str | None):
    policy = get_policy_for_request(request.method, request.path)
    policy_scope = policy.required_scope if policy else None
    explicit_scope = (explicit_required_scope or '').strip().lower() or None
    if policy_scope and explicit_scope:
        return policy, policy_scope if _scope_rank(policy_scope) >= _scope_rank(explicit_scope) else explicit_scope
    return policy, (policy_scope or explicit_scope)


def _enforce_route_policy_for_principal(
    *,
    policy,
    principal_type: str,
    required_scope: str | None,
    provided_scope,
    site_binding: str | None = None,
    allow_unscoped: bool = False,
):
    if policy and principal_type not in policy.allowed_principals:
        return jsonify({
            'success': False,
            'error': 'principal_not_allowed',
            'message': f'Principal type {principal_type} is not allowed for this route.',
            'allowed_principals': list(policy.allowed_principals),
        }), 403

    if required_scope and not allow_unscoped and not _scope_satisfies(required_scope, provided_scope):
        return jsonify({
            'success': False,
            'error': 'missing_scope',
            'required_scope': [required_scope],
            'provided_scope': _normalize_scope_list(provided_scope),
        }), 403

    if policy and policy.site_binding_required:
        requested_sites = infer_requested_site_ids()
        normalized_binding = _normalize_site_identifier(site_binding) if site_binding else None
        if requested_sites and (not normalized_binding or any(site != normalized_binding for site in requested_sites)):
            return jsonify({
                'success': False,
                'error': 'site_mismatch',
                'site_binding': normalized_binding,
                'requested_sites': requested_sites,
            }), 403

    return None


def require_agent_or_user_session(required_scope=None):
    """
    Lightweight explicit auth decorator for credential management endpoints.
    Accepts agent token, full lemma credential header, API key, or active agent browser session.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            policy, effective_required_scope = _resolve_route_policy_scope(required_scope)

            agent_token = request.headers.get('X-Agent-Token')
            if agent_token:
                credential_info = validate_agent_token(agent_token)
                if not credential_info:
                    return jsonify({'success': False, 'error': 'invalid_token'}), 401

                scope = credential_info.get('scope') or []
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='agent_token',
                    required_scope=effective_required_scope,
                    provided_scope=scope,
                    site_binding=None,
                )
                if policy_error:
                    return policy_error

                site_ok, blocked_site, allowed_sites_norm, _requested_sites = check_site_allowed(credential_info)
                if not site_ok:
                    return jsonify({
                        'success': False,
                        'error': 'site_not_allowed',
                        'site': blocked_site,
                        'allowed_sites': sorted(list(allowed_sites_norm)) if allowed_sites_norm is not None else None,
                        'message': 'This agent credential is restricted to specific sites.'
                    }), 403
                g.agent_credential = credential_info
                g.ppid = credential_info.get('authorized_by_ppid')
                g.authenticated = True
                g.auth_method = 'agent_token'
                return f(*args, **kwargs)

            lemma_principal, lemma_error = extract_user_lemma_principal(request.headers)
            if lemma_principal:
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='user_lemma',
                    required_scope=effective_required_scope,
                    provided_scope=lemma_principal.scope,
                    site_binding=lemma_principal.site_binding,
                )
                if policy_error:
                    return policy_error
                g.ppid = lemma_principal.ppid
                g.credential_id = lemma_principal.credential_id
                g.permission_id = lemma_principal.permission_id
                g.authenticated = True
                g.auth_method = lemma_principal.auth_method
                return f(*args, **kwargs)
            elif lemma_error and lemma_error not in {'missing_lemma_header', 'invalid_lemma_header'}:
                return jsonify({
                    'success': False,
                    'error': lemma_error,
                    'message': 'Invalid lemma credential',
                }), 401

            if session.get('agent_authenticated'):
                session_scope = session.get('agent_scope', [])
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='agent_token',
                    required_scope=effective_required_scope,
                    provided_scope=session_scope,
                    site_binding=None,
                )
                if policy_error:
                    return policy_error
                session_allowed_sites = session.get('agent_allowed_sites')
                if session_allowed_sites is not None:
                    site_ok, blocked_site, allowed_sites_norm, _requested_sites = check_site_allowed({
                        'allowed_sites': session_allowed_sites
                    })
                    if not site_ok:
                        return jsonify({
                            'success': False,
                            'error': 'site_not_allowed',
                            'site': blocked_site,
                            'allowed_sites': sorted(list(allowed_sites_norm)) if allowed_sites_norm is not None else None,
                            'message': 'This agent session is restricted to specific sites.'
                        }), 403
                g.ppid = session.get('agent_ppid')
                g.authenticated = True
                g.auth_method = 'agent_session'
                return f(*args, **kwargs)

            api_key = _extract_api_key_from_request()
            is_valid_key, key_info = _validate_request_api_key(api_key)
            if is_valid_key:
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='api_key',
                    required_scope=effective_required_scope,
                    provided_scope=[],
                    site_binding=None,
                    allow_unscoped=True,
                )
                if policy_error:
                    return policy_error
                g.api_key = api_key
                g.api_key_info = key_info
                g.authenticated = True
                g.auth_method = 'api_key'
                return f(*args, **kwargs)

            return jsonify({
                'success': False,
                'error': 'auth_required',
                'message': 'Provide X-Agent-Token, X-Lemma-Credential, X-API-Key, or Authorization: Bearer <api_key> header',
            }), 401

        return wrapped
    return decorator


# ============================================
# CREDENTIAL ISSUANCE (Requires Passkey Auth)
# ============================================

@agent_credentials_bp.route('/api/agent/credentials/issue', methods=['POST'])
@restricted_cross_origin()
@rate_limit(credential_issue_limit, key_func=get_issuance_identifier)
@require_agent_or_user_session()
def issue_agent_credential():
    """
    Issue a new agent credential with optional task-bound authorization.

    SECURITY: This endpoint requires the user to be authenticated via passkey.
    The passkey proof must be fresh (within last 5 minutes) to issue credentials.

    POST /api/agent/credentials/issue
    {
        "agent_name": "Claude Code",
        "scope": ["read", "write"],
        "ttl_hours": 4,
        "allowed_sites": null,
        "description": "Development session",

        // NEW: Task-bound authorization fields
        "task": "Fix the login bug in auth.py",
        "allowed_paths": ["/api/sites/*", "/api/git/**"],
        "max_operations": 100
    }

    Returns:
        - token: The plaintext token (SHOWN ONLY ONCE)
        - token_id: Identifier for managing the credential
        - expires_at: When the credential expires
        - task_hash: SHA256 of task for verification (if task provided)
    """
    try:
        is_allowed, error_response = _require_delegation_admin_session()
        if not is_allowed:
            return error_response

        # Strict issuance identity: PPID from validated delegation session only.
        authorized_by = getattr(g, 'delegation_ppid', None)
        user_email = session.get('user_email')
        if not authorized_by or not str(authorized_by).startswith('did:lemma:ppid_'):
            return jsonify({
                'success': False,
                'error': 'ppid_required',
                'message': 'Delegation issuance requires a valid lemma PPID.'
            }), 403

        # Parse request data
        data = request.get_json() or {}
        agent_name = data.get('agent_name', 'AI Agent')
        scope = data.get('scope', ['read'])
        ttl_hours = min(data.get('ttl_hours', 4), 24)  # Max 24 hours
        intended_platform = (
            data.get('intended_platform')
            or request.args.get('intended_platform')
            or request.headers.get('Origin')
            or request.host
            or 'lemma.id'
        )
        intended_platform = _normalize_site_identifier(intended_platform) or 'lemma.id'

        from api.platform_owner import (
            is_platform_owner_ppid,
            is_platform_site,
            platform_owner_enforcement_enabled,
        )

        scope_values = scope if isinstance(scope, list) else [scope]
        scope_norm = {str(item).strip().lower() for item in scope_values if item}
        if (
            platform_owner_enforcement_enabled()
            and is_platform_site(intended_platform)
            and 'admin' in scope_norm
            and not is_platform_owner_ppid(authorized_by)
        ):
            return jsonify({
                'success': False,
                'error': 'platform_owner_required',
                'message': 'Platform admin agent credentials may only be issued by the platform owner.',
            }), 403

        allowed_sites = data.get('allowed_sites')
        if allowed_sites is None:
            # Security default: site-bind credentials to the site where they are issued.
            allowed_sites = [intended_platform]
        description = data.get('description', '')
        audience = (data.get('audience') or data.get('aud') or '').strip().lower() or None
        delegation_reason = str(data.get('delegation_reason') or data.get('reason') or '').strip() or None
        delegation_id = str(data.get('delegation_id') or '').strip() or None
        acting_for_ppid = _normalize_ppid_claim(data.get('acting_for_ppid') or data.get('acting_for'))
        requested_by_ppid = _normalize_ppid_claim(data.get('requested_by_ppid') or data.get('requested_by'))
        delegated_by_user_ref = str(
            data.get('delegated_by_user_ref') or data.get('delegated_by_user_id') or data.get('customer_user_id') or user_email or ''
        ).strip() or None
        acting_for_user_ref = str(
            data.get('acting_for_user_ref') or data.get('acting_for_user_id') or ''
        ).strip() or None
        requested_by_user_ref = str(
            data.get('requested_by_user_ref') or data.get('requested_by_user_id') or ''
        ).strip() or None
        if acting_for_ppid is None:
            acting_for_ppid = str(authorized_by)
        if requested_by_ppid is None:
            requested_by_ppid = str(authorized_by)
        if not delegation_id:
            delegation_id = f"dlg_{secrets.token_urlsafe(8)}"

        # NEW: Task-bound authorization fields
        task_description = data.get('task')
        task_hash_value = hash_task(task_description)
        allowed_paths = data.get('allowed_paths')  # List of path patterns
        max_operations = data.get('max_operations')  # Max API calls

        # Validate allowed_paths format
        if allowed_paths is not None:
            if not isinstance(allowed_paths, list):
                return jsonify({
                    'success': False,
                    'error': 'allowed_paths must be a list of path patterns'
                }), 400
            # Validate each pattern is a string starting with /
            for pattern in allowed_paths:
                if not isinstance(pattern, str) or not pattern.startswith('/'):
                    return jsonify({
                        'success': False,
                        'error': f'Invalid path pattern: {pattern}. Must start with /'
                    }), 400

        # Validate max_operations
        if max_operations is not None:
            max_operations = int(max_operations)
            if max_operations < 1:
                return jsonify({
                    'success': False,
                    'error': 'max_operations must be at least 1'
                }), 400

        if not isinstance(allowed_sites, list):
            return jsonify({
                'success': False,
                'error': 'allowed_sites must be a list of site identifiers'
            }), 400
        normalized_allowed_sites = []
        for site in allowed_sites:
            site_norm = _normalize_site_identifier(site)
            if not site_norm:
                return jsonify({
                    'success': False,
                    'error': f'Invalid site identifier: {site}'
                }), 400
            normalized_allowed_sites.append(site_norm)
        allowed_sites = sorted(list(set(normalized_allowed_sites)))

        if data.get('operator_plane'):
            op_sites = {'lemma.id'}
            if set(allowed_sites) - op_sites:
                return jsonify({
                    'success': False,
                    'error': 'operator_plane_site_lock',
                    'message': 'Operator-plane tokens must use allowed_sites=["lemma.id"] only.',
                }), 400
            if _normalize_site_identifier(intended_platform) not in {'lemma.id', 'lemma_platform'}:
                return jsonify({
                    'success': False,
                    'error': 'operator_plane_site_lock',
                    'message': 'Operator-plane tokens must target lemma.id only.',
                }), 400
            if 'admin' not in scope_norm:
                return jsonify({
                    'success': False,
                    'error': 'admin_scope_required',
                    'message': 'Operator-plane tokens require admin scope.',
                }), 400

        # SECURITY: Delegated agent tokens may only target sites owned/administered
        # by the delegating principal.
        ownership_ok, invalid_sites, owned_sites = _validate_allowed_sites_against_ownership(
            allowed_sites=allowed_sites,
            authorized_by_ppid=authorized_by,
            authorized_by_email=user_email,
        )
        if not ownership_ok:
            return jsonify({
                'success': False,
                'error': 'site_ownership_mismatch',
                'message': 'Delegated agent tokens can only be issued for sites you own/administer.',
                'requested_sites': allowed_sites,
                'invalid_sites': invalid_sites,
                'owned_sites': sorted(list(owned_sites)),
            }), 403
        delegation_id = delegation_id or f"dlg_{secrets.token_urlsafe(8)}"

        if audience is not None:
            if not re.match(r'^[a-z0-9._-]{2,64}$', audience):
                return jsonify({
                    'success': False,
                    'error': 'invalid_audience',
                    'message': 'audience must match [a-z0-9._-]{2,64}'
                }), 400
        else:
            audience = intended_platform

        # Validate scope
        valid_scopes = ['read', 'write', 'admin', 'test']
        scope = [s for s in scope if s in valid_scopes]
        if not scope:
            scope = ['read']
        allowed_paths, max_operations = _apply_default_admin_bounds(scope, allowed_paths, max_operations)

        encoded_description = _encode_credential_description(
            description,
            audience,
            delegation_reason=delegation_reason,
            delegation_id=delegation_id,
            acting_for_ppid=acting_for_ppid,
            requested_by_ppid=requested_by_ppid,
            delegated_by_user_ref=delegated_by_user_ref,
            acting_for_user_ref=acting_for_user_ref,
            requested_by_user_ref=requested_by_user_ref,
        )

        # Generate token
        token_id, plaintext_token, token_hash = generate_agent_token()

        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        try:
            credential_id = _store_agent_credential_record(
                token_id=token_id,
                token_hash=token_hash,
                authorized_by=authorized_by,
                user_email=user_email,
                scope=scope,
                allowed_sites=allowed_sites,
                expires_at=expires_at,
                agent_name=agent_name,
                description=encoded_description,
                task_description=task_description,
                task_hash_value=task_hash_value,
                allowed_paths=allowed_paths,
                max_operations=max_operations,
                delegation_id=delegation_id,
                delegation_reason=delegation_reason,
                acting_for_ppid=acting_for_ppid,
                requested_by_ppid=requested_by_ppid,
                delegated_by_user_ref=delegated_by_user_ref,
                acting_for_user_ref=acting_for_user_ref,
                requested_by_user_ref=requested_by_user_ref,
                audience=audience,
                subject_ref=token_id,
            )
        except Exception as db_err:
            logger.error(f"Failed to store agent credential: {db_err}")
            return jsonify({
                'success': False,
                'error': 'Database error',
                'message': str(db_err)
            }), 500

        logger.info(f"Agent credential issued: {token_id} for {authorized_by} (scope: {scope}, task: {task_description[:50] if task_description else 'none'}, expires: {expires_at})")

        response_data = {
            'success': True,
            'credential': {
                'token': plaintext_token,  # SHOWN ONLY ONCE
                'token_id': token_id,
                'scope': scope,
                'allowed_sites': allowed_sites,
                'expires_at': expires_at.isoformat() + 'Z',
                'ttl_hours': ttl_hours,
                'agent_name': agent_name,
                'delegation': {
                    'delegation_id': delegation_id,
                    'delegation_reason': delegation_reason,
                    'delegated_by_ppid': str(authorized_by),
                    'acting_for_ppid': acting_for_ppid,
                    'requested_by_ppid': requested_by_ppid,
                    'delegated_by_user_ref': delegated_by_user_ref,
                    'acting_for_user_ref': acting_for_user_ref,
                    'requested_by_user_ref': requested_by_user_ref,
                },
            },
            'usage': {
                'header': 'X-Agent-Token',
                'example': f'X-Agent-Token: {plaintext_token}'
            },
            'message': 'Credential issued. Save the token - it will not be shown again.'
        }

        # Add task-bound info if present
        if task_description:
            response_data['credential']['task'] = task_description
            response_data['credential']['task_hash'] = task_hash_value
        if allowed_paths:
            response_data['credential']['allowed_paths'] = allowed_paths
        if max_operations:
            response_data['credential']['max_operations'] = max_operations
        if audience:
            response_data['credential']['audience'] = audience

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Failed to issue agent credential: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# CREDENTIAL VALIDATION (Used by Decorator)
# ============================================

def validate_agent_token_internal(token):
    """
    Validate an agent token for use by auth decorators.
    
    Returns:
        (is_valid, credential_info) tuple
    """
    result = validate_agent_token(token)
    if result:
        return True, result
    return False, None


def validate_agent_token_with_reason(token):
    """
    Validate an agent token and provide deterministic machine-readable failure
    reasons for wrapper enforcement and conformance tests.

    Returns:
        (credential_info, None) when valid
        (None, error_code) when invalid
    """
    if not token:
        return None, 'auth_required'
    if not token.startswith('lm_agent_'):
        return None, 'invalid_token'

    token_hash = hash_token(token)
    cached_info = _get_cached_agent_token(token_hash)
    if cached_info:
        quota_info, quota_error = _apply_operation_quota(cached_info)
        if quota_error:
            _evict_cached_agent_token(token_hash)
            return None, quota_error
        _set_cached_agent_token_runtime(token_hash, quota_info)
        return quota_info, None

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, token_id, authorized_by_ppid, authorized_by_email,
                   scope, allowed_sites, expires_at, agent_name,
                   task_description, task_hash, allowed_paths, max_operations,
                   use_count, task_deviation_count, revoked, description
            FROM agent_credentials
            WHERE token_hash = %s
            LIMIT 1
        """, (token_hash,))

        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            _evict_cached_agent_token(token_hash)
            return None, 'invalid_token'

        is_revoked = bool(row[14])
        expires_at = row[6]
        if is_revoked:
            cursor.close()
            conn.close()
            _evict_cached_agent_token(token_hash)
            return None, 'token_revoked'
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            cursor.close()
            conn.close()
            _evict_cached_agent_token(token_hash)
            return None, 'token_expired'

        credential_id = row[0]
        use_count = row[12] or 0
        max_operations = row[11]
        if max_operations is not None and use_count >= max_operations:
            cursor.close()
            conn.close()
            logger.warning(f"Agent credential {row[1]} exceeded max_operations ({max_operations})")
            _evict_cached_agent_token(token_hash)
            return None, 'max_operations_exceeded'
        cursor.close()
        conn.close()

        allowed_sites = row[5] if isinstance(row[5], list) else (json.loads(row[5]) if row[5] else None)
        authorized_by_ppid = row[2]
        authorized_by_email = row[3]
        owned_sites = _get_owned_sites_for_delegator(authorized_by_ppid, authorized_by_email)
        if allowed_sites is not None:
            ownership_ok, _invalid_sites, _owned = _validate_allowed_sites_against_ownership(
                allowed_sites=allowed_sites,
                authorized_by_ppid=authorized_by_ppid,
                authorized_by_email=authorized_by_email,
            )
            if not ownership_ok:
                return None, 'site_ownership_mismatch'
        description_meta = _decode_credential_description(row[15])
        inferred_audience = description_meta.get('audience')
        if not inferred_audience and isinstance(allowed_sites, list) and len(allowed_sites) == 1:
            inferred_audience = str(allowed_sites[0]).strip().lower()

        credential_info = {
            'credential_id': credential_id,
            'token_id': row[1],
            'authorized_by_ppid': authorized_by_ppid,
            'authorized_by_email': authorized_by_email,
            'scope': row[4] if isinstance(row[4], list) else json.loads(row[4] or '["read"]'),
            'allowed_sites': allowed_sites,
            'owned_sites': sorted(list(owned_sites)),
            'expires_at': expires_at,
            'agent_name': row[7],
            'task_description': row[8],
            'task_hash': row[9],
            'allowed_paths': row[10] if isinstance(row[10], list) else (json.loads(row[10]) if row[10] else None),
            'max_operations': max_operations,
            'base_use_count': use_count,
            'use_count': use_count,
            'task_deviation_count': row[13] or 0,
            'audience': inferred_audience,
            'delegation_reason': description_meta.get('delegation_reason'),
            'delegation_id': description_meta.get('delegation_id'),
            'acting_for_ppid': description_meta.get('acting_for_ppid') or authorized_by_ppid,
            'requested_by_ppid': description_meta.get('requested_by_ppid') or authorized_by_ppid,
            'delegated_by_user_ref': description_meta.get('delegated_by_user_ref') or authorized_by_email,
            'acting_for_user_ref': description_meta.get('acting_for_user_ref'),
            'requested_by_user_ref': description_meta.get('requested_by_user_ref'),
            'validation_cache_hit': False,
        }
        credential_info, quota_error = _apply_operation_quota(credential_info)
        if quota_error:
            _evict_cached_agent_token(token_hash)
            return None, quota_error
        _set_cached_agent_token(token_hash, credential_info)
        return credential_info, None

    except Exception as e:
        logger.error(f"Token validation error: {e}")
        _evict_cached_agent_token(token_hash)
        return None, 'invalid_token'


def validate_agent_token(token):
    """
    Validate an agent token and return credential info if valid.

    Returns:
        dict with credential info if valid (includes task-bound fields)
        None if invalid/expired/revoked
    """
    info, _reason = validate_agent_token_with_reason(token)
    return info


def log_agent_action(credential_info, action, resource=None, success=True, status_code=200,
                     path_allowed=True, task_deviation=False, deviation_reason=None, decision_receipt=None):
    """
    Log an agent action to the audit trail with task deviation tracking.

    Args:
        credential_info: Dict with credential details
        action: The action being performed
        resource: Optional resource identifier
        success: Whether the action succeeded
        status_code: HTTP status code
        path_allowed: Whether the path was in allowed_paths
        task_deviation: Whether this was flagged as a task deviation
        deviation_reason: Why this was flagged as a deviation
    """
    try:
        acting_for_header = request.headers.get('X-Acting-For') or request.headers.get('X-Acting-For-PPID')
        acting_for_ppid = _normalize_ppid_claim(acting_for_header) or credential_info.get('acting_for_ppid') or credential_info.get('authorized_by_ppid')
        metadata = {
            'delegation_id': credential_info.get('delegation_id'),
            'delegation_reason': credential_info.get('delegation_reason'),
            'delegated_by_ppid': credential_info.get('authorized_by_ppid'),
            'acting_for_ppid': acting_for_ppid,
            'requested_by_ppid': credential_info.get('requested_by_ppid'),
            'delegated_by_user_ref': credential_info.get('delegated_by_user_ref'),
            'acting_for_user_ref': credential_info.get('acting_for_user_ref'),
            'requested_by_user_ref': credential_info.get('requested_by_user_ref'),
            'token_audience': credential_info.get('audience'),
            'decision_id': (decision_receipt or {}).get('decision_id'),
            'decision_signature': (decision_receipt or {}).get('signature'),
            'decision_reason': (decision_receipt or {}).get('reason'),
            'decision_outcome': (decision_receipt or {}).get('outcome'),
            'auth_mode_effective': request.headers.get('X-Lemma-Auth-Mode-Effective') or getattr(g, 'auth_mode_effective', None),
            'auth_mode_expected': request.headers.get('X-Lemma-Auth-Mode-Expected') or getattr(g, 'auth_mode_expected', None),
            'auth_shadow_decision': request.headers.get('X-Lemma-Auth-Shadow-Decision') or getattr(g, 'auth_shadow_decision', None),
            'auth_shadow_reason': request.headers.get('X-Lemma-Auth-Shadow-Reason') or getattr(g, 'auth_shadow_reason', None),
        }
        event = {
            'credential_id': credential_info.get('credential_id'),
            'token_id': credential_info.get('token_id'),
            'action': action,
            'resource': resource,
            'method': request.method,
            'path': request.path,
            'status_code': status_code,
            'success': success,
            'path_allowed': path_allowed,
            'task_deviation': task_deviation,
            'deviation_reason': deviation_reason,
            'metadata_json': json.dumps(metadata),
        }
        enqueued = _enqueue_audit_event(event)
        if not enqueued:
            _write_agent_audit_events([event])
        if task_deviation and credential_info.get('credential_id'):
            from api.database import get_db_connection

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE agent_credentials
                SET task_deviation_count = COALESCE(task_deviation_count, 0) + 1
                WHERE id = %s
                """,
                (credential_info.get('credential_id'),),
            )
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Failed to log agent action: {e}")


# ============================================
# DECORATOR: Require Agent or User Auth
# ============================================

def require_agent_or_user_auth(required_scope=None, enforce_task_bounds=True):
    """
    Decorator that allows either:
    1. Agent token (X-Agent-Token header)
    2. User auth (X-Lemma-Credential header or session)

    For agent tokens, also enforces task-bound authorization:
    - Checks if the request path is in allowed_paths
    - Logs task deviations when agent accesses paths outside their task
    - Can optionally block requests outside allowed_paths

    Usage:
        @require_agent_or_user_auth(required_scope='write')
        def my_endpoint():
            # g.agent_credential is set if agent auth
            # g.ppid is set if user auth
            # g.task_deviation is set if agent went outside allowed_paths
            pass

    Args:
        required_scope: Required scope (read, write, admin, test)
        enforce_task_bounds: If True, block requests outside allowed_paths.
                            If False, allow but log as deviation. Default True.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_started_at = time.perf_counter()
            shadow_reason = ""
            shadow_decision = "not_evaluated"
            shadow_profile = "authz_profile_v2"
            expected_mode = "compat_bearer"
            effective_mode = "compat_bearer"
            freshness_age_seconds = None
            freshness_max_age_seconds = None
            step_up_required = False

            def _finalize_auth_response(response_obj, credential_info=None, auth_elapsed_ms=None):
                response = make_response(response_obj)
                response = _attach_authz_timing_headers(
                    response,
                    auth_started_at,
                    credential_info,
                    auth_elapsed_ms,
                )
                response.headers['X-Lemma-Auth-Mode-Expected'] = str(expected_mode or "compat_bearer")
                response.headers['X-Lemma-Auth-Mode-Effective'] = str(effective_mode or "compat_bearer")
                response.headers['X-Lemma-Auth-Shadow-Decision'] = str(shadow_decision)
                response.headers['X-Lemma-Auth-Shadow-Reason'] = str(shadow_reason or "")
                response.headers['X-Lemma-Auth-Profile'] = str(shadow_profile)
                if freshness_age_seconds is not None:
                    response.headers['X-Lemma-Auth-Freshness-Age-S'] = f"{float(freshness_age_seconds):.3f}"
                if freshness_max_age_seconds is not None:
                    response.headers['X-Lemma-Auth-Freshness-Max-S'] = str(int(freshness_max_age_seconds))
                response.headers['X-Lemma-Auth-Step-Up-Required'] = "true" if step_up_required else "false"
                return response

            policy, effective_required_scope = _resolve_route_policy_scope(required_scope)
            expected_mode = str(getattr(policy, "auth_mode", "compat_bearer") or "compat_bearer")
            mode_decision = evaluate_mode_policy(
                expected_mode=expected_mode,
                headers=request.headers,
                compat_sunset_utc=getattr(policy, "compat_bearer_sunset_utc", None),
            )
            effective_mode = mode_decision.effective_mode
            if not mode_decision.allowed:
                return _finalize_auth_response(
                    _error_with_decision(
                        status_code=403,
                        error=mode_decision.reason_code or "AUTH_MODE_DOWNGRADE",
                        message="Authorization mode policy denied this request.",
                        reason=(mode_decision.reason_code or "AUTH_MODE_DOWNGRADE").lower(),
                    )
                )

            if _shadow_proof_eval_enabled():
                revoked_proof_ids, revoked_root_grant_ids, min_revocation_epoch = _proof_revocation_context(
                    getattr(g, "org_id", "org_default"),
                    getattr(g, "environment", "prod"),
                )
                shadow_eval = evaluate_proof_native(
                    headers=request.headers,
                    method=request.method,
                    path=request.path,
                    required_scope=effective_required_scope,
                    base_url=_proof_base_url(),
                    revoked_proof_ids=revoked_proof_ids,
                    revoked_root_grant_ids=revoked_root_grant_ids,
                    min_revocation_epoch=min_revocation_epoch,
                )
                shadow_profile = shadow_eval.profile
                shadow_reason = shadow_eval.reason_code
                if mode_decision.proof_present:
                    pop_required = bool(expected_mode == "proof_required")
                    pop_eval = validate_pop_replay(
                        headers=request.headers,
                        method=request.method,
                        path=request.path,
                        body_bytes=request.get_data(cache=True) if request.method in {"POST", "PUT", "PATCH", "DELETE"} else b"",
                        required=pop_required,
                    )
                    if not pop_eval.valid:
                        shadow_eval = shadow_eval if not shadow_eval.allowed else None
                        shadow_decision = "deny"
                        shadow_reason = pop_eval.code or pop_eval.reason or "AUTH_PROOF_OF_POSSESSION_FAILED"
                    else:
                        shadow_decision = "allow" if shadow_eval.allowed else "deny"
                else:
                    shadow_decision = "allow" if shadow_eval.allowed else "deny"

            if expected_mode == "proof_required" and mode_decision.proof_present and shadow_decision == "deny":
                return _finalize_auth_response(
                    _error_with_decision(
                        status_code=403,
                        error=shadow_reason or "AUTH_CHAIN_BROKEN",
                        message="Proof validation failed on a proof-required route; bearer fallback is disabled.",
                        reason=str(shadow_reason or "AUTH_CHAIN_BROKEN").lower(),
                    )
                )

            risk_tier = str(getattr(policy, "risk_tier", "low") or "low")
            freshness_header = request.headers.get("X-Lemma-Freshness-Last-Sync-Epoch")
            if freshness_header:
                try:
                    last_sync = float(freshness_header)
                except ValueError:
                    last_sync = None
            else:
                last_sync = None
            if last_sync is None:
                freshness_age_seconds = None
                freshness_max_age_seconds = is_fresh_enough(risk_tier, 0)[2]
                require_signal = str(os.environ.get('LEMMA_REQUIRE_FRESHNESS_SIGNAL', '0') or '0').strip().lower() in {'1', 'true', 'yes', 'on'}
                step_up_required = bool(require_signal and risk_tier in {"high", "critical"})
            else:
                fresh_ok, age_seconds, max_age = is_fresh_enough(risk_tier, last_sync)
                freshness_age_seconds = age_seconds
                freshness_max_age_seconds = max_age
                if risk_tier in {"high", "critical"} and not fresh_ok:
                    step_up_required = True
            g.auth_mode_expected = expected_mode
            g.auth_mode_effective = effective_mode
            g.auth_shadow_decision = shadow_decision
            g.auth_shadow_reason = shadow_reason
            g.auth_profile = shadow_profile
            enforce_high_freshness = str(os.environ.get('LEMMA_ENFORCE_HIGH_RISK_FRESHNESS', '0') or '0').strip().lower() in {'1', 'true', 'yes', 'on'}
            if step_up_required and (risk_tier == "critical" or (risk_tier == "high" and enforce_high_freshness)):
                return _finalize_auth_response(
                    _error_with_decision(
                        status_code=403,
                        error="AUTH_RISK_STEP_UP_REQUIRED",
                        message="Freshness window is stale for this route; perform step-up or refresh control-plane state.",
                        reason="risk_step_up_required",
                        extra={
                            "risk_tier": risk_tier,
                            "freshness_age_seconds": freshness_age_seconds,
                            "freshness_max_age_seconds": freshness_max_age_seconds,
                        },
                    )
                )
            # Try agent token first
            agent_token = request.headers.get('X-Agent-Token')

            if agent_token:
                credential_info, token_error = validate_agent_token_with_reason(agent_token)

                if not credential_info:
                    return _finalize_auth_response(_error_with_decision(
                        status_code=401,
                        error=token_error or 'invalid_token',
                        message='Token failed validation',
                        reason=token_error or 'invalid_token',
                    ))

                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='agent_token',
                    required_scope=effective_required_scope,
                    provided_scope=credential_info.get('scope', []),
                    site_binding=None,
                )
                if policy_error:
                    deny_receipt = _build_decision_receipt(
                        outcome='deny',
                        reason='policy_denied',
                        credential_info=credential_info,
                        status_code=403,
                    )
                    log_agent_action(
                        credential_info,
                        f'scope_or_policy_denied:{effective_required_scope or "none"}',
                        success=False,
                        status_code=403,
                        decision_receipt=deny_receipt,
                    )
                    response = make_response(policy_error)
                    payload = response.get_json(silent=True) if hasattr(response, "get_json") else None
                    if isinstance(payload, dict):
                        payload['decision'] = deny_receipt
                        response.set_data(json.dumps(payload))
                        response.mimetype = 'application/json'
                    return _finalize_auth_response(_attach_decision_headers(response, deny_receipt), credential_info)

                # Enforce optional site-level restrictions
                site_ok, blocked_site, allowed_sites_norm, requested_sites = check_site_allowed(credential_info)
                if not site_ok:
                    deny_receipt = _build_decision_receipt(
                        outcome='deny',
                        reason='site_not_allowed',
                        credential_info=credential_info,
                        status_code=403,
                    )
                    log_agent_action(
                        credential_info,
                        f'site_denied:{blocked_site or "unknown"}',
                        success=False,
                        status_code=403,
                        decision_receipt=deny_receipt,
                    )
                    return _finalize_auth_response(_error_with_decision(
                        status_code=403,
                        error='site_not_allowed',
                        message='This agent credential is restricted to specific sites. Request a new credential with the correct allowed_sites.',
                        reason='site_not_allowed',
                        credential_info=credential_info,
                        extra={
                            'site': blocked_site,
                            'allowed_sites': sorted(list(allowed_sites_norm)) if allowed_sites_norm is not None else None,
                        },
                    ), credential_info)

                # Check task-bound path restrictions
                allowed_paths = credential_info.get('allowed_paths')
                path_allowed, matching_pattern = check_path_allowed(request.path, allowed_paths)
                task_deviation = False
                deviation_reason = None

                if not path_allowed and allowed_paths is not None:
                    task_deviation = True
                    deviation_reason = f"Path {request.path} not in allowed_paths: {allowed_paths}"

                    if enforce_task_bounds:
                        # Block the request
                        deny_receipt = _build_decision_receipt(
                            outcome='deny',
                            reason='path_not_allowed',
                            credential_info=credential_info,
                            status_code=403,
                        )
                        log_agent_action(credential_info, f'path_denied:{request.path}',
                                        success=False, status_code=403,
                                        path_allowed=False, task_deviation=True,
                                        deviation_reason=deviation_reason,
                                        decision_receipt=deny_receipt)
                        return _finalize_auth_response(_error_with_decision(
                            status_code=403,
                            error='path_not_allowed',
                            message='This agent credential is restricted to specific paths. Request a new credential with broader access or correct allowed_paths.',
                            reason='path_not_allowed',
                            credential_info=credential_info,
                            extra={
                                'path': request.path,
                                'allowed_paths': allowed_paths,
                                'task': credential_info.get('task_description'),
                            },
                        ), credential_info)

                # Set credential info in request context
                g.agent_credential = credential_info
                g.ppid = credential_info['authorized_by_ppid']  # Use authorizer's PPID
                g.delegated_by_ppid = credential_info.get('authorized_by_ppid')
                g.acting_for_ppid = credential_info.get('acting_for_ppid') or credential_info.get('authorized_by_ppid')
                g.requested_by_ppid = credential_info.get('requested_by_ppid') or credential_info.get('authorized_by_ppid')
                g.delegated_by_user_ref = credential_info.get('delegated_by_user_ref')
                g.acting_for_user_ref = credential_info.get('acting_for_user_ref')
                g.requested_by_user_ref = credential_info.get('requested_by_user_ref')
                g.delegation_id = credential_info.get('delegation_id')
                g.authenticated = True
                g.auth_method = 'agent_token'
                g.task_deviation = task_deviation
                g.task_info = {
                    'task': credential_info.get('task_description'),
                    'task_hash': credential_info.get('task_hash'),
                    'allowed_sites': credential_info.get('allowed_sites'),
                    'requested_sites': requested_sites,
                    'allowed_paths': allowed_paths,
                    'path_allowed': path_allowed,
                    'matching_pattern': matching_pattern,
                    'operations_remaining': (
                        credential_info['max_operations'] - credential_info['use_count']
                        if credential_info.get('max_operations') else None
                    )
                }

                # Log the action (with deviation info if applicable)
                allow_receipt = _build_decision_receipt(
                    outcome='allow',
                    reason='agent_token_allowed',
                    credential_info=credential_info,
                    status_code=200,
                )
                log_agent_action(credential_info, f'{request.method}:{request.path}',
                                path_allowed=path_allowed, task_deviation=task_deviation,
                                deviation_reason=deviation_reason,
                                decision_receipt=allow_receipt)

                auth_elapsed_ms = (time.perf_counter() - auth_started_at) * 1000.0
                response = make_response(f(*args, **kwargs))
                return _finalize_auth_response(
                    _attach_decision_headers(response, allow_receipt),
                    credential_info,
                    auth_elapsed_ms,
                )

            # Support browser agent sessions created via /api/agent/session.
            if session.get('agent_authenticated'):
                session_scope = session.get('agent_scope', [])
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='agent_token',
                    required_scope=effective_required_scope,
                    provided_scope=session_scope,
                    site_binding=None,
                )
                if policy_error:
                    return _finalize_auth_response(policy_error)

                session_allowed_sites = session.get('agent_allowed_sites')
                if session_allowed_sites is not None:
                    site_ok, blocked_site, allowed_sites_norm, requested_sites = check_site_allowed({
                        'allowed_sites': session_allowed_sites
                    })
                    if not site_ok:
                        return jsonify({
                            'success': False,
                            'error': 'site_not_allowed',
                            'site': blocked_site,
                            'allowed_sites': sorted(list(allowed_sites_norm)) if allowed_sites_norm is not None else None,
                            'message': 'This agent session is restricted to specific sites.'
                        }), 403

                session_ppid = session.get('agent_ppid')
                if session_ppid:
                    g.ppid = session_ppid
                g.authenticated = True
                g.auth_method = 'agent_session'
                auth_elapsed_ms = (time.perf_counter() - auth_started_at) * 1000.0
                return _finalize_auth_response(f(*args, **kwargs), auth_elapsed_ms=auth_elapsed_ms)

            # Fall back to user auth (unified verifier path)
            lemma_principal, lemma_error = extract_user_lemma_principal(request.headers)
            api_key = _extract_api_key_from_request()

            if lemma_principal:
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type=lemma_principal.principal_type,
                    required_scope=effective_required_scope,
                    provided_scope=lemma_principal.scope,
                    site_binding=lemma_principal.site_binding,
                )
                if policy_error:
                    return _finalize_auth_response(policy_error)
                g.ppid = lemma_principal.ppid
                g.credential_id = lemma_principal.credential_id
                g.permission_id = lemma_principal.permission_id
                g.authenticated = True
                g.auth_method = lemma_principal.auth_method
                auth_elapsed_ms = (time.perf_counter() - auth_started_at) * 1000.0
                return _finalize_auth_response(f(*args, **kwargs), auth_elapsed_ms=auth_elapsed_ms)

            is_valid_key, key_info = _validate_request_api_key(api_key)
            if is_valid_key:
                policy_error = _enforce_route_policy_for_principal(
                    policy=policy,
                    principal_type='api_key',
                    required_scope=effective_required_scope,
                    provided_scope=[],
                    site_binding=None,
                    allow_unscoped=True,
                )
                if policy_error:
                    return _finalize_auth_response(policy_error)
                g.api_key = api_key
                g.api_key_info = key_info
                g.authenticated = True
                g.auth_method = 'api_key'
                auth_elapsed_ms = (time.perf_counter() - auth_started_at) * 1000.0
                return _finalize_auth_response(f(*args, **kwargs), auth_elapsed_ms=auth_elapsed_ms)

            return _finalize_auth_response((jsonify({
                'success': False,
                'error': 'auth_required',
                'message': 'Provide X-Agent-Token, X-Lemma-Credential, X-API-Key, or Authorization: Bearer <api_key> header',
                'lemma_error': lemma_error
            }), 401))

        return decorated_function
    return decorator


# ============================================
# CREDENTIAL MANAGEMENT ENDPOINTS
# ============================================

@agent_credentials_bp.route('/api/agent/credentials', methods=['GET'])
@restricted_cross_origin()
def list_agent_credentials():
    """List all agent credentials for the authenticated user, including task-bound info."""
    authorized_by, auth_error = _resolve_agent_owner_ppid()
    if not authorized_by:
        return jsonify({
            'success': False,
            'error': auth_error or 'Authentication required'
        }), 401

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT token_id, scope, allowed_sites, issued_at, expires_at,
                   revoked, revoked_at, agent_name, description, last_used_at, use_count,
                   task_description, task_hash, allowed_paths, max_operations, task_deviation_count
            FROM agent_credentials
            WHERE authorized_by_ppid = %s
            ORDER BY issued_at DESC
        """, (authorized_by,))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        credentials = []
        for row in rows:
            cred = {
                'token_id': row[0],
                'scope': row[1] if isinstance(row[1], list) else json.loads(row[1] or '[]'),
                'allowed_sites': row[2] if isinstance(row[2], list) else (json.loads(row[2]) if row[2] else None),
                'issued_at': row[3].isoformat() + 'Z' if row[3] else None,
                'expires_at': row[4].isoformat() + 'Z' if row[4] else None,
                'revoked': row[5],
                'revoked_at': row[6].isoformat() + 'Z' if row[6] else None,
                'agent_name': row[7],
                'description': row[8],
                'last_used_at': row[9].isoformat() + 'Z' if row[9] else None,
                'use_count': row[10],
                'status': 'revoked' if row[5] else ('expired' if row[4] and row[4] < datetime.now(timezone.utc) else 'active'),
                # Task-bound fields
                'task_description': row[11],
                'task_hash': row[12],
                'allowed_paths': row[13] if isinstance(row[13], list) else (json.loads(row[13]) if row[13] else None),
                'max_operations': row[14],
                'task_deviation_count': row[15] or 0,
                'is_task_bound': row[11] is not None or row[13] is not None
            }
            credentials.append(cred)

        return jsonify({
            'success': True,
            'credentials': credentials
        })

    except Exception as e:
        logger.error(f"Failed to list agent credentials: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@agent_credentials_bp.route('/api/agent/credentials/<token_id>/revoke', methods=['POST'])
@restricted_cross_origin()
@require_agent_or_user_session()
def revoke_agent_credential(token_id):
    """
    Revoke an agent credential immediately.
    
    This is the KILL SWITCH - use it if:
    - Agent is behaving unexpectedly
    - Session is no longer needed
    - Security concern
    """
    ppid = _extract_ppid_from_lemma_header() or session.get('ppid')
    customer_id = session.get('customer_id')

    # Machine flow: allow owner resolution from a lemma-bound admin agent token.
    if not ppid:
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token and agent_token.startswith('lm_agent_'):
            token_info = validate_agent_token(agent_token)
            if token_info:
                token_scope = token_info.get('scope') or []
                if isinstance(token_scope, str):
                    token_scope = [token_scope]
                token_scope = [str(s).strip().lower() for s in token_scope if s]
                if 'admin' in token_scope:
                    ppid = token_info.get('authorized_by_ppid') or token_info.get('authorized_by')

    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'auth_required'
        }), 401

    authorized_by = ppid or f"customer:{customer_id}"
    
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual revocation')
    
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Only allow revoking your own credentials
        cursor.execute("""
            UPDATE agent_credentials
            SET revoked = TRUE, revoked_at = NOW(), revoked_reason = %s
            WHERE token_id = %s AND authorized_by_ppid = %s
            RETURNING id
        """, (reason, token_id, authorized_by))
        
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        if not result:
            return jsonify({
                'success': False,
                'error': 'Credential not found or not owned by you'
            }), 404

        revoke_delegation_for_token(token_id=token_id, reason=reason, revoked_by=authorized_by)
        record_revocation(
            subject_type='token',
            subject_ref=token_id,
            delegator_ppid=ppid,
            reason_code='token_revoked',
            revoked_by=authorized_by,
            metadata={'reason': reason},
            org_id=getattr(g, "org_id", "org_default"),
            environment=getattr(g, "environment", "prod"),
            root_type='passkey_root',
        )
        
        logger.info(f"Agent credential revoked: {token_id} by {authorized_by} (reason: {reason})")
        
        return jsonify({
            'success': True,
            'message': f'Credential {token_id} has been revoked',
            'revoked_at': datetime.utcnow().isoformat() + 'Z'
        })
        
    except Exception as e:
        logger.error(f"Failed to revoke credential: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@agent_credentials_bp.route('/api/agent/credentials/audit', methods=['GET'])
@restricted_cross_origin()
def get_agent_audit_log():
    """Get audit log for agent actions."""
    ppid = _extract_ppid_from_lemma_header()
    customer_id = session.get('customer_id')
    
    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    authorized_by = ppid or f"customer:{customer_id}"
    
    # Optional filters
    token_id = request.args.get('token_id')
    limit = min(int(request.args.get('limit', 100)), 500)
    
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if token_id:
            cursor.execute("""
                SELECT al.token_id, al.action, al.resource, al.method, al.path,
                       al.status_code, al.success, al.timestamp, al.metadata
                FROM agent_audit_log al
                JOIN agent_credentials ac ON al.credential_id = ac.id
                WHERE ac.authorized_by_ppid = %s AND al.token_id = %s
                ORDER BY al.timestamp DESC
                LIMIT %s
            """, (authorized_by, token_id, limit))
        else:
            cursor.execute("""
                SELECT al.token_id, al.action, al.resource, al.method, al.path,
                       al.status_code, al.success, al.timestamp, al.metadata
                FROM agent_audit_log al
                JOIN agent_credentials ac ON al.credential_id = ac.id
                WHERE ac.authorized_by_ppid = %s
                ORDER BY al.timestamp DESC
                LIMIT %s
            """, (authorized_by, limit))
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        audit_log = []
        for row in rows:
            metadata = row[8] if isinstance(row[8], dict) else (json.loads(row[8]) if row[8] else {})
            audit_log.append({
                'token_id': row[0],
                'action': row[1],
                'resource': row[2],
                'method': row[3],
                'path': row[4],
                'status_code': row[5],
                'success': row[6],
                'timestamp': row[7].isoformat() + 'Z' if row[7] else None,
                'delegation': {
                    'delegation_id': metadata.get('delegation_id'),
                    'delegation_reason': metadata.get('delegation_reason'),
                    'delegated_by_ppid': metadata.get('delegated_by_ppid'),
                    'acting_for_ppid': metadata.get('acting_for_ppid'),
                    'requested_by_ppid': metadata.get('requested_by_ppid'),
                    'delegated_by_user_ref': metadata.get('delegated_by_user_ref'),
                    'acting_for_user_ref': metadata.get('acting_for_user_ref'),
                    'requested_by_user_ref': metadata.get('requested_by_user_ref'),
                },
            })
        
        return jsonify({
            'success': True,
            'audit_log': audit_log
        })

    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# TASK ADHERENCE REPORT
# ============================================

@agent_credentials_bp.route('/api/agent/credentials/<token_id>/task-report', methods=['GET'])
@restricted_cross_origin()
def get_task_adherence_report(token_id):
    """
    Get a task adherence report for a specific agent credential.

    Shows:
    - Task description and hash
    - Allowed paths vs actual paths accessed
    - Deviation count and details
    - Operations used vs max allowed

    This helps humans verify that agents stayed on-task.
    """
    ppid = _extract_ppid_from_lemma_header()
    customer_id = session.get('customer_id')

    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401

    authorized_by = ppid or f"customer:{customer_id}"

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get credential info
        cursor.execute("""
            SELECT id, token_id, agent_name, task_description, task_hash,
                   allowed_paths, max_operations, use_count, task_deviation_count,
                   issued_at, expires_at, revoked
            FROM agent_credentials
            WHERE token_id = %s AND authorized_by_ppid = %s
        """, (token_id, authorized_by))

        cred_row = cursor.fetchone()

        if not cred_row:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Credential not found or not owned by you'
            }), 404

        credential_id = cred_row[0]
        allowed_paths = cred_row[5] if isinstance(cred_row[5], list) else (json.loads(cred_row[5]) if cred_row[5] else None)
        max_operations = cred_row[6]
        use_count = cred_row[7] or 0
        deviation_count = cred_row[8] or 0

        # Get all unique paths accessed
        cursor.execute("""
            SELECT DISTINCT path, COUNT(*) as count
            FROM agent_audit_log
            WHERE credential_id = %s
            GROUP BY path
            ORDER BY count DESC
        """, (credential_id,))

        path_rows = cursor.fetchall()
        paths_accessed = [{'path': row[0], 'count': row[1]} for row in path_rows]

        # Get deviation details
        cursor.execute("""
            SELECT path, action, deviation_reason, timestamp
            FROM agent_audit_log
            WHERE credential_id = %s AND task_deviation = TRUE
            ORDER BY timestamp DESC
            LIMIT 50
        """, (credential_id,))

        deviation_rows = cursor.fetchall()
        deviations = [{
            'path': row[0],
            'action': row[1],
            'reason': row[2],
            'timestamp': row[3].isoformat() + 'Z' if row[3] else None
        } for row in deviation_rows]

        # Calculate adherence score
        if use_count > 0:
            adherence_score = round((1 - (deviation_count / use_count)) * 100, 1)
        else:
            adherence_score = 100.0

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'report': {
                'token_id': cred_row[1],
                'agent_name': cred_row[2],
                'task': {
                    'description': cred_row[3],
                    'hash': cred_row[4],
                    'is_task_bound': cred_row[3] is not None or allowed_paths is not None
                },
                'bounds': {
                    'allowed_paths': allowed_paths,
                    'max_operations': max_operations
                },
                'usage': {
                    'operations_used': use_count,
                    'operations_remaining': max_operations - use_count if max_operations else None,
                    'deviation_count': deviation_count,
                    'adherence_score': adherence_score,
                    'adherence_grade': (
                        'A' if adherence_score >= 95 else
                        'B' if adherence_score >= 85 else
                        'C' if adherence_score >= 70 else
                        'D' if adherence_score >= 50 else 'F'
                    )
                },
                'paths_accessed': paths_accessed,
                'deviations': deviations,
                'credential_status': {
                    'issued_at': cred_row[9].isoformat() + 'Z' if cred_row[9] else None,
                    'expires_at': cred_row[10].isoformat() + 'Z' if cred_row[10] else None,
                    'revoked': cred_row[11]
                }
            }
        })

    except Exception as e:
        logger.error(f"Failed to get task report: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# MONITORING ENDPOINTS (for custom site UIs)
# ============================================

@agent_credentials_bp.route('/api/agent/monitor/tokens', methods=['GET'])
@restricted_cross_origin()
def get_agent_monitor_tokens():
    """List agent credentials for monitoring dashboards."""
    identity, auth_error = _resolve_monitor_identity()
    if auth_error:
        message, status = auth_error
        return jsonify({'success': False, 'error': message}), status

    include_revoked = request.args.get('include_revoked', 'false').lower() == 'true'
    limit = min(max(int(request.args.get('limit', 100)), 1), 500)

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        owner_filter, owner_params = _build_owner_filter(identity, alias='ac')
        revoked_filter = '' if include_revoked else 'AND ac.revoked = FALSE'

        query = f"""
            SELECT ac.token_id, ac.agent_name, ac.scope, ac.allowed_paths, ac.max_operations,
                   ac.use_count, ac.task_deviation_count, ac.last_used_at, ac.issued_at, ac.expires_at,
                   ac.revoked, ac.revoked_at, ac.description
            FROM agent_credentials ac
            WHERE {owner_filter}
            {revoked_filter}
            ORDER BY ac.issued_at DESC
            LIMIT %s
        """
        cursor.execute(query, (*owner_params, limit))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        tokens = []
        for row in rows:
            scope = row[2] if isinstance(row[2], list) else json.loads(row[2] or '[]')
            allowed_paths = row[3] if isinstance(row[3], list) else (json.loads(row[3]) if row[3] else None)
            use_count = row[5] or 0
            max_ops = row[4]
            tokens.append({
                'token_id': row[0],
                'agent_name': row[1],
                'scope': scope,
                'allowed_paths': allowed_paths,
                'max_operations': max_ops,
                'use_count': use_count,
                'operations_remaining': (max_ops - use_count) if max_ops is not None else None,
                'task_deviation_count': row[6] or 0,
                'last_used_at': row[7].isoformat() + 'Z' if row[7] else None,
                'issued_at': row[8].isoformat() + 'Z' if row[8] else None,
                'expires_at': row[9].isoformat() + 'Z' if row[9] else None,
                'revoked': row[10],
                'revoked_at': row[11].isoformat() + 'Z' if row[11] else None,
                'description': row[12],
                'status': 'revoked' if row[10] else ('expired' if row[9] and row[9] < datetime.now(timezone.utc) else 'active')
            })

        return jsonify({
            'success': True,
            'auth_method': identity.get('auth_method'),
            'tokens': tokens
        })
    except Exception as e:
        logger.error(f"Failed to load monitor tokens: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agent_credentials_bp.route('/api/agent/monitor/events', methods=['GET'])
@restricted_cross_origin()
def get_agent_monitor_events():
    """Get detailed per-request audit events for monitoring dashboards."""
    identity, auth_error = _resolve_monitor_identity()
    if auth_error:
        message, status = auth_error
        return jsonify({'success': False, 'error': message}), status

    token_id = request.args.get('token_id')
    status_filter = (request.args.get('status') or 'all').lower()  # all | success | failure
    hours = min(max(int(request.args.get('hours', 24)), 1), 24 * 30)
    limit = min(max(int(request.args.get('limit', 200)), 1), 1000)

    if status_filter not in ('all', 'success', 'failure'):
        return jsonify({'success': False, 'error': 'status must be one of: all, success, failure'}), 400

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        owner_filter, owner_params = _build_owner_filter(identity, alias='ac')
        where_parts = [
            owner_filter,
            "al.timestamp >= (NOW() - (%s || ' hours')::interval)"
        ]
        params = [*owner_params, str(hours)]

        if token_id:
            where_parts.append("al.token_id = %s")
            params.append(token_id)

        if status_filter == 'success':
            where_parts.append("al.success = TRUE")
        elif status_filter == 'failure':
            where_parts.append("al.success = FALSE")

        query = f"""
            SELECT al.token_id, al.action, al.resource, al.method, al.path,
                   al.status_code, al.success, al.path_allowed, al.task_deviation,
                   al.deviation_reason, al.timestamp
            FROM agent_audit_log al
            JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE {' AND '.join(where_parts)}
            ORDER BY al.timestamp DESC
            LIMIT %s
        """
        params.append(limit)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        events = [{
            'token_id': row[0],
            'action': row[1],
            'resource': row[2],
            'method': row[3],
            'path': row[4],
            'status_code': row[5],
            'success': row[6],
            'path_allowed': row[7],
            'task_deviation': row[8],
            'deviation_reason': row[9],
            'timestamp': row[10].isoformat() + 'Z' if row[10] else None
        } for row in rows]

        return jsonify({
            'success': True,
            'auth_method': identity.get('auth_method'),
            'window_hours': hours,
            'events': events
        })
    except Exception as e:
        logger.error(f"Failed to load monitor events: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@agent_credentials_bp.route('/api/agent/monitor/log-external', methods=['POST'])
@restricted_cross_origin()
def log_external_agent_activity():
    """
    Ingest external API activity for AIM dashboards.

    Used by customer-side gateways/firewalls that enforce Lemma policy before
    forwarding to third-party APIs, so AIM can reflect cross-API activity.
    """
    credential_info = None
    proof_identity = None
    agent_token = request.headers.get('X-Agent-Token')
    if agent_token:
        credential_info, reason = validate_agent_token_with_reason(agent_token)
        if not credential_info:
            message = reason or 'invalid_token'
            status = 403 if message == 'max_operations_exceeded' else 401
            return jsonify({'success': False, 'error': message}), status
    else:
        proof_identity = _extract_ppid_from_lemma_header()
        if not proof_identity:
            return jsonify({'success': False, 'error': 'missing_auth'}), 401

    payload = request.get_json(silent=True) or {}
    action = str(payload.get('action') or 'external_api_call').strip() or 'external_api_call'
    resource = str(payload.get('resource') or payload.get('upstream_api_id') or 'external').strip() or 'external'
    method = str(payload.get('method') or 'GET').strip().upper()
    path = str(payload.get('path') or payload.get('target_path') or '/').strip() or '/'
    status_code = int(payload.get('status_code') or 200)
    success = bool(payload.get('success', status_code < 400))
    path_allowed = bool(payload.get('path_allowed', True))
    task_deviation = bool(payload.get('task_deviation', False))
    deviation_reason = str(payload.get('deviation_reason') or '').strip() or None

    delegated_by_ppid = credential_info.get('authorized_by_ppid') if credential_info else proof_identity
    token_id = (
        credential_info.get('token_id')
        if credential_info
        else str(payload.get('proof_id') or f"proof:{(delegated_by_ppid or 'unknown')[-8:]}")
    )
    metadata = {
        'source': 'external_firewall',
        'upstream_api_id': payload.get('upstream_api_id'),
        'upstream_base_url': payload.get('upstream_base_url'),
        'target_url': payload.get('target_url'),
        'risk_tier': payload.get('risk_tier'),
        'runtime_id': payload.get('runtime_id'),
        'policy_profile': payload.get('policy_profile'),
        'reason_code': payload.get('reason_code'),
        'request_correlation_id': payload.get('request_correlation_id'),
        'auth_mode': 'token' if credential_info else 'proof',
        'delegation_id': credential_info.get('delegation_id') if credential_info else payload.get('delegation_id'),
        'delegation_reason': credential_info.get('delegation_reason') if credential_info else payload.get('delegation_reason'),
        'delegated_by_ppid': delegated_by_ppid,
        'acting_for_ppid': (
            credential_info.get('acting_for_ppid') or credential_info.get('authorized_by_ppid')
        ) if credential_info else payload.get('acting_for_ppid') or delegated_by_ppid,
        'requested_by_ppid': credential_info.get('requested_by_ppid') if credential_info else payload.get('requested_by_ppid'),
        'delegated_by_user_ref': credential_info.get('delegated_by_user_ref') if credential_info else payload.get('delegated_by_user_ref'),
        'proof_id': payload.get('proof_id'),
    }
    event = {
        'credential_id': credential_info.get('credential_id') if credential_info else None,
        'token_id': token_id,
        'action': action,
        'resource': resource,
        'method': method,
        'path': path,
        'status_code': status_code,
        'success': success,
        'path_allowed': path_allowed,
        'task_deviation': task_deviation,
        'deviation_reason': deviation_reason,
        'metadata_json': json.dumps(metadata),
    }
    enqueued = _enqueue_audit_event(event)
    if not enqueued:
        _write_agent_audit_events([event])

    if task_deviation and credential_info and credential_info.get('credential_id'):
        try:
            from api.database import get_db_connection

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE agent_credentials
                SET task_deviation_count = COALESCE(task_deviation_count, 0) + 1
                WHERE id = %s
                """,
                (credential_info.get('credential_id'),),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as exc:
            logger.warning(f"Failed to increment deviation count from external log: {exc}")

    return jsonify({'success': True, 'logged': True})


@agent_credentials_bp.route('/api/agent/monitor/summary', methods=['GET'])
@restricted_cross_origin()
def get_agent_monitor_summary():
    """Get aggregate visibility metrics for delegated agent activity."""
    identity, auth_error = _resolve_monitor_identity()
    if auth_error:
        message, status = auth_error
        return jsonify({'success': False, 'error': message}), status

    token_id = request.args.get('token_id')
    hours = min(max(int(request.args.get('hours', 24)), 1), 24 * 30)

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        owner_filter, owner_params = _build_owner_filter(identity, alias='ac')
        where_parts = [
            owner_filter,
            "al.timestamp >= (NOW() - (%s || ' hours')::interval)"
        ]
        params = [*owner_params, str(hours)]

        if token_id:
            where_parts.append("al.token_id = %s")
            params.append(token_id)

        summary_query = f"""
            SELECT
                COUNT(*) AS total_actions,
                COUNT(*) FILTER (WHERE al.success = TRUE) AS success_count,
                COUNT(*) FILTER (WHERE al.success = FALSE) AS failure_count,
                COUNT(*) FILTER (WHERE al.status_code = 403 OR al.path_allowed = FALSE) AS denied_count,
                COUNT(*) FILTER (WHERE al.task_deviation = TRUE) AS deviation_count,
                COUNT(DISTINCT al.path) AS unique_paths,
                MAX(al.timestamp) AS last_seen_at
            FROM agent_audit_log al
            JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE {' AND '.join(where_parts)}
        """
        cursor.execute(summary_query, tuple(params))
        row = cursor.fetchone()

        path_query = f"""
            SELECT al.path, COUNT(*) AS count
            FROM agent_audit_log al
            JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE {' AND '.join(where_parts)}
            GROUP BY al.path
            ORDER BY count DESC
            LIMIT 10
        """
        cursor.execute(path_query, tuple(params))
        path_rows = cursor.fetchall()

        status_query = f"""
            SELECT al.status_code, COUNT(*) AS count
            FROM agent_audit_log al
            JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE {' AND '.join(where_parts)}
            GROUP BY al.status_code
            ORDER BY count DESC
            LIMIT 10
        """
        cursor.execute(status_query, tuple(params))
        status_rows = cursor.fetchall()

        cursor.close()
        conn.close()

        summary = {
            'total_actions': row[0] or 0,
            'success_count': row[1] or 0,
            'failure_count': row[2] or 0,
            'denied_count': row[3] or 0,
            'deviation_count': row[4] or 0,
            'unique_paths': row[5] or 0,
            'last_seen_at': row[6].isoformat() + 'Z' if row[6] else None,
            'top_paths': [{'path': p[0], 'count': p[1]} for p in path_rows],
            'status_codes': [{'status_code': s[0], 'count': s[1]} for s in status_rows]
        }

        return jsonify({
            'success': True,
            'auth_method': identity.get('auth_method'),
            'window_hours': hours,
            'token_id': token_id,
            'summary': summary
        })
    except Exception as e:
        logger.error(f"Failed to load monitor summary: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# QUICK VALIDATION ENDPOINT (For Testing)
# ============================================


def _issue_agent_token_from_inputs(
    *,
    ttl_hours: int,
    scope_param,
    agent_name: str,
    task_description: str | None,
    allowed_paths,
    max_operations,
    allowed_sites,
    intended_platform: str | None,
    delegation_reason: str | None = None,
    delegation_id: str | None = None,
    acting_for_ppid: str | None = None,
    requested_by_ppid: str | None = None,
    delegated_by_user_ref: str | None = None,
    acting_for_user_ref: str | None = None,
    requested_by_user_ref: str | None = None,
) -> tuple[dict, int]:
    """Shared issuance implementation for auto-issue and CLI browser login."""
    is_allowed, error_response = _require_delegation_admin_session()
    if not is_allowed:
        return error_response

    passkey_verified = session.get('passkey_verified', False)
    auth_method = session.get('auth_method')
    user_email = session.get('user_email')
    ppid = getattr(g, 'delegation_ppid', None) or session.get('ppid') or _extract_ppid_from_lemma_header()
    logger.info(
        "Agent issuance check: passkey_verified=%s, auth_method=%s, has_ppid=%s",
        passkey_verified,
        auth_method,
        bool(ppid),
    )

    if not ppid or not str(ppid).startswith('did:lemma:ppid_'):
        return jsonify({
            'success': False,
            'error': 'ppid_required',
            'message': 'Please unlock wallet and provide a valid lemma PPID to issue delegated credentials.'
        }), 403

    authorized_by = str(ppid)
    acting_for_ppid = _normalize_ppid_claim(acting_for_ppid) or authorized_by
    requested_by_ppid = _normalize_ppid_claim(requested_by_ppid) or authorized_by
    delegation_reason = str(delegation_reason or '').strip() or None
    delegation_id = str(delegation_id or '').strip() or f"dlg_{secrets.token_urlsafe(8)}"
    delegated_by_user_ref = str(delegated_by_user_ref or user_email or '').strip() or None
    acting_for_user_ref = str(acting_for_user_ref or '').strip() or None
    requested_by_user_ref = str(requested_by_user_ref or '').strip() or None
    ttl_hours = min(max(int(ttl_hours), 1), 24)

    if allowed_sites is None:
        allowed_sites = [_normalize_site_identifier(intended_platform) or 'lemma.id']
    if not isinstance(allowed_sites, list):
        return jsonify({
            'success': False,
            'error': 'allowed_sites must be a list of site identifiers'
        }), 400

    normalized_allowed_sites = []
    for site in allowed_sites:
        site_norm = _normalize_site_identifier(site)
        if not site_norm:
            return jsonify({
                'success': False,
                'error': f'Invalid site identifier: {site}'
            }), 400
        normalized_allowed_sites.append(site_norm)
    allowed_sites = sorted(list(set(normalized_allowed_sites)))

    ownership_ok, invalid_sites, owned_sites = _validate_allowed_sites_against_ownership(
        allowed_sites=allowed_sites,
        authorized_by_ppid=authorized_by,
        authorized_by_email=user_email,
    )
    if not ownership_ok:
        return jsonify({
            'success': False,
            'error': 'site_ownership_mismatch',
            'message': 'Delegated agent tokens can only be issued for sites you own/administer.',
            'requested_sites': allowed_sites,
            'invalid_sites': invalid_sites,
            'owned_sites': sorted(list(owned_sites)),
        }), 403

    if isinstance(scope_param, list):
        scope = [s for s in scope_param if s in ['read', 'write', 'admin', 'test']]
    else:
        scope = [
            s.strip() for s in str(scope_param or "").split(",")
            if s.strip() in ['read', 'write', 'admin', 'test']
        ]
    if not scope:
        scope = ['read', 'write']
    allowed_paths, max_operations = _apply_default_admin_bounds(scope, allowed_paths, max_operations)

    task_hash_value = hash_task(task_description)
    token_id, plaintext_token, token_hash = generate_agent_token()
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

    try:
        _store_agent_credential_record(
            token_id=token_id,
            token_hash=token_hash,
            authorized_by=authorized_by,
            user_email=user_email,
            scope=scope,
            allowed_sites=allowed_sites,
            expires_at=expires_at,
            agent_name=agent_name,
            description=_encode_credential_description(
                f'Auto-issued via active session (auth_method: {auth_method})',
                delegation_reason=delegation_reason,
                delegation_id=delegation_id,
                acting_for_ppid=acting_for_ppid,
                requested_by_ppid=requested_by_ppid,
                delegated_by_user_ref=delegated_by_user_ref,
                acting_for_user_ref=acting_for_user_ref,
                requested_by_user_ref=requested_by_user_ref,
            ),
            task_description=task_description,
            task_hash_value=task_hash_value,
            allowed_paths=allowed_paths,
            max_operations=max_operations,
            delegation_id=delegation_id,
            delegation_reason=delegation_reason,
            acting_for_ppid=acting_for_ppid,
            requested_by_ppid=requested_by_ppid,
            delegated_by_user_ref=delegated_by_user_ref,
            acting_for_user_ref=acting_for_user_ref,
            requested_by_user_ref=requested_by_user_ref,
            audience=allowed_sites[0] if allowed_sites else None,
            subject_ref=token_id,
        )
    except Exception as db_err:
        logger.error(f"Failed to store auto-issued credential: {db_err}")
        return jsonify({
            'success': False,
            'error': 'Database error',
            'message': str(db_err)
        }), 500

    response_data = {
        'success': True,
        'token': plaintext_token,
        'token_id': token_id,
        'scope': scope,
        'allowed_sites': allowed_sites,
        'expires_at': expires_at.isoformat() + 'Z',
        'ttl_hours': ttl_hours,
        'authorized_by': authorized_by,
        'delegation': {
            'delegation_id': delegation_id,
            'delegation_reason': delegation_reason,
            'delegated_by_ppid': authorized_by,
            'acting_for_ppid': acting_for_ppid,
            'requested_by_ppid': requested_by_ppid,
            'delegated_by_user_ref': delegated_by_user_ref,
            'acting_for_user_ref': acting_for_user_ref,
            'requested_by_user_ref': requested_by_user_ref,
        },
        'message': 'Token issued from active wallet session'
    }
    if task_description:
        response_data['task'] = task_description
        response_data['task_hash'] = task_hash_value
    if allowed_paths:
        response_data['allowed_paths'] = allowed_paths
    if max_operations:
        response_data['max_operations'] = max_operations

    return jsonify(response_data), 200

@agent_credentials_bp.route('/api/agent/auto-issue', methods=['GET', 'POST'])
@agent_credentials_bp.route('/api/agent/credentials/session-issue', methods=['POST'])
@rate_limit(credential_issue_limit, key_func=get_issuance_identifier)
@require_agent_or_user_session()
def auto_issue_agent_credential():
    """
    Auto-issue an agent credential if wallet session is active.

    This endpoint checks the session cookie - if the user has an active
    wallet session with admin credentials, it automatically issues a token.

    This allows AI agents to fetch tokens directly when the human has
    already authenticated via passkey.

    GET /api/agent/auto-issue?ttl=4&scope=read,write&task=Fix%20bug&paths=/api/sites/*

    POST /api/agent/auto-issue
    {
        "ttl": 4,
        "scope": "read,write",
        "task": "Fix the login bug",
        "allowed_paths": ["/api/sites/*", "/api/git/**"],
        "max_operations": 100
    }

    Returns: JSON with token if session is valid, error if not
    """
    try:
        from flask import session

        is_allowed, error_response = _require_delegation_admin_session()
        if not is_allowed:
            return error_response

        # Check for active wallet session
        passkey_verified = session.get('passkey_verified', False)
        auth_method = session.get('auth_method')
        user_email = session.get('user_email')
        ppid = getattr(g, 'delegation_ppid', None) or session.get('ppid') or _extract_ppid_from_lemma_header()

        # Debug: log what we found
        logger.info(f"Auto-issue check: passkey_verified={passkey_verified}, auth_method={auth_method}, has_ppid={bool(ppid)}")

        # Strict policy: require lemma PPID identity (no customer/wallet fallback identifiers)
        if not ppid or not str(ppid).startswith('did:lemma:ppid_'):
            return jsonify({
                'success': False,
                'error': 'ppid_required',
                'message': 'Please unlock wallet and provide a valid lemma PPID to issue delegated credentials.'
            }), 403

        authorized_by = str(ppid)

        # Parse parameters from GET query string or POST body
        if request.method == 'POST':
            data = request.get_json() or {}
            ttl_value = data.get('ttl_hours', data.get('ttl', 4))
            ttl_hours = min(int(ttl_value), 24)
            ttl_hours = max(ttl_hours, 1)
            scope_param = data.get('scope', ['read', 'write'])
            agent_name = data.get('agent_name', data.get('name', 'Auto-issued Agent Token'))
            task_description = data.get('task')
            allowed_paths = data.get('allowed_paths')
            max_operations = data.get('max_operations')
            allowed_sites = data.get('allowed_sites')
            delegation_reason = str(data.get('delegation_reason') or data.get('reason') or '').strip() or None
            delegation_id = str(data.get('delegation_id') or '').strip() or None
            acting_for_ppid = _normalize_ppid_claim(data.get('acting_for_ppid') or data.get('acting_for')) or authorized_by
            requested_by_ppid = _normalize_ppid_claim(data.get('requested_by_ppid') or data.get('requested_by')) or authorized_by
            delegated_by_user_ref = str(
                data.get('delegated_by_user_ref') or data.get('delegated_by_user_id') or data.get('customer_user_id') or user_email or ''
            ).strip() or None
            acting_for_user_ref = str(
                data.get('acting_for_user_ref') or data.get('acting_for_user_id') or ''
            ).strip() or None
            requested_by_user_ref = str(
                data.get('requested_by_user_ref') or data.get('requested_by_user_id') or ''
            ).strip() or None
            intended_platform = (
                data.get('intended_platform')
                or request.args.get('intended_platform')
                or request.headers.get('Origin')
                or request.host
                or 'lemma.id'
            )
        else:
            ttl_hours = min(int(request.args.get('ttl', 4)), 24)
            scope_param = request.args.get('scope', 'read,write')
            agent_name = request.args.get('name', 'Auto-issued Agent Token')
            task_description = request.args.get('task')
            # Parse allowed_paths from comma-separated query param
            paths_param = request.args.get('paths')
            allowed_paths = paths_param.split(',') if paths_param else None
            max_ops_param = request.args.get('max_ops')
            max_operations = int(max_ops_param) if max_ops_param else None
            delegation_reason = str(request.args.get('delegation_reason') or request.args.get('reason') or '').strip() or None
            delegation_id = str(request.args.get('delegation_id') or '').strip() or None
            acting_for_ppid = _normalize_ppid_claim(request.args.get('acting_for_ppid') or request.args.get('acting_for')) or authorized_by
            requested_by_ppid = _normalize_ppid_claim(request.args.get('requested_by_ppid') or request.args.get('requested_by')) or authorized_by
            delegated_by_user_ref = str(
                request.args.get('delegated_by_user_ref') or request.args.get('delegated_by_user_id') or request.args.get('customer_user_id') or user_email or ''
            ).strip() or None
            acting_for_user_ref = str(
                request.args.get('acting_for_user_ref') or request.args.get('acting_for_user_id') or ''
            ).strip() or None
            requested_by_user_ref = str(
                request.args.get('requested_by_user_ref') or request.args.get('requested_by_user_id') or ''
            ).strip() or None
            allowed_sites = request.args.get('allowed_sites')
            if allowed_sites:
                allowed_sites = [s.strip() for s in str(allowed_sites).split(',') if s.strip()]
            intended_platform = (
                request.args.get('intended_platform')
                or request.headers.get('Origin')
                or request.host
                or 'lemma.id'
            )

        if allowed_sites is None:
            allowed_sites = [_normalize_site_identifier(intended_platform) or 'lemma.id']
        if not isinstance(allowed_sites, list):
            return jsonify({
                'success': False,
                'error': 'allowed_sites must be a list of site identifiers'
            }), 400
        normalized_allowed_sites = []
        for site in allowed_sites:
            site_norm = _normalize_site_identifier(site)
            if not site_norm:
                return jsonify({
                    'success': False,
                    'error': f'Invalid site identifier: {site}'
                }), 400
            normalized_allowed_sites.append(site_norm)
        allowed_sites = sorted(list(set(normalized_allowed_sites)))

        ownership_ok, invalid_sites, owned_sites = _validate_allowed_sites_against_ownership(
            allowed_sites=allowed_sites,
            authorized_by_ppid=authorized_by,
            authorized_by_email=user_email,
        )
        if not ownership_ok:
            return jsonify({
                'success': False,
                'error': 'site_ownership_mismatch',
                'message': 'Delegated agent tokens can only be issued for sites you own/administer.',
                'requested_sites': allowed_sites,
                'invalid_sites': invalid_sites,
                'owned_sites': sorted(list(owned_sites)),
            }), 403

        # Parse scope
        if isinstance(scope_param, list):
            scope = [s for s in scope_param if s in ['read', 'write', 'admin', 'test']]
        else:
            scope = [s.strip() for s in scope_param.split(',') if s.strip() in ['read', 'write', 'admin', 'test']]
        if not scope:
            scope = ['read', 'write']
        allowed_paths, max_operations = _apply_default_admin_bounds(scope, allowed_paths, max_operations)

        # Hash task if provided
        task_hash_value = hash_task(task_description)

        # Generate token
        token_id, plaintext_token, token_hash = generate_agent_token()
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        try:
            _store_agent_credential_record(
                token_id=token_id,
                token_hash=token_hash,
                authorized_by=authorized_by,
                user_email=user_email,
                scope=scope,
                allowed_sites=allowed_sites,
                expires_at=expires_at,
                agent_name=agent_name,
                description=_encode_credential_description(
                    f'Auto-issued via active session (auth_method: {auth_method})',
                    delegation_reason=delegation_reason,
                    delegation_id=delegation_id,
                    acting_for_ppid=acting_for_ppid,
                    requested_by_ppid=requested_by_ppid,
                    delegated_by_user_ref=delegated_by_user_ref,
                    acting_for_user_ref=acting_for_user_ref,
                    requested_by_user_ref=requested_by_user_ref,
                ),
                task_description=task_description,
                task_hash_value=task_hash_value,
                allowed_paths=allowed_paths,
                max_operations=max_operations,
                delegation_id=delegation_id,
                delegation_reason=delegation_reason,
                acting_for_ppid=acting_for_ppid,
                requested_by_ppid=requested_by_ppid,
                delegated_by_user_ref=delegated_by_user_ref,
                acting_for_user_ref=acting_for_user_ref,
                requested_by_user_ref=requested_by_user_ref,
                audience=allowed_sites[0] if allowed_sites else None,
                subject_ref=token_id,
            )
        except Exception as db_err:
            logger.error(f"Failed to store auto-issued credential: {db_err}")
            return jsonify({
                'success': False,
                'error': 'Database error',
                'message': str(db_err)
            }), 500

        logger.info(f"Auto-issued agent credential: {token_id} for {authorized_by} (task: {task_description[:50] if task_description else 'none'})")

        response_data = {
            'success': True,
            'token': plaintext_token,
            'token_id': token_id,
            'scope': scope,
            'allowed_sites': allowed_sites,
            'expires_at': expires_at.isoformat() + 'Z',
            'ttl_hours': ttl_hours,
            'authorized_by': authorized_by,
            'delegation': {
                'delegation_id': delegation_id,
                'delegation_reason': delegation_reason,
                'delegated_by_ppid': authorized_by,
                'acting_for_ppid': acting_for_ppid,
                'requested_by_ppid': requested_by_ppid,
                'delegated_by_user_ref': delegated_by_user_ref,
                'acting_for_user_ref': acting_for_user_ref,
                'requested_by_user_ref': requested_by_user_ref,
            },
            'message': 'Token issued from active wallet session'
        }

        # Add task-bound info if present
        if task_description:
            response_data['task'] = task_description
            response_data['task_hash'] = task_hash_value
        if allowed_paths:
            response_data['allowed_paths'] = allowed_paths
        if max_operations:
            response_data['max_operations'] = max_operations

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Auto-issue failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@agent_credentials_bp.route('/api/agent/cli-login/complete', methods=['GET'])
def cli_login_complete():
    """
    Browser completion endpoint for CLI login.
    Opens in browser, issues token from active lemma.id session, stores one-time
    result keyed by state, and renders a human confirmation page.
    """
    state = (request.args.get('state') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,200}', state):
        return jsonify({'success': False, 'error': 'invalid_state'}), 400

    ttl_hours_raw = request.args.get('ttl_hours', '8')
    try:
        ttl_hours = int(ttl_hours_raw)
    except (TypeError, ValueError):
        ttl_hours = 8
    scope_param = request.args.get('scope', 'read,write,admin')
    agent_name = request.args.get('agent_name', 'lemma-cli')
    task_description = request.args.get('task', 'CLI authenticated provisioning session')
    delegation_reason = str(request.args.get('delegation_reason') or request.args.get('reason') or '').strip() or None
    delegation_id = str(request.args.get('delegation_id') or '').strip() or None
    acting_for_ppid = _normalize_ppid_claim(request.args.get('acting_for_ppid') or request.args.get('acting_for'))
    requested_by_ppid = _normalize_ppid_claim(request.args.get('requested_by_ppid') or request.args.get('requested_by'))
    delegated_by_user_ref = str(
        request.args.get('delegated_by_user_ref') or request.args.get('delegated_by_user_id') or request.args.get('customer_user_id') or ''
    ).strip() or None
    acting_for_user_ref = str(
        request.args.get('acting_for_user_ref') or request.args.get('acting_for_user_id') or ''
    ).strip() or None
    requested_by_user_ref = str(
        request.args.get('requested_by_user_ref') or request.args.get('requested_by_user_id') or ''
    ).strip() or None
    allowed_sites_param = request.args.get('allowed_sites', '')
    allowed_sites = [s.strip() for s in str(allowed_sites_param).split(',') if s.strip()] or None
    intended_platform = (
        request.args.get('intended_platform')
        or request.headers.get('Origin')
        or request.host
        or 'lemma.id'
    )

    issue_response, issue_status = _issue_agent_token_from_inputs(
        ttl_hours=ttl_hours,
        scope_param=scope_param,
        agent_name=agent_name,
        task_description=task_description,
        allowed_paths=None,
        max_operations=None,
        allowed_sites=allowed_sites,
        intended_platform=intended_platform,
        delegation_reason=delegation_reason,
        delegation_id=delegation_id,
        acting_for_ppid=acting_for_ppid,
        requested_by_ppid=requested_by_ppid,
        delegated_by_user_ref=delegated_by_user_ref,
        acting_for_user_ref=acting_for_user_ref,
        requested_by_user_ref=requested_by_user_ref,
    )
    issue_payload = issue_response.get_json(silent=True) or {}

    if issue_status == 200 and issue_payload.get('success'):
        stored = _store_cli_login_result(state, {
            'success': True,
            'status_code': issue_status,
            'token': issue_payload.get('token'),
            'token_id': issue_payload.get('token_id'),
            'scope': issue_payload.get('scope'),
            'allowed_sites': issue_payload.get('allowed_sites'),
            'authorized_by': issue_payload.get('authorized_by'),
            'delegation': issue_payload.get('delegation'),
            'expires_at': issue_payload.get('expires_at'),
        })
        if not stored:
            return jsonify({'success': False, 'error': 'result_store_failed'}), 500

        body = """
        <html><head><title>Lemma CLI Login Complete</title></head>
        <body style="font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto;">
          <h2>Lemma CLI login approved</h2>
          <p>You can return to your terminal now. The CLI will complete automatically.</p>
          <p><strong>Token ID:</strong> {token_id}</p>
          <p><strong>Scope:</strong> {scope}</p>
        </body></html>
        """.format(
            token_id=html.escape(str(issue_payload.get('token_id') or '')),
            scope=html.escape(",".join(issue_payload.get('scope') or [])),
        )
        return body, 200, {'Content-Type': 'text/html; charset=utf-8'}

    store_payload = {
        'success': False,
        'status_code': issue_status,
        'error': issue_payload.get('error', 'login_failed'),
        'message': issue_payload.get('message', 'Could not complete CLI login from current browser session.'),
    }
    _store_cli_login_result(state, store_payload)
    error_message = html.escape(str(store_payload.get('message') or store_payload.get('error')))
    login_href = "/login"
    unlock_href = "/wallet/unlock"
    body = f"""
    <html><head><title>Lemma CLI Login Action Required</title></head>
    <body style="font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto;">
      <h2>Lemma CLI login not completed yet</h2>
      <p>{error_message}</p>
      <p>Complete lemma.id login/unlock in this browser, then reopen this URL.</p>
      <p><a href="{login_href}">Open Login</a> | <a href="{unlock_href}">Open Wallet Unlock</a></p>
    </body></html>
    """
    return body, 403, {'Content-Type': 'text/html; charset=utf-8'}


@agent_credentials_bp.route('/api/agent/cli-login/poll', methods=['GET'])
def cli_login_poll():
    """CLI poll endpoint for browser login completion."""
    state = (request.args.get('state') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,200}', state):
        return jsonify({'success': False, 'error': 'invalid_state'}), 400

    result = _consume_cli_login_result(state)
    if not result:
        return jsonify({'success': True, 'completed': False}), 200
    return jsonify({'success': True, 'completed': True, **result}), 200


@agent_credentials_bp.route('/api/agent/session', methods=['GET', 'POST'])
@restricted_cross_origin(supports_credentials=True)
@require_agent_or_user_session()
def create_agent_session():
    """
    Create a browser session from an agent token.
    
    This enables AI agents with browser tools to navigate the platform
    as an authenticated user. The agent token is converted into a
    session cookie that works with normal page navigation.
    
    GET/POST /api/agent/session
    Headers:
        X-Agent-Token: lm_agent_xxx
    OR Query Parameter:
        ?token=lm_agent_xxx
    
    Returns:
        - Sets session cookie
        - Returns session info for the browser
        - Optionally redirects to a target page
    """
    # Accept token from header or query parameter
    token = request.headers.get('X-Agent-Token') or request.args.get('token')
    
    if not token:
        return jsonify({
            'success': False,
            'error': 'auth_required',
            'message': 'X-Agent-Token header required'
        }), 400
    
    credential_info = validate_agent_token(token)
    
    if not credential_info:
        return jsonify({
            'success': False,
            'error': 'invalid_token',
            'message': 'Invalid, expired, or revoked agent token'
        }), 401

    site_ok, blocked_site, allowed_sites_norm, _requested_sites = check_site_allowed(credential_info)
    if not site_ok:
        return jsonify({
            'success': False,
            'error': 'site_not_allowed',
            'site': blocked_site,
            'allowed_sites': sorted(list(allowed_sites_norm)) if allowed_sites_norm is not None else None,
            'message': 'This agent credential is restricted to specific sites and cannot create a session here.'
        }), 403
    
    # Create session from agent token
    session['agent_authenticated'] = True
    session['agent_token_id'] = credential_info['token_id']
    session['agent_ppid'] = credential_info['authorized_by_ppid']
    session['agent_scope'] = credential_info['scope']
    session['agent_allowed_sites'] = credential_info.get('allowed_sites')
    session['customer_id'] = credential_info.get('authorized_by_ppid', '').replace('did:lemma:', '')
    session['auth_method'] = 'agent_token'
    
    # Set admin flag if scope includes admin
    if 'admin' in credential_info['scope']:
        session['is_admin'] = True
    
    logger.info(f"Agent session created: {credential_info['token_id']} -> browser session")
    
    # Check for redirect parameter
    redirect_to = request.args.get('redirect')
    if redirect_to:
        # Validate redirect is to our domain
        from urllib.parse import urlparse
        parsed = urlparse(redirect_to)
        if parsed.netloc in ['', 'lemma.id', 'www.lemma.id'] or redirect_to.startswith('/'):
            from flask import redirect
            return redirect(redirect_to)
    
    response = jsonify({
        'success': True,
        'session_created': True,
        'token_id': credential_info['token_id'],
        'scope': credential_info['scope'],
        'allowed_sites': credential_info.get('allowed_sites'),
        'ppid': credential_info['authorized_by_ppid'],
        'is_admin': 'admin' in credential_info['scope'],
        'message': 'Browser session created. You can now navigate authenticated pages.',
        'next_steps': [
            'Navigate to /admin for admin dashboard',
            'Navigate to /developer for developer dashboard',
            'Or use ?redirect=/admin to auto-redirect'
        ]
    })
    
    return response


@agent_credentials_bp.route('/api/agent/validate', methods=['GET', 'POST'])
@restricted_cross_origin()
def validate_agent_token_endpoint():
    """
    Quick endpoint to test if an agent token or session is valid.
    Checks both X-Agent-Token header and Flask session (from /api/agent/session).

    Returns 200 for valid tokens/sessions and 401 for missing/invalid auth.
    Includes task-bound info if the credential has task restrictions.
    """
    # First check for token in header
    token = request.headers.get('X-Agent-Token')

    if token:
        credential_info, token_error = validate_agent_token_with_reason(token)

        if credential_info:
            response = {
                'valid': True,
                'auth_method': 'token',
                'token_id': credential_info['token_id'],
                'scope': credential_info['scope'],
                'expires_at': credential_info['expires_at'].isoformat() + 'Z' if credential_info['expires_at'] else None,
                'agent_name': credential_info['agent_name'],
                'authorized_by': credential_info['authorized_by_email'] or credential_info['authorized_by_ppid'],
                'delegation': {
                    'delegation_id': credential_info.get('delegation_id'),
                    'delegation_reason': credential_info.get('delegation_reason'),
                    'delegated_by_ppid': credential_info.get('authorized_by_ppid'),
                    'acting_for_ppid': credential_info.get('acting_for_ppid'),
                    'requested_by_ppid': credential_info.get('requested_by_ppid'),
                    'delegated_by_user_ref': credential_info.get('delegated_by_user_ref'),
                    'acting_for_user_ref': credential_info.get('acting_for_user_ref'),
                    'requested_by_user_ref': credential_info.get('requested_by_user_ref'),
                },
                # Task-bound info
                'is_task_bound': credential_info.get('task_description') is not None or credential_info.get('allowed_paths') is not None,
                'task': credential_info.get('task_description'),
                'task_hash': credential_info.get('task_hash'),
                'allowed_paths': credential_info.get('allowed_paths'),
                'max_operations': credential_info.get('max_operations'),
                'operations_used': credential_info.get('use_count', 0),
                'operations_remaining': (
                    credential_info['max_operations'] - credential_info.get('use_count', 0)
                    if credential_info.get('max_operations') else None
                ),
                'task_deviation_count': credential_info.get('task_deviation_count', 0)
            }
            if credential_info.get('audience'):
                response['audience'] = credential_info.get('audience')
            return jsonify(response)
        else:
            return jsonify({
                'valid': False,
                'error': token_error or 'invalid_token',
                'message': 'Token failed validation'
            }), 401

    # Check for session-based agent auth (from /api/agent/session)
    if session.get('agent_authenticated'):
        return jsonify({
            'valid': True,
            'auth_method': 'session',
            'token_id': session.get('agent_token_id'),
            'scope': session.get('agent_scope', []),
            'allowed_sites': session.get('agent_allowed_sites'),
            'ppid': session.get('agent_ppid'),
            'message': 'Authenticated via agent session cookie'
        })

    # No auth found - return a machine-branchable auth error.
    return jsonify({
        'valid': False,
        'error': 'auth_required',
        'message': 'No agent token or session found'
    }), 401
