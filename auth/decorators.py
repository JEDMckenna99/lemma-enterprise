"""
Authentication and authorization decorators for Lemma.id platform
Session-free architecture - all auth via credentials + smart caching
"""

from functools import wraps
from flask import request, jsonify, g, make_response
import jwt
import json
from typing import Optional

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
        # METHOD 1: Client-side verified credential (edge verification)
        credential_id = request.headers.get('X-Credential-ID')
        permission_id = request.headers.get('X-Permission-ID')
        user_email = request.headers.get('X-User-Email')
        
        if credential_id and permission_id:
            # Check revocation only (trust client-side signature verification)
            from api.wallet_revocation import is_credential_revoked
            
            if is_credential_revoked(credential_id):
                return jsonify({'error': 'Credential revoked'}), 401
            
            # Verify it's an admin permission
            if permission_id in ['admin_access', 'super_admin']:
                g.is_admin = True
                g.admin_email = user_email or 'admin@lemma.id'
                g.credential_id = credential_id
                g.permission_id = permission_id
                return f(*args, **kwargs)
            else:
                return jsonify({'error': 'Admin permission required'}), 403
        
        # METHOD 2: API key (programmatic access - still supported)
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if api_key and len(api_key) >= 10:
            # API keys bypass credential system
            g.api_key = api_key
            g.is_admin = True
            g.admin_email = 'api@lemma.id'
            return f(*args, **kwargs)
        
        # No valid auth found
        return jsonify({'error': 'Admin authentication required (credential ID or API key)'}), 401
    
    return decorated_function

def require_oauth_token(f):
    """
    Decorator to require valid OAuth access token
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'OAuth token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        try:
            # TODO: Use proper secret key from config
            payload = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
            g.oauth_payload = payload
            g.site_id = payload.get('site_id')
            return f(*args, **kwargs)
        except jwt.InvalidTokenError as e:
            return jsonify({'error': f'Invalid token: {str(e)}'}), 401
    
    return decorated_function

def optional_auth(f):
    """
    Decorator that allows optional authentication
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try API key first
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key and len(api_key) >= 10:
            g.api_key = api_key
            g.authenticated = True
        else:
            # Try OAuth token
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                try:
                    payload = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
                    g.oauth_payload = payload
                    g.site_id = payload.get('site_id')
                    g.authenticated = True
                except jwt.InvalidTokenError:
                    g.authenticated = False
            else:
                g.authenticated = False
        
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
    Decorator to require admin privileges
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key first
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'Admin API key required'}), 401
        
        # TODO: Validate admin privileges against database
        # For now, accept any valid API key as admin for testing
        if len(api_key) < 10:
            return jsonify({'error': 'Invalid admin credentials'}), 403
        
        g.api_key = api_key
        g.is_admin = True
        return f(*args, **kwargs)
    
    return decorated_function

def init_csrf_protection(app):
    """
    Initialize CSRF protection for the Flask app
    """
    # TODO: Implement CSRF protection
    pass

def require_authenticated(f):
    """
    Decorator to require authenticated user
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for any form of authentication
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        auth_header = request.headers.get('Authorization')
        
        authenticated = False
        
        if api_key and len(api_key) >= 10:
            g.api_key = api_key
            authenticated = True
        elif auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                payload = jwt.decode(token, 'your-secret-key', algorithms=['HS256'])
                g.oauth_payload = payload
                g.site_id = payload.get('site_id')
                authenticated = True
            except jwt.InvalidTokenError:
                pass
        
        if not authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        
        g.authenticated = True
        return f(*args, **kwargs)
    
    return decorated_function

def get_current_user():
    """
    Get current authenticated user information
    """
    if hasattr(g, 'oauth_payload'):
        return g.oauth_payload
    elif hasattr(g, 'api_key'):
        return {'api_key': g.api_key}
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