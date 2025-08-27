"""
Security Decorators - Salvaged from Old Build
============================================
Enhanced security decorators for CSRF protection, rate limiting, and API key authentication.
"""

import time
import logging
from functools import wraps
from flask import request, jsonify, session, current_app, g, redirect, url_for
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Rate limiting storage (in production, use Redis)
rate_limit_storage = {}

def csrf_protect(f):
    """
    SALVAGED: CSRF protection decorator
    Validates CSRF tokens for state-changing requests
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Get CSRF token from headers
            token = (request.headers.get('X-CSRF-Token') or 
                    request.headers.get('X-CSRFToken') or
                    request.headers.get('X-XSRF-TOKEN'))
            
            # Get session token
            session_token = session.get('csrf_token')
            
            if not token:
                logger.warning(f"CSRF token missing for {request.endpoint}")
                return jsonify({
                    'success': False,
                    'error': 'csrf_token_missing',
                    'message': 'CSRF token required for this request',
                    'shield_action': 'require_verification'
                }), 403
            
            if not session_token:
                logger.warning(f"Session CSRF token missing for {request.endpoint}")
                return jsonify({
                    'success': False,
                    'error': 'csrf_session_missing',
                    'message': 'CSRF session not found',
                    'shield_action': 'require_verification'
                }), 403
            
            if token != session_token:
                logger.warning(f"CSRF token mismatch for {request.endpoint}")
                return jsonify({
                    'success': False,
                    'error': 'csrf_token_invalid',
                    'message': 'Invalid CSRF token',
                    'shield_action': 'require_verification'
                }), 403
        
        return f(*args, **kwargs)
    return decorated_function

def rate_limit(max_requests: int = 100, window: int = 60, per_ip: bool = True):
    """
    SALVAGED: Rate limiting decorator
    Limits requests per IP or globally within a time window
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_time = time.time()
            
            # Generate key for rate limiting
            if per_ip:
                key = f"rate_limit:{request.remote_addr}:{request.endpoint}"
            else:
                key = f"rate_limit:global:{request.endpoint}"
            
            # Clean old entries
            if key in rate_limit_storage:
                rate_limit_storage[key] = [
                    timestamp for timestamp in rate_limit_storage[key]
                    if current_time - timestamp < window
                ]
            else:
                rate_limit_storage[key] = []
            
            # Check rate limit
            if len(rate_limit_storage[key]) >= max_requests:
                logger.warning(f"Rate limit exceeded for {key}")
                return jsonify({
                    'success': False,
                    'error': 'rate_limit_exceeded',
                    'message': f'Rate limit exceeded. Max {max_requests} requests per {window} seconds.',
                    'retry_after': window,
                    'shield_action': 'rate_limited'
                }), 429
            
            # Add current request
            rate_limit_storage[key].append(current_time)
            
            # Add rate limit headers
            response = f(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(max_requests)
                response.headers['X-RateLimit-Remaining'] = str(max_requests - len(rate_limit_storage[key]))
                response.headers['X-RateLimit-Reset'] = str(int(current_time + window))
            
            return response
        return decorated_function
    return decorator

def require_api_key(f):
    """
    SALVAGED: API key authentication decorator
    Requires valid API key for access
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key from headers
        api_key = (request.headers.get('X-API-Key') or 
                  request.headers.get('Authorization', '').replace('Bearer ', ''))
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'api_key_required',
                'message': 'API key required for this endpoint',
                'shield_action': 'require_api_key'
            }), 401
        
        # Validate API key (implement your validation logic)
        if not validate_api_key(api_key):
            return jsonify({
                'success': False,
                'error': 'invalid_api_key',
                'message': 'Invalid API key',
                'shield_action': 'invalid_credentials'
            }), 401
        
        # Store API key info in g for use in the request
        g.api_key = api_key
        
        return f(*args, **kwargs)
    return decorated_function

def validate_api_key(api_key: str) -> bool:
    """
    Validate API key
    In production, check against database or API key service
    """
    if not api_key:
        return False
    
    # For development, accept any key that starts with 'lemma_'
    if current_app.debug and api_key.startswith('lemma_'):
        return True
    
    # TODO: Implement proper API key validation
    # This should check against your API key management system
    return True

def cors_headers(f):
    """
    SALVAGED: CORS headers decorator
    Adds appropriate CORS headers for cross-origin requests
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import make_response
        
        response = f(*args, **kwargs)
        
        # Convert to Flask Response object if needed
        if not hasattr(response, 'headers'):
            response = make_response(response)
        
        # Add CORS headers
        origin = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-CSRF-Token'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'
        
        return response
    return decorated_function

def require_verified_user(f):
    """
    SALVAGED: Require verified user decorator
    Ensures user has completed verification
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is verified
        if not session.get('verified_user'):
            return jsonify({
                'success': False,
                'error': 'verification_required',
                'message': 'User verification required',
                'shield_action': 'require_verification'
            }), 401
        
        # Check if verification is still valid
        verification_time = session.get('verification_time')
        if verification_time:
            verification_age = time.time() - verification_time
            # Verification expires after 24 hours
            if verification_age > 86400:
                session.pop('verified_user', None)
                session.pop('verification_time', None)
                return jsonify({
                    'success': False,
                    'error': 'verification_expired',
                    'message': 'User verification has expired',
                    'shield_action': 'require_verification'
                }), 401
        
        return f(*args, **kwargs)
    return decorated_function

def init_csrf_protection(app):
    """
    Initialize CSRF protection for the Flask app
    """
    @app.before_request
    def generate_csrf_token():
        """Generate CSRF token if not present"""
        if 'csrf_token' not in session:
            session['csrf_token'] = generate_secure_token()
    
    @app.route('/api/csrf-token', methods=['GET'])
    def get_csrf_token():
        """Get CSRF token for client-side requests"""
        return jsonify({
            'success': True,
            'csrf_token': session.get('csrf_token'),
            'message': 'CSRF token generated'
        })

def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token"""
    import secrets
    return secrets.token_urlsafe(length)

def log_security_event(event_type: str, details: Dict[str, Any], level: str = 'INFO'):
    """
    SALVAGED: Security event logging
    Logs security events for monitoring and analysis
    """
    security_logger = logging.getLogger('security')
    
    log_entry = {
        'event_type': event_type,
        'timestamp': time.time(),
        'ip_address': request.remote_addr if request else 'unknown',
        'user_agent': request.user_agent.string if request else 'unknown',
        'endpoint': request.endpoint if request else 'unknown',
        'details': details
    }
    
    if level == 'WARNING':
        security_logger.warning(f"Security event: {event_type}", extra=log_entry)
    elif level == 'ERROR':
        security_logger.error(f"Security event: {event_type}", extra=log_entry)
    else:
        security_logger.info(f"Security event: {event_type}", extra=log_entry)

# Input validation helpers
def validate_json_input(required_fields: list = None, optional_fields: list = None):
    """
    SALVAGED: JSON input validation decorator
    Validates JSON input structure
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'error': 'invalid_content_type',
                    'message': 'Content-Type must be application/json'
                }), 400
            
            try:
                data = request.get_json()
                if data is None:
                    return jsonify({
                        'success': False,
                        'error': 'invalid_json',
                        'message': 'Invalid JSON in request body'
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': 'json_parse_error',
                    'message': f'Failed to parse JSON: {str(e)}'
                }), 400
            
            # Validate required fields
            if required_fields:
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    return jsonify({
                        'success': False,
                        'error': 'missing_required_fields',
                        'message': f'Missing required fields: {", ".join(missing_fields)}'
                    }), 400
            
            # Store validated data in g for use in the request
            g.validated_json = data
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================================
# ROLE-BASED AUTHORIZATION DECORATORS
# ============================================================================

def require_authenticated(redirect_to_login=True):
    """
    Decorator to require authenticated user
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            customer_id = session.get('customer_id')
            if not customer_id:
                if redirect_to_login and request.endpoint and not request.is_json:
                    return redirect(url_for('customer_accounts.login'))
                return jsonify({
                    'success': False,
                    'error': 'authentication_required',
                    'message': 'Authentication required',
                    'redirect_url': '/login'
                }), 401
            
            # Store customer info in g for use in request
            g.customer_id = customer_id
            g.user_role = session.get('user_role', 'customer')
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_role(required_role: str, redirect_to_login=True):
    """
    Decorator to require specific user role
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            customer_id = session.get('customer_id')
            user_role = session.get('user_role', 'customer')
            
            if not customer_id:
                if redirect_to_login and request.endpoint and not request.is_json:
                    return redirect(url_for('customer_accounts.login'))
                return jsonify({
                    'success': False,
                    'error': 'authentication_required',
                    'message': 'Authentication required',
                    'redirect_url': '/login'
                }), 401
            
            if user_role != required_role:
                log_security_event('unauthorized_role_access', {
                    'required_role': required_role,
                    'user_role': user_role,
                    'customer_id': customer_id,
                    'endpoint': request.endpoint
                }, 'WARNING')
                
                if redirect_to_login and request.endpoint and not request.is_json:
                    return redirect(url_for('index'))  # Redirect to home instead of error
                return jsonify({
                    'success': False,
                    'error': 'insufficient_permissions',
                    'message': f'Role "{required_role}" required for this action',
                    'user_role': user_role
                }), 403
            
            # Store user info in g for use in request
            g.customer_id = customer_id
            g.user_role = user_role
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_admin(redirect_to_login=True):
    """
    Decorator to require admin role
    """
    return require_role('admin', redirect_to_login)

def require_customer(redirect_to_login=True):
    """
    Decorator to require customer role (or higher)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            customer_id = session.get('customer_id')
            user_role = session.get('user_role', 'customer')
            
            if not customer_id:
                if redirect_to_login and request.endpoint and not request.is_json:
                    return redirect(url_for('customer_accounts.login'))
                return jsonify({
                    'success': False,
                    'error': 'authentication_required',
                    'message': 'Authentication required',
                    'redirect_url': '/login'
                }), 401
            
            # Allow both customer and admin roles
            if user_role not in ['customer', 'admin']:
                log_security_event('unauthorized_role_access', {
                    'required_role': 'customer_or_admin',
                    'user_role': user_role,
                    'customer_id': customer_id,
                    'endpoint': request.endpoint
                }, 'WARNING')
                
                return jsonify({
                    'success': False,
                    'error': 'insufficient_permissions',
                    'message': 'Customer account required for this action',
                    'user_role': user_role
                }), 403
            
            # Store user info in g for use in request
            g.customer_id = customer_id
            g.user_role = user_role
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """
    Helper function to get current user info from session
    """
    return {
        'customer_id': session.get('customer_id'),
        'user_role': session.get('user_role', 'customer'),
        'is_authenticated': bool(session.get('customer_id')),
        'is_admin': session.get('user_role') == 'admin',
        'is_customer': session.get('user_role') in ['customer', 'admin']
    } 