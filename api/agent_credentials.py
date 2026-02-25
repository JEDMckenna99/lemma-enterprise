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
import logging
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, g, session
from flask_cors import cross_origin

from auth.rate_limiter import rate_limit, credential_issue_limit, get_issuance_identifier

logger = logging.getLogger(__name__)

agent_credentials_bp = Blueprint('agent_credentials', __name__)

DEFAULT_DELEGATION_ALLOWED_PERMISSIONS = 'admin_access,super_admin_access'
DEFAULT_DELEGATION_ALLOWED_ROLES = 'admin,super_admin'


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


def _encode_credential_description(description: str, audience: str | None = None) -> str:
    """
    Keep backward compatibility with plain-text description while allowing
    structured metadata needed by OpenClaw profile checks.
    """
    description_text = (description or '').strip()
    if not audience:
        return description_text
    return json.dumps({
        'description': description_text,
        'audience': str(audience).strip().lower()
    })


def _decode_credential_description(raw_description: str | None) -> dict:
    """Parse description metadata when stored as JSON; fallback to plain text."""
    if not raw_description:
        return {'description': '', 'audience': None}

    if isinstance(raw_description, dict):
        return {
            'description': str(raw_description.get('description') or '').strip(),
            'audience': str(raw_description.get('audience') or '').strip().lower() or None
        }

    if not isinstance(raw_description, str):
        return {'description': str(raw_description), 'audience': None}

    try:
        decoded = json.loads(raw_description)
        if isinstance(decoded, dict):
            return {
                'description': str(decoded.get('description') or '').strip(),
                'audience': str(decoded.get('audience') or '').strip().lower() or None
            }
    except Exception:
        pass

    return {'description': raw_description, 'audience': None}


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

    Strict policy: issuance is human-gated by wallet unlock state and PPID identity.
    Machine-token-only issuance is intentionally disallowed.
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

    lemma_site_id = admin_lemma_ctx.get('site_id')
    if lemma_site_id and lemma_site_id != intended_platform:
        return False, (
            jsonify({
                'success': False,
                'error': 'admin_lemma_site_mismatch',
                'message': f'Admin lemma is for {lemma_site_id}, but requested delegation is for {intended_platform}.'
            }),
            403
        )

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
    requested_sites = infer_requested_site_ids()

    if allowed_sites is None:
        return True, None, None, requested_sites

    allowed_sites_norm = {
        s for s in (_normalize_site_identifier(item) for item in allowed_sites) if s
    }
    if not allowed_sites_norm:
        return False, None, set(), requested_sites

    blocked_sites = [s for s in requested_sites if s not in allowed_sites_norm]
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


def _extract_ppid_from_lemma_header():
    """
    Extract verified PPID from full credential header.
    Header format: X-Lemma-Credential = base64url(JSON credential) or raw JSON.
    """
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

    if not isinstance(credential, dict):
        return None

    try:
        from api.trusted_issuers import verify_credential_with_trust
        verification = verify_credential_with_trust(credential)
        if not verification.get('valid'):
            return None
    except Exception:
        return None

    claims = credential.get('claims') or credential.get('credentialSubject') or {}
    ppid = (
        credential.get('subject')
        or credential.get('sub')
        or claims.get('ppid')
        or claims.get('id')
        or claims.get('subject')
    )
    if ppid and str(ppid).startswith('did:lemma:ppid_'):
        return str(ppid)
    return None


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


def require_agent_or_user_session(required_scope=None):
    """
    Lightweight explicit auth decorator for credential management endpoints.
    Accepts agent token, PPID header, API key, or active agent browser session.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            agent_token = request.headers.get('X-Agent-Token')
            if agent_token:
                credential_info = validate_agent_token(agent_token)
                if not credential_info:
                    return jsonify({'success': False, 'error': 'invalid_token'}), 401

                scope = credential_info.get('scope') or []
                if isinstance(scope, str):
                    scope = [scope]
                if required_scope and required_scope not in scope:
                    return jsonify({
                        'success': False,
                        'error': 'missing_scope',
                        'required_scope': [required_scope],
                        'provided_scope': scope,
                    }), 403

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

            ppid = _extract_ppid_from_lemma_header()
            if ppid and ppid.startswith('did:lemma:ppid_'):
                g.ppid = ppid
                g.authenticated = True
                g.auth_method = 'ppid'
                return f(*args, **kwargs)

            if session.get('agent_authenticated'):
                session_scope = session.get('agent_scope', [])
                if required_scope and required_scope not in session_scope:
                    return jsonify({
                        'success': False,
                        'error': 'missing_scope',
                        'required_scope': [required_scope],
                        'provided_scope': session_scope,
                    }), 403
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
@cross_origin()
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
                'message': 'Delegation issuance requires a valid lemma PPID and unlocked wallet session.'
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

        allowed_sites = data.get('allowed_sites')
        if allowed_sites is None:
            # Security default: site-bind credentials to the site where they are issued.
            allowed_sites = [intended_platform]
        description = data.get('description', '')
        audience = (data.get('audience') or data.get('aud') or '').strip().lower() or None

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

        encoded_description = _encode_credential_description(description, audience)

        # Generate token
        token_id, plaintext_token, token_hash = generate_agent_token()

        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        # Store in database
        try:
            from api.database import get_db_connection

            conn = get_db_connection()
            cursor = conn.cursor()

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
                encoded_description,
                task_description,
                task_hash_value,
                json.dumps(allowed_paths) if allowed_paths else None,
                max_operations
            ))

            credential_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()

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
                'agent_name': agent_name
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
            return None, 'invalid_token'

        is_revoked = bool(row[14])
        expires_at = row[6]
        if is_revoked:
            cursor.close()
            conn.close()
            return None, 'token_revoked'
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            cursor.close()
            conn.close()
            return None, 'token_expired'

        credential_id = row[0]
        use_count = row[12] or 0
        max_operations = row[11]
        if max_operations is not None and use_count >= max_operations:
            cursor.close()
            conn.close()
            logger.warning(f"Agent credential {row[1]} exceeded max_operations ({max_operations})")
            return None, 'max_operations_exceeded'

        cursor.execute("""
            UPDATE agent_credentials
            SET last_used_at = NOW(), use_count = use_count + 1
            WHERE id = %s
        """, (credential_id,))

        conn.commit()
        cursor.close()
        conn.close()

        allowed_sites = row[5] if isinstance(row[5], list) else (json.loads(row[5]) if row[5] else None)
        description_meta = _decode_credential_description(row[15])
        inferred_audience = description_meta.get('audience')
        if not inferred_audience and isinstance(allowed_sites, list) and len(allowed_sites) == 1:
            inferred_audience = str(allowed_sites[0]).strip().lower()

        return {
            'credential_id': credential_id,
            'token_id': row[1],
            'authorized_by_ppid': row[2],
            'authorized_by_email': row[3],
            'scope': row[4] if isinstance(row[4], list) else json.loads(row[4] or '["read"]'),
            'allowed_sites': allowed_sites,
            'expires_at': expires_at,
            'agent_name': row[7],
            'task_description': row[8],
            'task_hash': row[9],
            'allowed_paths': row[10] if isinstance(row[10], list) else (json.loads(row[10]) if row[10] else None),
            'max_operations': max_operations,
            'use_count': use_count + 1,
            'task_deviation_count': row[13] or 0,
            'audience': inferred_audience
        }, None

    except Exception as e:
        logger.error(f"Token validation error: {e}")
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
                     path_allowed=True, task_deviation=False, deviation_reason=None):
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
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert audit log entry with deviation tracking
        cursor.execute("""
            INSERT INTO agent_audit_log
            (credential_id, token_id, action, resource, method, path, status_code, success,
             path_allowed, task_deviation, deviation_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            credential_info.get('credential_id'),
            credential_info.get('token_id'),
            action,
            resource,
            request.method,
            request.path,
            status_code,
            success,
            path_allowed,
            task_deviation,
            deviation_reason
        ))

        # If this is a task deviation, increment the deviation count on the credential
        if task_deviation and credential_info.get('credential_id'):
            cursor.execute("""
                UPDATE agent_credentials
                SET task_deviation_count = COALESCE(task_deviation_count, 0) + 1
                WHERE id = %s
            """, (credential_info.get('credential_id'),))

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
    2. User auth (X-Lemma-PPID header or session)

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
            # Try agent token first
            agent_token = request.headers.get('X-Agent-Token')

            if agent_token:
                credential_info, token_error = validate_agent_token_with_reason(agent_token)

                if not credential_info:
                    return jsonify({
                        'success': False,
                        'error': token_error or 'invalid_token'
                    }), 401

                # Check scope if required
                if required_scope:
                    if required_scope not in credential_info['scope']:
                        log_agent_action(credential_info, f'scope_denied:{required_scope}',
                                        success=False, status_code=403)
                        return jsonify({
                            'success': False,
                            'error': 'missing_scope',
                            'required_scope': [required_scope],
                            'provided_scope': credential_info.get('scope', [])
                        }), 403

                # Enforce optional site-level restrictions
                site_ok, blocked_site, allowed_sites_norm, requested_sites = check_site_allowed(credential_info)
                if not site_ok:
                    log_agent_action(
                        credential_info,
                        f'site_denied:{blocked_site or "unknown"}',
                        success=False,
                        status_code=403,
                    )
                    return jsonify({
                        'success': False,
                        'error': 'site_not_allowed',
                        'site': blocked_site,
                        'allowed_sites': sorted(list(allowed_sites_norm)) if allowed_sites_norm is not None else None,
                        'message': 'This agent credential is restricted to specific sites. Request a new credential with the correct allowed_sites.'
                    }), 403

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
                        log_agent_action(credential_info, f'path_denied:{request.path}',
                                        success=False, status_code=403,
                                        path_allowed=False, task_deviation=True,
                                        deviation_reason=deviation_reason)
                        return jsonify({
                            'success': False,
                            'error': 'path_not_allowed',
                            'path': request.path,
                            'allowed_paths': allowed_paths,
                            'task': credential_info.get('task_description'),
                            'message': 'This agent credential is restricted to specific paths. Request a new credential with broader access or correct allowed_paths.'
                        }), 403

                # Set credential info in request context
                g.agent_credential = credential_info
                g.ppid = credential_info['authorized_by_ppid']  # Use authorizer's PPID
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
                log_agent_action(credential_info, f'{request.method}:{request.path}',
                                path_allowed=path_allowed, task_deviation=task_deviation,
                                deviation_reason=deviation_reason)

                return f(*args, **kwargs)

            # Support browser agent sessions created via /api/agent/session.
            if session.get('agent_authenticated'):
                session_scope = session.get('agent_scope', [])
                if required_scope and required_scope not in session_scope:
                    return jsonify({
                        'success': False,
                        'error': f'Agent session lacks required scope: {required_scope}'
                    }), 403

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
                return f(*args, **kwargs)

            # Fall back to user auth
            ppid = _extract_ppid_from_lemma_header()
            api_key = _extract_api_key_from_request()

            if ppid and ppid.startswith('did:lemma:ppid_'):
                g.ppid = ppid
                g.authenticated = True
                g.auth_method = 'ppid'
                return f(*args, **kwargs)

            is_valid_key, key_info = _validate_request_api_key(api_key)
            if is_valid_key:
                g.api_key = api_key
                g.api_key_info = key_info
                g.authenticated = True
                g.auth_method = 'api_key'
                return f(*args, **kwargs)

            return jsonify({
                'success': False,
                'error': 'auth_required',
                'message': 'Provide X-Agent-Token, X-Lemma-Credential, X-API-Key, or Authorization: Bearer <api_key> header'
            }), 401

        return decorated_function
    return decorator


# ============================================
# CREDENTIAL MANAGEMENT ENDPOINTS
# ============================================

@agent_credentials_bp.route('/api/agent/credentials', methods=['GET'])
@cross_origin()
def list_agent_credentials():
    """List all agent credentials for the authenticated user, including task-bound info."""
    # Allow direct token-based auth for automation and API clients.
    agent_token = request.headers.get('X-Agent-Token')
    credential_info = validate_agent_token(agent_token) if agent_token else None

    ppid = _extract_ppid_from_lemma_header() or session.get('ppid')
    customer_id = session.get('customer_id')

    if credential_info:
        authorized_by = credential_info.get('authorized_by_ppid') or credential_info.get('authorized_by_email')
        if not authorized_by:
            return jsonify({
                'success': False,
                'error': 'Agent token missing authorized principal'
            }), 401
    elif not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    else:
        authorized_by = ppid or f"customer:{customer_id}"

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
@cross_origin()
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
@cross_origin()
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
                       al.status_code, al.success, al.timestamp
                FROM agent_audit_log al
                JOIN agent_credentials ac ON al.credential_id = ac.id
                WHERE ac.authorized_by_ppid = %s AND al.token_id = %s
                ORDER BY al.timestamp DESC
                LIMIT %s
            """, (authorized_by, token_id, limit))
        else:
            cursor.execute("""
                SELECT al.token_id, al.action, al.resource, al.method, al.path,
                       al.status_code, al.success, al.timestamp
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
            audit_log.append({
                'token_id': row[0],
                'action': row[1],
                'resource': row[2],
                'method': row[3],
                'path': row[4],
                'status_code': row[5],
                'success': row[6],
                'timestamp': row[7].isoformat() + 'Z' if row[7] else None
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
@cross_origin()
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
@cross_origin()
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
@cross_origin()
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


@agent_credentials_bp.route('/api/agent/monitor/summary', methods=['GET'])
@cross_origin()
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

        # Parse scope
        if isinstance(scope_param, list):
            scope = [s for s in scope_param if s in ['read', 'write', 'admin', 'test']]
        else:
            scope = [s.strip() for s in scope_param.split(',') if s.strip() in ['read', 'write', 'admin', 'test']]
        if not scope:
            scope = ['read', 'write']

        # Hash task if provided
        task_hash_value = hash_task(task_description)

        # Generate token
        token_id, plaintext_token, token_hash = generate_agent_token()
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        # Store in database
        try:
            from api.database import get_db_connection

            conn = get_db_connection()
            cursor = conn.cursor()

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
                json.dumps(allowed_sites),
                expires_at,
                agent_name,
                f'Auto-issued via active session (auth_method: {auth_method})',
                task_description,
                task_hash_value,
                json.dumps(allowed_paths) if allowed_paths else None,
                max_operations
            ))

            conn.commit()
            cursor.close()
            conn.close()

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


@agent_credentials_bp.route('/api/agent/session', methods=['GET', 'POST'])
@cross_origin(supports_credentials=True)
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
@cross_origin()
def validate_agent_token_endpoint():
    """
    Quick endpoint to test if an agent token or session is valid.
    Checks both X-Agent-Token header and Flask session (from /api/agent/session).

    Returns 200 with valid: true/false (never 400 for missing token)
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

    # No auth found - return valid: false (not an error, just not authenticated)
    return jsonify({
        'valid': False,
        'error': 'auth_required',
        'message': 'No agent token or session found'
    })
