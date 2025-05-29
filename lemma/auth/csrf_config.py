"""
CSRF Protection Configuration for Lemma Enterprise.
Provides enhanced CSRF protection for enterprise-grade security.
"""
import logging
import secrets
import os
from flask import request, abort, current_app, session, jsonify, render_template, make_response
from functools import wraps, update_wrapper
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf as flask_generate_csrf

logger = logging.getLogger(__name__)

def configure_csrf(app):
    """Configure CSRF protection for the application."""
    # Check if we're in testing mode
    testing_mode = app.config.get('TESTING', False)
    skip_auth = app.config.get('SKIP_AUTH_IN_TESTS', False)
    
    # Log CSRF protection configuration
    app.logger.info(f"Configuring CSRF protection (testing={testing_mode})")
    
    # Configure Flask-WTF CSRF settings
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # We'll handle CSRF manually
    app.config['WTF_CSRF_SSL_STRICT'] = False     # Allow non-HTTPS in development
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600      # 1 hour token lifetime
    
    # Initialize CSRF protection with custom configuration
    csrf = CSRFProtect()
    
    # Store reference to CSRF instance for exemptions
    app.csrf = csrf
    
    # Override the protect method to exempt API key-protected endpoints
    original_protect = csrf.protect
    
    def custom_csrf_protect():
        """
        Custom CSRF protection that exempts API key-protected endpoints.
        """
        # List of API endpoints that should be exempt from CSRF because they use API key auth
        api_key_endpoints = [
            '/api/issue-credential',
            '/api/verify-credential',
            '/api/user-credential',
            '/api/credentials', 
            '/api/presentation',
            '/api/verify-presentation',
            '/api/revocation/status',
            '/api/revocation/sync',
            '/api/revocation/import',
            '/api/revocation/issuers',
            '/api/revocation/add_peer',
            '/api/peers',
            '/api/peers/add',
            '/api/peers/discover',
            '/api/peers/health'
        ]
        
        # List of endpoints that should use relaxed CSRF (no referrer check)
        relaxed_csrf_endpoints = [
            '/api/v2/security-log',
            '/api/security-log'
        ]
        
        # Check if this is a relaxed CSRF endpoint
        if request.path in relaxed_csrf_endpoints:
            # For security logging, just check token without referrer
            token = request.headers.get('X-CSRF-Token')
            if not token and request.is_json:
                token = request.json.get('csrf_token')
            
            if token and session.get('_csrf_token'):
                if secrets.compare_digest(str(session.get('_csrf_token')), str(token)):
                    return  # Valid token, allow request
            
            # Invalid or missing token for relaxed endpoint
            abort(400, "CSRF token required")
        
        # Check if this is an API key-protected endpoint
        if request.path.startswith('/api/') and request.method in ['POST', 'PUT', 'DELETE']:
            for endpoint in api_key_endpoints:
                if request.path == endpoint or request.path.startswith(endpoint + '/'):
                    # Skip CSRF protection for API key endpoints
                    return
        
        # Use original CSRF protection for all other endpoints
        return original_protect()
    
    # Replace the protect method
    csrf.protect = custom_csrf_protect
    csrf.init_app(app)
    
    # Register error handler for CSRF errors
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Handle CSRF errors."""
        # In testing mode with skip_auth, don't raise CSRF errors
        if testing_mode and skip_auth:
            return {}, 200
            
        app.logger.warning("CSRF error: %s from IP: %s", 
                          e.description, request.remote_addr)
        
        # Always return JSON for API routes
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'CSRF validation failed',
                'message': e.description,
                'status': 'error'
            }), 400
        
        # For non-API requests, return HTML error
        return render_template('error.html', 
                             error="CSRF validation failed", 
                             message=e.description), 400

def generate_csrf():
    """Generate a CSRF token and set it in both session and cookie."""
    # In test mode with skip_auth, return a dummy token
    if current_app.config.get('TESTING', False) and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
        return 'test-csrf-token'
    
    # Generate a new token using Flask-WTF's function
    token = flask_generate_csrf()
    
    # Set the token in the session
    session['_csrf_token'] = token
    
    return token

def get_csrf_response(token=None):
    """Create a response with CSRF token in both JSON and cookie."""
    if token is None:
        token = generate_csrf()
    
    # Create the response
    response = make_response(jsonify({'csrf_token': token}))
    
    # Store token in session
    session['_csrf_token'] = token
    
    # Use secure cookies in production environments
    is_production = not current_app.config.get('TESTING', False)
    
    # Set the token cookie with appropriate settings
    response.set_cookie(
        '_csrf_token',
        token,
        httponly=False,  # JavaScript needs access
        secure=is_production,   # Secure in production
        samesite='Strict',      # Strict SameSite policy
        path='/',               # Available across all paths
        max_age=3600            # 1 hour expiry
    )
    
    # Log the token being set
    current_app.logger.info(f"Setting new CSRF token in session and cookie (secure={is_production})")
    
    return response

def csrf_protect(f=None):
    """
    Decorator to explicitly require CSRF protection for a view.
    Can be used as @csrf_protect or @csrf_protect()
    """
    # This allows the decorator to be used with or without parentheses
    if f is None:
        return csrf_protect
        
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip CSRF check in testing environment if configured
        if current_app.config.get('TESTING', False) and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
            return f(*args, **kwargs)
        
        # Validate CSRF token
        if not validate_csrf_token():
            current_app.logger.warning("CSRF validation failed from IP: %s", request.remote_addr)
            abort(400, "CSRF validation failed")
        
        return f(*args, **kwargs)
    
    # Update the name of the wrapped function to include the original function's name
    decorated_function.__name__ = f"csrf_protected_{f.__name__}"
    
    # Make sure the blueprint endpoint routing works correctly
    update_wrapper(decorated_function, f)
    
    return decorated_function

def validate_csrf_token(token=None):
    """Validate a CSRF token."""
    # Skip CSRF validation in test environments if configured
    if current_app.config.get('TESTING', False):
        if current_app.config.get('SKIP_AUTH_IN_TESTS', False):
            current_app.logger.info("Skipping CSRF validation in test environment")
            return True
    
    # Get token from request if not provided
    if token is None:
        # Check in headers first (for API requests)
        token = request.headers.get('X-CSRF-Token')
        
        # Then check in form data (for form submissions)
        if not token and request.form:
            token = request.form.get('csrf_token')
            
        # Check in JSON data (for API requests with JSON body)
        if not token and request.is_json:
            token = request.json.get('csrf_token')
            
        # Check in cookies
        if not token:
            token = request.cookies.get('_csrf_token')
            
        # Finally check in session
        if not token:
            token = session.get('_csrf_token')
    
    # If no token found anywhere, validation fails
    if not token:
        current_app.logger.error("No CSRF token found in request")
        return False
    
    # Get the session token
    session_token = session.get('_csrf_token')
    
    # If no session token exists, validation fails
    if not session_token:
        current_app.logger.error("No session token found")
        return False
    
    # Compare the provided token with the session token
    if not secrets.compare_digest(str(session_token), str(token)):
        current_app.logger.error("CSRF token validation failed")
        return False
        
    return True
