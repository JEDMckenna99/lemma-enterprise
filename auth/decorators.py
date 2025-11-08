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
    Decorator to require site admin privileges (session-free)
    Supports credential-based auth (web UI) AND API key auth (programmatic)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # METHOD 1: Check for credential-based auth (web UI)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                credential_json = auth_header.split(' ', 1)[1]
                credential = json.loads(credential_json)
                
                # Check if it's an admin permission lemma
                claims = credential.get('claims', {})
                permission_id = claims.get('permissionId', '')
                account_type = claims.get('accountType', '')
                
                if permission_id == 'admin_access' or account_type == 'admin':
                    g.is_admin = True
                    g.admin_email = claims.get('email', 'admin@lemma.id')
                    g.credential = credential
                    return f(*args, **kwargs)
            except:
                pass
        
        # METHOD 2: Check for API key (programmatic access)
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if api_key:
            # TODO: Validate API key against database
            # For now, accept any valid API key as admin for testing
            if len(api_key) < 10:
                return jsonify({'error': 'Invalid admin credentials'}), 403
            
            g.api_key = api_key
            g.is_admin = True
            g.admin_email = 'api@lemma.id'
            return f(*args, **kwargs)
        
        # No valid auth found
        return jsonify({'error': 'Admin authentication required (credential or API key)'}), 401
    
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
    Decorator to require a valid permission lemma for site access (session-free)
    Credential must be passed in Authorization header
    
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
            
            # SESSION-FREE: Check Authorization header for credential
            auth_header = request.headers.get('Authorization')
            
            if auth_header and auth_header.startswith('Bearer '):
                try:
                    credential_json = auth_header.split(' ', 1)[1]
                    credential = json.loads(credential_json)
                    
                    # Validate credential
                    claims = credential.get('claims', {})
                    permission_site = claims.get('siteId')
                    permission_id = claims.get('permissionId')
                    
                    if permission_site == site_id and permission_id in required_permissions:
                        # Valid permission lemma
                        g.credential = credential
                        g.permission_id = permission_id
                        return f(*args, **kwargs)
                except:
                    pass
            
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