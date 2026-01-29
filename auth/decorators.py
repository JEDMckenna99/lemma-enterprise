"""
Authentication and authorization decorators for Lemma.id platform
Session-free architecture - all auth via credentials + smart caching
"""

from functools import wraps
from flask import request, jsonify, g, make_response
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

def require_api_key(f):
    """
    Decorator to require valid API key for endpoint access
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # TODO: Validate API key against database
        # For now, accept any non-empty API key for testing
        if len(api_key) < 10:
            return jsonify({'error': 'Invalid API key'}), 401
        
        g.api_key = api_key
        return f(*args, **kwargs)
    
    return decorated_function

def require_site_admin(f):
    """
    Decorator to require site admin privileges (CLIENT-SIDE VERIFICATION)
    
    Architecture:
    - Client verifies credential locally (Ed25519 + Bloom filter)
    - Client sends only credential ID in X-Credential-ID header
    - Server checks if credential ID is revoked (simple hash lookup)
    - Server TRUSTS client-side verification (Web Crypto API at edge)
    
    This is TRUE EDGE COMPUTING - server is ultra-lightweight.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # METHOD 0: Agent token with admin scope
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
    Decorator that allows optional authentication via PPID, credential, or API key.
    Sets g.authenticated, g.ppid, g.credential_id as appropriate.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.authenticated = False
        
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
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Method 0: Agent token with admin scope
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
    Decorator to require authenticated user via PPID, credential, or API key.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
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
    2. X-Lemma-PPID header (from SDK after wallet auth)
    3. PPID in request body (for API calls)
    4. API key fallback (X-API-Key)
    
    Sets g.ppid and g.authenticated on success.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Method 0: Agent token (delegated access from human)
        agent_token = request.headers.get('X-Agent-Token')
        if agent_token:
            is_valid, credential_info = validate_agent_token(agent_token)
            if is_valid:
                g.ppid = credential_info.get('authorized_by_ppid')
                g.authenticated = True
                g.auth_method = 'agent_token'
                g.agent_credential = credential_info
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
    Also supports agent tokens.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try agent token first
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