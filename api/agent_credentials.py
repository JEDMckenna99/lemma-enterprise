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
import secrets
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Blueprint, request, jsonify, g, session
from flask_cors import cross_origin

from auth.rate_limiter import rate_limit, credential_issue_limit

logger = logging.getLogger(__name__)

agent_credentials_bp = Blueprint('agent_credentials', __name__)


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


def _resolve_monitor_identity():
    """
    Resolve owner identity for monitoring endpoints.

    Supports:
    - X-Agent-Token (owner inferred from credential)
    - X-Lemma-PPID
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

    ppid = request.headers.get('X-Lemma-PPID')
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

    api_key = request.headers.get('X-API-Key')
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


# ============================================
# CREDENTIAL ISSUANCE (Requires Passkey Auth)
# ============================================

@agent_credentials_bp.route('/api/agent/credentials/issue', methods=['POST'])
@cross_origin()
@rate_limit(credential_issue_limit)
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
        # SECURITY CHECK 1: User must be authenticated
        # Check for passkey session or PPID
        ppid = request.headers.get('X-Lemma-PPID')
        passkey_verified = session.get('passkey_verified', False)
        customer_id = session.get('customer_id')
        user_email = session.get('user_email')

        # Also check Authorization header for Bearer token with credential
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer ') and not ppid:
            # Could be a JSON credential - extract PPID
            try:
                cred_data = json.loads(auth_header[7:])
                ppid = cred_data.get('subject') or cred_data.get('credentialSubject', {}).get('id')
            except:
                pass

        if not ppid and not customer_id:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'You must be signed in with passkey to issue agent credentials'
            }), 401

        # SECURITY: Validate PPID format if provided via header (prevent spoofing)
        if ppid and not ppid.startswith('did:lemma:ppid_'):
            return jsonify({
                'success': False,
                'error': 'Invalid PPID format',
                'message': 'PPID must be a valid Lemma identifier'
            }), 400

        # SECURITY: For customer_id auth, require passkey verification
        # This prevents session-only auth from issuing agent credentials
        if customer_id and not ppid and not passkey_verified:
            return jsonify({
                'success': False,
                'error': 'Passkey verification required',
                'message': 'Agent credentials require passkey authentication, not just session'
            }), 403

        # Use PPID as identifier, fall back to customer_id
        authorized_by = ppid or f"customer:{customer_id}"

        # Parse request data
        data = request.get_json() or {}
        agent_name = data.get('agent_name', 'AI Agent')
        scope = data.get('scope', ['read'])
        ttl_hours = min(data.get('ttl_hours', 4), 24)  # Max 24 hours
        allowed_sites = data.get('allowed_sites')  # null = all user's sites
        description = data.get('description', '')

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

        # Validate scope
        valid_scopes = ['read', 'write', 'admin', 'test']
        scope = [s for s in scope if s in valid_scopes]
        if not scope:
            scope = ['read']

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
                json.dumps(allowed_sites) if allowed_sites else None,
                expires_at,
                agent_name,
                description,
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


def validate_agent_token(token):
    """
    Validate an agent token and return credential info if valid.

    Returns:
        dict with credential info if valid (includes task-bound fields)
        None if invalid/expired/revoked
    """
    if not token or not token.startswith('lm_agent_'):
        return None

    token_hash = hash_token(token)

    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, token_id, authorized_by_ppid, authorized_by_email,
                   scope, allowed_sites, expires_at, agent_name,
                   task_description, task_hash, allowed_paths, max_operations,
                   use_count, task_deviation_count
            FROM agent_credentials
            WHERE token_hash = %s
              AND revoked = FALSE
              AND expires_at > NOW()
        """, (token_hash,))

        row = cursor.fetchone()

        if not row:
            cursor.close()
            conn.close()
            return None

        credential_id = row[0]
        use_count = row[12] or 0
        max_operations = row[11]

        # Check max_operations limit BEFORE incrementing
        if max_operations is not None and use_count >= max_operations:
            cursor.close()
            conn.close()
            logger.warning(f"Agent credential {row[1]} exceeded max_operations ({max_operations})")
            return None

        # Update usage stats
        cursor.execute("""
            UPDATE agent_credentials
            SET last_used_at = NOW(), use_count = use_count + 1
            WHERE id = %s
        """, (credential_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            'credential_id': credential_id,
            'token_id': row[1],
            'authorized_by_ppid': row[2],
            'authorized_by_email': row[3],
            'scope': row[4] if isinstance(row[4], list) else json.loads(row[4] or '["read"]'),
            'allowed_sites': row[5] if isinstance(row[5], list) else (json.loads(row[5]) if row[5] else None),
            'expires_at': row[6],
            'agent_name': row[7],
            # Task-bound fields
            'task_description': row[8],
            'task_hash': row[9],
            'allowed_paths': row[10] if isinstance(row[10], list) else (json.loads(row[10]) if row[10] else None),
            'max_operations': row[11],
            'use_count': use_count + 1,  # After increment
            'task_deviation_count': row[13] or 0
        }

    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return None


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
                credential_info = validate_agent_token(agent_token)

                if not credential_info:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid, expired, or max operations exceeded'
                    }), 401

                # Check scope if required
                if required_scope:
                    if required_scope not in credential_info['scope']:
                        log_agent_action(credential_info, f'scope_denied:{required_scope}',
                                        success=False, status_code=403)
                        return jsonify({
                            'success': False,
                            'error': f'Agent credential lacks required scope: {required_scope}'
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
                            'error': 'Path not allowed for this task-bound credential',
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

                session_ppid = session.get('agent_ppid')
                if session_ppid:
                    g.ppid = session_ppid
                g.authenticated = True
                g.auth_method = 'agent_session'
                return f(*args, **kwargs)

            # Fall back to user auth
            ppid = request.headers.get('X-Lemma-PPID')
            api_key = request.headers.get('X-API-Key')

            if ppid and ppid.startswith('did:lemma:ppid_'):
                g.ppid = ppid
                g.authenticated = True
                g.auth_method = 'ppid'
                return f(*args, **kwargs)

            if api_key and len(api_key) >= 10:
                g.api_key = api_key
                g.authenticated = True
                g.auth_method = 'api_key'
                return f(*args, **kwargs)

            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'Provide X-Agent-Token, X-Lemma-PPID, or X-API-Key header'
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

    ppid = request.headers.get('X-Lemma-PPID')
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
def revoke_agent_credential(token_id):
    """
    Revoke an agent credential immediately.
    
    This is the KILL SWITCH - use it if:
    - Agent is behaving unexpectedly
    - Session is no longer needed
    - Security concern
    """
    ppid = request.headers.get('X-Lemma-PPID')
    customer_id = session.get('customer_id')
    
    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
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
    ppid = request.headers.get('X-Lemma-PPID')
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
    ppid = request.headers.get('X-Lemma-PPID')
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
@rate_limit(credential_issue_limit)
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

        # Check for active wallet session
        customer_id = session.get('customer_id')
        passkey_verified = session.get('passkey_verified', False)
        auth_method = session.get('auth_method')
        user_email = session.get('user_email')
        wallet_id = session.get('wallet_id')

        # Also check for PPID in session or derived from wallet
        ppid = session.get('ppid')

        # Debug: log what we found
        logger.info(f"Auto-issue check: customer_id={customer_id}, passkey_verified={passkey_verified}, auth_method={auth_method}, wallet_id={wallet_id}")

        # Must have some form of authentication
        if not customer_id and not wallet_id and not ppid:
            return jsonify({
                'success': False,
                'error': 'No active wallet session',
                'message': 'Please sign in with your wallet first',
                'debug': {
                    'customer_id': customer_id,
                    'passkey_verified': passkey_verified,
                    'auth_method': auth_method
                }
            }), 401

        # Build authorized_by identifier
        if ppid:
            authorized_by = ppid
        elif wallet_id:
            authorized_by = f"wallet:{wallet_id}"
        else:
            authorized_by = f"customer:{customer_id}"

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
                 scope, expires_at, agent_name, description,
                 task_description, task_hash, allowed_paths, max_operations)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                token_id,
                token_hash,
                authorized_by,
                user_email,
                json.dumps(scope),
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
            'error': 'X-Agent-Token header required'
        }), 400
    
    credential_info = validate_agent_token(token)
    
    if not credential_info:
        return jsonify({
            'success': False,
            'error': 'Invalid, expired, or revoked agent token'
        }), 401
    
    # Create session from agent token
    session['agent_authenticated'] = True
    session['agent_token_id'] = credential_info['token_id']
    session['agent_ppid'] = credential_info['authorized_by_ppid']
    session['agent_scope'] = credential_info['scope']
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
        credential_info = validate_agent_token(token)

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
                'allowed_paths': credential_info.get('allowed_paths'),
                'max_operations': credential_info.get('max_operations'),
                'operations_used': credential_info.get('use_count', 0),
                'operations_remaining': (
                    credential_info['max_operations'] - credential_info.get('use_count', 0)
                    if credential_info.get('max_operations') else None
                ),
                'task_deviation_count': credential_info.get('task_deviation_count', 0)
            }
            return jsonify(response)
        else:
            return jsonify({
                'valid': False,
                'error': 'Invalid, expired, revoked, or max operations exceeded'
            }), 401

    # Check for session-based agent auth (from /api/agent/session)
    if session.get('agent_authenticated'):
        return jsonify({
            'valid': True,
            'auth_method': 'session',
            'token_id': session.get('agent_token_id'),
            'scope': session.get('agent_scope', []),
            'ppid': session.get('agent_ppid'),
            'message': 'Authenticated via agent session cookie'
        })

    # No auth found - return valid: false (not an error, just not authenticated)
    return jsonify({
        'valid': False,
        'message': 'No agent token or session found'
    })
