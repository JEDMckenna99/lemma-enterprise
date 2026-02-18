"""
Authentication and authorization decorators for Lemma.id platform
Session-free architecture - all auth via credentials + smart caching

AGENT DELEGATION:
When a user authorizes an AI agent via passkey, the agent receives a token.
This token can be used:
1. In X-Agent-Token header (for direct API calls)
2. Via /api/agent/session to create a browser session (Flask session)

The decorators check BOTH methods, enabling full agent delegation chain:
User Passkey → Agent Token → Browser Session → API Calls
"""

from functools import wraps
from flask import request, jsonify, g, make_response, session
from typing import Optional
import logging

from auth.permissions import normalize_scopes, is_admin_permission

logger = logging.getLogger(__name__)


def _extract_api_key_from_request() -> Optional[str]:
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
        # Ignore likely credential JSON/JWT payloads and agent tokens here.
        if token and not token.startswith('{') and not token.startswith('lm_agent_'):
            return token

    return None


def _auth_error(code: str, message: str, status: int = 401, auth_method: str = 'none', required_scope=None, provided_scope=None):
    payload = {
        'error': code,
        'message': message,
        'auth_method': auth_method,
    }
    if required_scope is not None:
        payload['required_scope'] = required_scope
    if provided_scope is not None:
        payload['provided_scope'] = provided_scope
    return jsonify(payload), status


def validate_agent_token(token):
    """
    Validate an agent token and return the credential info if valid.
    Returns: (is_valid, credential_info) tuple
    """
    if not token or not token.startswith('lm_agent_'):
        return False, None

    try:
        from api.agent_credentials import validate_agent_token_internal
        is_valid, info = validate_agent_token_internal(token)
        return is_valid, info
    except Exception as e:
        logger.warning(f"Agent token validation error: {e}")
        return False, None


def validate_api_key_secure(api_key: str, endpoint: str = None, method: str = None) -> tuple:
    """
    Securely validate an API key using the APIKeyManager.

    SECURITY: This replaces the insecure len(api_key) >= 10 check with proper
    hash-based validation against stored API keys.

    Returns: (is_valid, api_key_obj, error_message)
    """
    if not api_key:
        return False, None, "API key required"

    # Quick format check before expensive validation
    if not api_key.startswith('sk_live_') or len(api_key) < 32:
        return False, None, "Invalid API key format"

    try:
        from auth.api_key_manager import get_api_key_manager
        manager = get_api_key_manager()

        # Get endpoint and method from request if not provided
        if endpoint is None:
            endpoint = request.path if request else '/'
        if method is None:
            method = request.method if request else 'GET'

        client_ip = request.remote_addr if request else None

        return manager.validate_api_key(api_key, endpoint, method, client_ip)
    except Exception as e:
        logger.error(f"API key validation error: {e}")
        return False, None, "API key validation failed"


def check_agent_session():
    """
    Check if there's an active agent session from /api/agent/session.
    Returns (is_valid, session_info) tuple.
    
    This enables the agent delegation chain - browser requests inherit
    the agent's authorization via Flask session.
    """
    try:
        if session.get('agent_authenticated'):
            return True, {
                'token_id': session.get('agent_token_id'),
                'authorized_by_ppid': session.get('agent_ppid'),
                'scope': session.get('agent_scope', []),
                'auth_method': 'agent_session'
            }
    except Exception as e:
        logger.debug(f"Agent session check error: {e}")
    return False, None

def require_api_key(f):
    """
    Decorator to require valid API key for endpoint access.
    
    Validates against:
    1. Platform API key (LEMMA_API_KEY or LEMMA_PLATFORM_API_KEY env var)
    2. Customer API keys stored in database (via customer_manager)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = _extract_api_key_from_request()
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # Check platform API key from environment
        import os
        platform_key = os.getenv('LEMMA_API_KEY') or os.getenv('LEMMA_PLATFORM_API_KEY')
        if platform_key and api_key == platform_key:
            g.api_key = api_key
            g.api_key_info = {'valid': True, 'type': 'platform'}
            return f(*args, **kwargs)
        
        # Validate against customer database
        try:
            from api.customer_accounts import customer_manager
            validation_result = customer_manager.validate_api_key(api_key)
            
            if validation_result.get('valid'):
                g.api_key = api_key
                g.api_key_info = validation_result
                return f(*args, **kwargs)
            else:
                return jsonify({
                    'error': 'Invalid API key',
                    'message': validation_result.get('error', 'API key validation failed')
                }), 401
                
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"API key validation error: {e}")
            return jsonify({'error': 'Unable to validate API key'}), 500
    
    return decorated_function

def require_site_admin(f):
    """
    Decorator to require site admin privileges (CLIENT-SIDE VERIFICATION)
    
    Architecture:
    - Client verifies credential locally (Ed25519 + Bloom filter)
    - Client sends only credential ID in X-Credential-ID header
    - Server checks if credential ID is revoked (simple hash lookup)
    - Server TRUSTS client-side verification (Web Crypto API at edge)
    
    AGENT DELEGATION:
    - Agent token in X-Agent-Token header
    - Agent session via Flask session (from /api/agent/session)
    Both inherit admin permissions from the authorizing user's passkey.
    
    This is TRUE EDGE COMPUTING - server is ultra-lightweight.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # METHOD 0a: Agent token with admin scope (header)
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                scope = normalize_scopes(credential_info.get('scope', []))
                if 'admin' in scope:
                    g.is_admin = True
                    g.admin_email = credential_info.get('authorized_by_email', 'agent@lemma.id')
                    g.auth_method = 'agent_token'
                    g.agent_credential = credential_info
                    g.ppid = credential_info.get('authorized_by_ppid')
                    return f(*args, **kwargs)
                else:
                    return _auth_error(
                        'missing_scope',
                        'Token was issued without admin scope. Request a new token with admin scope.',
                        status=403,
                        auth_method='agent_token',
                        required_scope=['admin'],
                        provided_scope=scope,
                    )
        
        # METHOD 0b: Agent session (from /api/agent/session - browser requests)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            scope = normalize_scopes(session_info.get('scope', []))
            if 'admin' in scope:
                g.is_admin = True
                g.admin_email = 'agent@lemma.id'
                g.auth_method = 'agent_session'
                g.ppid = session_info.get('authorized_by_ppid')
                g.agent_credential = session_info
                return f(*args, **kwargs)
            else:
                return _auth_error(
                    'missing_scope',
                    'Agent was authorized without admin scope.',
                    status=403,
                    auth_method='agent_session',
                    required_scope=['admin'],
                    provided_scope=scope,
                )
        
        # METHOD 1: Client-side verified credential (edge verification)
        credential_id = request.headers.get('X-Credential-ID')
        permission_id = request.headers.get('X-Permission-ID')
        user_email = request.headers.get('X-User-Email')
        
        if credential_id and permission_id:
            # Check revocation only (trust client-side signature verification)
            from api.wallet_revocation import is_credential_revoked
            
            if is_credential_revoked(credential_id):
                return _auth_error('credential_revoked', 'Credential revoked', status=401, auth_method='credential')
            
            # Verify it's an admin permission
            if is_admin_permission(permission_id):
                g.is_admin = True
                g.admin_email = user_email or 'admin@lemma.id'
                g.credential_id = credential_id
                g.permission_id = permission_id
                g.auth_method = 'credential'
                return f(*args, **kwargs)
            else:
                return _auth_error(
                    'missing_permission',
                    f'Admin permission required, got: {permission_id}',
                    status=403,
                    auth_method='credential',
                )
        
        # METHOD 2: API key (programmatic access - still supported)
        api_key = _extract_api_key_from_request()
        
        is_valid_key, key_obj, key_error = validate_api_key_secure(api_key)
        if is_valid_key:
            # API keys bypass credential system
            g.api_key = api_key
            g.is_admin = True
            g.admin_email = 'api@lemma.id'
            g.auth_method = 'api_key'
            return f(*args, **kwargs)
        
        # No valid auth found
        return _auth_error(
            'auth_required',
            'Admin authentication required (credential ID, API key, or agent token with admin scope)',
            status=401,
        )
    
    return decorated_function

def optional_auth(f):
    """
    Decorator that allows optional authentication via PPID, credential, API key, or agent session.
    Sets g.authenticated, g.ppid, g.credential_id as appropriate.
    
    AGENT DELEGATION: Also checks for agent sessions from /api/agent/session
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.authenticated = False
        
        # Method 0a: Agent token header
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                g.ppid = credential_info.get('authorized_by_ppid')
                g.authenticated = True
                g.auth_method = 'agent_token'
                g.agent_credential = credential_info
                return f(*args, **kwargs)
        
        # Method 0b: Agent session (browser requests from /api/agent/session)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            g.ppid = session_info.get('authorized_by_ppid')
            g.authenticated = True
            g.auth_method = 'agent_session'
            g.agent_credential = session_info
            return f(*args, **kwargs)
        
        # Method 1: PPID from header (SDK sends this after wallet auth)
        ppid = request.headers.get('X-Lemma-PPID')
        if ppid and ppid.startswith('did:lemma:ppid_'):
            g.ppid = ppid
            g.authenticated = True
            return f(*args, **kwargs)
        
        # Method 2: Credential headers (edge computing)
        credential_id = request.headers.get('X-Credential-ID')
        if credential_id:
            from api.wallet_revocation import is_credential_revoked
            if not is_credential_revoked(credential_id):
                g.credential_id = credential_id
                g.permission_id = request.headers.get('X-Permission-ID')
                g.authenticated = True
                return f(*args, **kwargs)
        
        # Method 3: API key fallback
        api_key = _extract_api_key_from_request()
        is_valid_key, key_obj, key_error = validate_api_key_secure(api_key)
        if is_valid_key:
            g.api_key = api_key
            g.authenticated = True
        
        return f(*args, **kwargs)
    
    return decorated_function

def cors_headers(f):
    """
    Decorator to add CORS headers to responses
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = make_response(f(*args, **kwargs))
        origin = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-CSRF-Token'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    return decorated_function

def require_admin(f):
    """
    Decorator to require admin privileges via credential, API key, or agent token.
    Uses the same pattern as require_site_admin for consistency.

    AGENT DELEGATION: Also checks for agent sessions from /api/agent/session
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Method 0a: Agent token with admin scope (header)
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                scope = normalize_scopes(credential_info.get('scope', []))
                if 'admin' in scope:
                    g.is_admin = True
                    g.admin_email = credential_info.get('authorized_by_email', 'agent@lemma.id')
                    g.auth_method = 'agent_token'
                    g.agent_credential = credential_info
                    g.ppid = credential_info.get('authorized_by_ppid')
                    return f(*args, **kwargs)
                return _auth_error(
                    'missing_scope',
                    'Token was issued without admin scope. Request a new token with admin scope.',
                    status=403,
                    auth_method='agent_token',
                    required_scope=['admin'],
                    provided_scope=scope,
                )

        # Method 0b: Agent session (browser requests from /api/agent/session)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            scope = normalize_scopes(session_info.get('scope', []))
            if 'admin' in scope:
                g.is_admin = True
                g.admin_email = 'agent@lemma.id'
                g.auth_method = 'agent_session'
                g.ppid = session_info.get('authorized_by_ppid')
                g.agent_credential = session_info
                return f(*args, **kwargs)
            return _auth_error(
                'missing_scope',
                'Agent was authorized without admin scope.',
                status=403,
                auth_method='agent_session',
                required_scope=['admin'],
                provided_scope=scope,
            )

        # Method 1: Client-side verified credential (edge verification)
        credential_id = request.headers.get('X-Credential-ID')
        permission_id = request.headers.get('X-Permission-ID')

        if credential_id and permission_id:
            from api.wallet_revocation import is_credential_revoked

            if is_credential_revoked(credential_id):
                return _auth_error('credential_revoked', 'Credential revoked', status=401, auth_method='credential')

            # Verify it's an admin permission
            if is_admin_permission(permission_id):
                g.is_admin = True
                g.credential_id = credential_id
                g.permission_id = permission_id
                g.auth_method = 'credential'
                return f(*args, **kwargs)
            return _auth_error(
                'missing_permission',
                f'Admin permission required, got: {permission_id}',
                status=403,
                auth_method='credential',
            )

        # Method 2: API key fallback (programmatic access)
        api_key = _extract_api_key_from_request()
        is_valid_key, key_obj, key_error = validate_api_key_secure(api_key)
        if is_valid_key:
            g.api_key = api_key
            g.is_admin = True
            g.auth_method = 'api_key'
            return f(*args, **kwargs)

        return _auth_error(
            'auth_required',
            'Admin authentication required (credential, API key, or agent token with admin scope)',
            status=401,
        )

    return decorated_function


def init_csrf_protection(app):
    """
    Initialize CSRF protection for the Flask app
    
    Uses double-submit cookie pattern:
    1. Server sets CSRF token in cookie (readable by JS)
    2. Client sends token in X-CSRF-Token header
    3. Server validates cookie matches header
    
    This protects against CSRF because:
    - Attacker can't read the cookie from another domain (same-origin policy)
    - Attacker can't set the header from another domain (CORS prevents it)
    """
    import secrets
    
    CSRF_COOKIE_NAME = 'lemma_csrf_token'
    CSRF_HEADER_NAME = 'X-CSRF-Token'
    
    # Methods that require CSRF protection
    PROTECTED_METHODS = ['POST', 'PUT', 'DELETE', 'PATCH']
    
    # Endpoints exempt from CSRF (API key authenticated, webhooks, etc.)
    CSRF_EXEMPT_PREFIXES = [
        '/api/sdk/',           # SDK endpoints use API key auth
        '/api/webhook/',       # Webhooks have their own auth
        '/api/passkey/authenticate/',  # WebAuthn has built-in CSRF protection
        '/api/passkey/register/',      # WebAuthn has built-in CSRF protection
        '/api/health',         # Health check
        '/api/revocation/',    # Public revocation list
    ]
    
    @app.before_request
    def csrf_protect():
        """Validate CSRF token for state-changing requests"""
        from flask import request, g
        
        # Skip non-protected methods
        if request.method not in PROTECTED_METHODS:
            return
        
        # Skip exempt endpoints
        for prefix in CSRF_EXEMPT_PREFIXES:
            if request.path.startswith(prefix):
                return
        
        # Skip if API key is present (programmatic access)
        if _extract_api_key_from_request():
            return
        
        # Validate CSRF token
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        
        # Also check form data for traditional forms
        if not header_token:
            header_token = request.form.get('csrf_token')
        
        if not cookie_token or not header_token:
            # Log but don't block yet (gradual rollout)
            app.logger.warning(f"⚠️ CSRF token missing for {request.method} {request.path}")
            # TODO: Return 403 after testing period
            # return jsonify({'error': 'CSRF token required'}), 403
            return
        
        if not secrets.compare_digest(cookie_token, header_token):
            app.logger.warning(f"🚫 CSRF token mismatch for {request.method} {request.path}")
            # TODO: Return 403 after testing period
            # return jsonify({'error': 'CSRF token invalid'}), 403
            return
        
        g.csrf_validated = True
    
    @app.after_request
    def set_csrf_cookie(response):
        """Set CSRF cookie if not present"""
        from flask import request
        
        # Only set for HTML responses or session-based auth
        if request.cookies.get(CSRF_COOKIE_NAME):
            return response
        
        # Generate new token
        token = secrets.token_urlsafe(32)
        
        # Set cookie (SameSite=Lax allows normal navigation, blocks cross-site POST)
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            httponly=False,  # JS needs to read this
            secure=True,
            samesite='Lax',
            max_age=86400 * 7  # 7 days
        )
        
        return response
    
    app.logger.info("✅ CSRF protection initialized")


def require_authenticated(f):
    """
    Decorator to require authenticated user via PPID, credential, API key, or agent session.
    
    AGENT DELEGATION: Supports agent token header and agent session from /api/agent/session.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Method 0a: Agent token header
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                g.ppid = credential_info.get('authorized_by_ppid')
                g.authenticated = True
                g.auth_method = 'agent_token'
                g.agent_credential = credential_info
                return f(*args, **kwargs)
        
        # Method 0b: Agent session (browser requests from /api/agent/session)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            g.ppid = session_info.get('authorized_by_ppid')
            g.authenticated = True
            g.auth_method = 'agent_session'
            g.agent_credential = session_info
            return f(*args, **kwargs)
        
        # Method 1: PPID from header (SDK sends this after wallet auth)
        ppid = request.headers.get('X-Lemma-PPID')
        if ppid and ppid.startswith('did:lemma:ppid_'):
            g.ppid = ppid
            g.authenticated = True
            return f(*args, **kwargs)
        
        # Method 2: Credential headers (edge computing)
        credential_id = request.headers.get('X-Credential-ID')
        if credential_id:
            from api.wallet_revocation import is_credential_revoked
            if not is_credential_revoked(credential_id):
                g.credential_id = credential_id
                g.permission_id = request.headers.get('X-Permission-ID')
                g.authenticated = True
                return f(*args, **kwargs)
        
        # Method 3: API key fallback
        api_key = _extract_api_key_from_request()
        is_valid_key, key_obj, key_error = validate_api_key_secure(api_key)
        if is_valid_key:
            g.api_key = api_key
            g.authenticated = True
            return f(*args, **kwargs)
        
        return jsonify({'error': 'Authentication required'}), 401
    
    return decorated_function


def get_current_user():
    """
    Get current authenticated user information from request context.
    """
    if hasattr(g, 'ppid'):
        return {'ppid': g.ppid, 'type': 'wallet'}
    elif hasattr(g, 'credential_id'):
        return {'credential_id': g.credential_id, 'permission_id': getattr(g, 'permission_id', None), 'type': 'credential'}
    elif hasattr(g, 'api_key'):
        return {'api_key': g.api_key, 'type': 'api_key'}
    return None

def require_permission_lemma(site_id='lemma.id', required_permissions=None):
    """
    Decorator to require a valid permission lemma for site access (CLIENT-SIDE VERIFICATION)
    
    Architecture (TRUE EDGE COMPUTING):
    - Client verifies credential locally using Web Crypto API (Ed25519 signature)
    - Client checks revocation locally using Bloom filter
    - Client sends only: credential ID, permission ID, user email (NO full credential)
    - Server checks revocation list (simple hash lookup - ultra fast)
    - Server TRUSTS client-side cryptographic verification
    
    This is Lemma's edge computing advantage - server is stateless and lightweight.
    
    Usage:
        @app.route('/dashboard')
        @require_permission_lemma('lemma.id', ['customer_access', 'admin_access'])
        def dashboard():
            return render_template('dashboard.html')
    """
    if required_permissions is None:
        required_permissions = ['customer_access', 'admin_access']
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import redirect, url_for, request
            
            # CLIENT-SIDE VERIFIED: Read minimal headers
            credential_id = request.headers.get('X-Credential-ID')
            permission_id = request.headers.get('X-Permission-ID')
            user_email = request.headers.get('X-User-Email')
            credential_site = request.headers.get('X-Site-ID')
            
            if credential_id and permission_id and credential_site == site_id:
                # Check revocation only (trust client-side signature verification)
                from api.wallet_revocation import is_credential_revoked
                
                if is_credential_revoked(credential_id):
                    return redirect(url_for('customer_accounts.login'))
                
                # Verify permission level
                if permission_id in required_permissions:
                    # Valid permission - server trusts client-side verification
                    g.credential_id = credential_id
                    g.permission_id = permission_id
                    g.user_email = user_email
                    return f(*args, **kwargs)
            
            # No valid credential - redirect to login
            return redirect(url_for('customer_accounts.login'))
        
        return decorated_function
    return decorator

def rate_limit(max_requests=100, window=60):
    """
    Decorator for rate limiting (mock implementation)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # TODO: Implement actual rate limiting with max_requests and window
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def require_wallet_ppid(f):
    """
    Decorator requiring authenticated wallet (via PPID).
    
    Accepts:
    1. X-Agent-Token header (AI agent with delegated access)
    2. Agent session via Flask session (from /api/agent/session)
    3. X-Lemma-PPID header (from SDK after wallet auth)
    4. PPID in request body (for API calls)
    5. API key fallback (X-API-Key)
    
    AGENT DELEGATION: Both header and session methods inherit PPID from
    the authorizing user's passkey.
    
    Sets g.ppid and g.authenticated on success.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Method 0a: Agent token (delegated access from human)
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                g.ppid = credential_info.get('authorized_by_ppid')
                g.authenticated = True
                g.auth_method = 'agent_token'
                g.agent_credential = credential_info
                return f(*args, **kwargs)
        
        # Method 0b: Agent session (browser requests from /api/agent/session)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            g.ppid = session_info.get('authorized_by_ppid')
            g.authenticated = True
            g.auth_method = 'agent_session'
            g.agent_credential = session_info
            return f(*args, **kwargs)
        
        # Method 1: PPID from header (SDK sends this after wallet auth)
        ppid = request.headers.get('X-Lemma-PPID')
        
        # Method 2: PPID from request body
        if not ppid:
            data = request.get_json(silent=True) or {}
            ppid = data.get('ppid')
        
        if ppid and ppid.startswith('did:lemma:ppid_'):
            g.ppid = ppid
            g.authenticated = True
            g.auth_method = 'ppid'
            return f(*args, **kwargs)
        
        # Method 3: API key fallback (for programmatic access)
        api_key = _extract_api_key_from_request()
        is_valid_key, key_obj, key_error = validate_api_key_secure(api_key)
        if is_valid_key:
            g.api_key = api_key
            g.authenticated = True
            g.auth_method = 'api_key'
            g.ppid = None  # No PPID for API key auth
            return f(*args, **kwargs)
        
        return jsonify({
            'success': False,
            'error': 'Authentication required',
            'message': 'Provide X-Agent-Token, X-Lemma-PPID, X-API-Key, or Authorization: Bearer <api_key>'
        }), 401
    
    return decorated_function


def require_customer_or_admin(f):
    """
    Decorator allowing either customer (PPID) or admin (credential) access.
    
    For endpoints that both customers and admins can access.
    
    AGENT DELEGATION: Supports both agent token header and agent session
    from /api/agent/session, inheriting permissions from the authorizing user.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try agent token first (header)
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                scope = credential_info.get('scope', [])
                g.ppid = credential_info.get('authorized_by_ppid')
                g.authenticated = True
                g.auth_method = 'agent_token'
                g.agent_credential = credential_info
                g.is_admin = 'admin' in scope
                return f(*args, **kwargs)
        
        # Try agent session (browser requests from /api/agent/session)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            scope = session_info.get('scope', [])
            g.ppid = session_info.get('authorized_by_ppid')
            g.authenticated = True
            g.auth_method = 'agent_session'
            g.agent_credential = session_info
            g.is_admin = 'admin' in scope
            return f(*args, **kwargs)
        
        # Try admin auth (credential headers)
        credential_id = request.headers.get('X-Credential-ID')
        permission_id = request.headers.get('X-Permission-ID')
        
        if credential_id and permission_id:
            from api.wallet_revocation import is_credential_revoked
            if not is_credential_revoked(credential_id):
                admin_permissions = ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin']
                if permission_id in admin_permissions or 'admin' in permission_id.lower():
                    g.is_admin = True
                    g.credential_id = credential_id
                    g.permission_id = permission_id
                    g.auth_method = 'credential'
                    return f(*args, **kwargs)
        
        # Try PPID auth
        ppid = request.headers.get('X-Lemma-PPID')
        if not ppid:
            data = request.get_json(silent=True) or {}
            ppid = data.get('ppid')
        
        if ppid and ppid.startswith('did:lemma:ppid_'):
            g.ppid = ppid
            g.is_admin = False
            g.authenticated = True
            g.auth_method = 'ppid'
            return f(*args, **kwargs)
        
        # API key fallback
        api_key = _extract_api_key_from_request()
        is_valid_key, key_obj, key_error = validate_api_key_secure(api_key)
        if is_valid_key:
            g.api_key = api_key
            g.authenticated = True
            g.auth_method = 'api_key'
            return f(*args, **kwargs)
        
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    return decorated_function