"""
CSRF Protection Configuration for Lemma Enterprise.
Provides enhanced CSRF protection for enterprise-grade security.
"""
import logging
from flask import request, abort, current_app, session
from functools import wraps, update_wrapper
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf

logger = logging.getLogger(__name__)

# Initialize CSRF protection
csrf = CSRFProtect()

# List of exempt routes (paths that don't require CSRF protection)
CSRF_EXEMPT_ROUTES = [
    '/api/health',
    '/api/issue-credential',
    '/api/verify-credential',
    '/api/verify-presentation',
    '/api/generate-challenge',
    '/api/credentials',
    '/api/store-credential',
    '/api/credential/',
    '/admin/login',
    '/admin/issue',
    '/admin/revoke',
    '/admin/logout',
    '/api/node_info',
    '/api/peers',
    '/api/peers/add',
    '/api/peers/remove/',
    '/api/peers/discover',
    '/api/peers/health',
    '/api/peers/sync/',
    '/api/revocation/status',
    '/api/revocation/sync',
    '/api/revocation/import',
    '/api/revocation/issuers',
    '/api/revocation/issuer/',
    '/api/revocation/data/',
    '/api/revocation/check/',
    '/api/revocation/add_peer'
]

def configure_csrf(app):
    """Configure CSRF protection for the application."""
    # Check if we're in testing mode
    testing_mode = app.config.get('TESTING', False)
    skip_auth = app.config.get('SKIP_AUTH_IN_TESTS', False)
    
    # Log CSRF protection configuration
    app.logger.info("Configuring CSRF protection")
    
    # Initialize CSRF protection
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
        return {
            'error': 'CSRF validation failed',
            'message': e.description
        }, 400
    
    # Configure exempt routes
    for route in CSRF_EXEMPT_ROUTES:
        csrf.exempt(route)
        
    # In testing mode with skip_auth, exempt all routes
    if testing_mode and skip_auth:
        app.logger.info("CSRF protection disabled for testing")
        csrf.exempt("*")
    
    return app

def csrf_protect():
    """Decorator to explicitly require CSRF protection for a view."""
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            # Skip CSRF check in testing environment if configured
            if current_app.config.get('TESTING', False) and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
                return view_function(*args, **kwargs)
            
            # Validate CSRF token
            if not validate_csrf_token():
                current_app.logger.warning("CSRF validation failed from IP: %s", request.remote_addr)
                abort(400, "CSRF validation failed")
            
            return view_function(*args, **kwargs)
        
        # Update the name of the wrapped function to include the original function's name
        wrapped_view.__name__ = f"csrf_protected_{view_function.__name__}"
        
        # Make sure the blueprint endpoint routing works correctly
        update_wrapper(wrapped_view, view_function)
        
        return wrapped_view
    return decorator

def validate_csrf_token(token=None):
    """Validate a CSRF token."""
    # Skip CSRF validation in test environments if configured
    if current_app.config.get('TESTING', False):
        if current_app.config.get('SKIP_AUTH_IN_TESTS', False) or current_app.config.get('WTF_CSRF_ENABLED', False) is False:
            current_app.logger.info("Skipping CSRF validation in test environment")
            return True
        
    # Get token from request if not provided
    if token is None:
        # Check in headers first (for API requests)
        token = request.headers.get('X-CSRF-Token')
        
        # Then check in form data (for form submissions)
        if not token and request.form:
            token = request.form.get('csrf_token')
            
        # Finally check in JSON data (for API requests with JSON body)
        if not token and request.is_json:
            token = request.json.get('csrf_token')
    
    # Validate token using Flask-WTF
    try:
        csrf.validate_csrf(token)
        return True
    except CSRFError:
        return False

def generate_csrf_token():
    """Generate a CSRF token."""
    # In test mode with skip_auth, return a dummy token
    if current_app.config.get('TESTING', False) and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
        return 'test-csrf-token'
    
    # Use Flask-WTF's CSRF token generation
    try:
        return generate_csrf()
    except Exception as e:
        current_app.logger.warning(f"Error generating CSRF token: {e}")
        return None
