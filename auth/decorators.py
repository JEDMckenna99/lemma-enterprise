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

logger = logging.getLogger(__name__)


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
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
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
                scope = credential_info.get('scope', [])
                if 'admin' in scope:
                    g.is_admin = True
                    g.admin_email = credential_info.get('authorized_by_email', 'agent@lemma.id')
                    g.auth_method = 'agent_token'
                    g.agent_credential = credential_info
                    g.ppid = credential_info.get('authorized_by_ppid')
                    return f(*args, **kwargs)
                else:
                    return jsonify({
                        'error': 'Agent token lacks admin scope',
                        'message': 'Token was issued without admin scope. Request a new token with admin scope.'
                    }), 403
        
        # METHOD 0b: Agent session (from /api/agent/session - browser requests)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            scope = session_info.get('scope', [])
            if 'admin' in scope:
                g.is_admin = True
                g.admin_email = 'agent@lemma.id'
                g.auth_method = 'agent_session'
                g.ppid = session_info.get('authorized_by_ppid')
                g.agent_credential = session_info
                return f(*args, **kwargs)
            else:
                return jsonify({
                    'error': 'Agent session lacks admin scope',
                    'message': 'Agent was authorized without admin scope.'
                }), 403
        
        # METHOD 1: Client-side verified credential (edge verification)
        credential_id = request.headers.get('X-Credential-ID')
        permission_id = request.headers.get('X-Permission-ID')
        user_email = request.headers.get('X-User-Email')
        
        if credential_id and permission_id:
            # Check revocation only (trust client-side signature verification)
            from api.wallet_revocation import is_credential_revoked
            
            if is_credential_revoked(credential_id):
                return jsonify({'error': 'Credential revoked'}), 401
            
            # Verify it's an admin permission (accept common admin permission names)
            admin_permissions = ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin']
            if permission_id in admin_permissions or 'admin' in permission_id.lower():
                g.is_admin = True
                g.admin_email = user_email or 'admin@lemma.id'
                g.credential_id = credential_id
                g.permission_id = permission_id
                g.auth_method = 'credential'
                return f(*args, **kwargs)
            else:
                return jsonify({'error': f'Admin permission required, got: {permission_id}'}), 403
        
        # METHOD 2: API key (programmatic access - still supported)
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if api_key and len(api_key) >= 10:
            # API keys bypass credential system
            g.api_key = api_key
            g.is_admin = True
            g.admin_email = 'api@lemma.id'
            g.auth_method = 'api_key'
            return f(*args, **kwargs)
        
        # No valid auth found
        return jsonify({'error': 'Admin authentication required (credential ID, API key, or agent token with admin scope)'}), 401
    
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
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key and len(api_key) >= 10:
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
                scope = credential_info.get('scope', [])
                if 'admin' in scope:
                    g.is_admin = True
                    g.admin_email = credential_info.get('authorized_by_email', 'agent@lemma.id')
                    g.auth_method = 'agent_token'
                    g.agent_credential = credential_info
                    g.ppid = credential_info.get('authorized_by_ppid')
                    return f(*args, **kwargs)
                else:
                    return jsonify({
                        'error': 'Agent token lacks admin scope',
                        'message': 'Token was issued without admin scope. Request a new token with admin scope.'
                    }), 403
        
        # Method 0b: Agent session (browser requests from /api/agent/session)
        is_agent_session, session_info = check_agent_session()
        if is_agent_session:
            scope = session_info.get('scope', [])
            if 'admin' in scope:
                g.is_admin = True
                g.admin_email = 'agent@lemma.id'
                g.auth_method = 'agent_session'
                g.ppid = session_info.get('authorized_by_ppid')
                g.agent_credential = session_info
                return f(*args, **kwargs)
            else:
                return jsonify({
                    'error': 'Agent session lacks admin scope',
                    'message': 'Agent was authorized without admin scope.'
                }), 403
        
        # Method 1: Client-side verified credential (edge verification)
        credential_id = request.headers.get('X-Credential-ID')
        permission_id = request.headers.get('X-Permission-ID')
        
        if credential_id and permission_id:
            from api.wallet_revocation import is_credential_revoked
            
            if is_credential_revoked(credential_id):
                return jsonify({'error': 'Credential revoked'}), 401
            
            # Verify it's an admin permission
            admin_permissions = ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin']
            if permission_id in admin_permissions or 'admin' in permission_id.lower():
                g.is_admin = True
                g.credential_id = credential_id
                g.permission_id = permission_id
                g.auth_method = 'credential'
                return f(*args, **kwargs)
            else:
                return jsonify({'error': f'Admin permission required, got: {permission_id}'}), 403
        
        # Method 2: API key fallback (programmatic access)
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key and len(api_key) >= 10:
            g.api_key = api_key
            g.is_admin = True
            g.auth_method = 'api_key'
            return f(*args, **kwargs)
        
        return jsonify({'error': 'Admin authentication required (credential, API key, or agent token with admin scope)'}), 401
    
    return decorated_function


def init_csrf_protection(app):
    """
    Initialize CSRF protection for the Flask app
    """
    # TODO: Implement CSRF protection
    pass


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
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key and len(api_key) >= 10:
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
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key and len(api_key) >= 10:
            g.api_key = api_key
            g.authenticated = True
            g.auth_method = 'api_key'
            g.ppid = None  # No PPID for API key auth
            return f(*args, **kwargs)
        
        return jsonify({
            'success': False,
            'error': 'Authentication required',
            'message': 'Provide X-Agent-Token, X-Lemma-PPID, or X-API-Key'
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
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key and len(api_key) >= 10:
            g.api_key = api_key
            g.authenticated = True
            g.auth_method = 'api_key'
            return f(*args, **kwargs)
        
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    return decorated_function