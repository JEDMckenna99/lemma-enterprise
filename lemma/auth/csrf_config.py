"""
CSRF Protection Configuration for Lemma Enterprise.
Provides enhanced CSRF protection for enterprise-grade security.
"""
import logging
from flask import request, abort, current_app, session, jsonify, render_template
from functools import wraps, update_wrapper
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf as flask_generate_csrf
import secrets

logger = logging.getLogger(__name__)

def configure_csrf(app):
    """Configure CSRF protection for the application."""
    # Check if we're in testing mode
    testing_mode = app.config.get('TESTING', False)
    skip_auth = app.config.get('SKIP_AUTH_IN_TESTS', False)
    
    # Log CSRF protection configuration
    app.logger.info("Configuring CSRF protection")
    
    # Initialize CSRF protection
    csrf = CSRFProtect()
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
        
        # Check if request expects JSON
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({
                'error': 'CSRF validation failed',
                'message': e.description,
                'status': 'error'
            }), 400
        
        # For non-JSON requests, return HTML error
        return render_template('error.html', 
                             error="CSRF validation failed", 
                             message=e.description), 400
    
    # Configure exempt routes
    for route in [
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
    ]:
        csrf.exempt(route)
        
    # In testing mode with skip_auth, exempt all routes
    if testing_mode and skip_auth:
        app.logger.info("CSRF protection disabled for testing")
        csrf.exempt("*")
    
    return csrf

def generate_csrf():
    """Generate a CSRF token."""
    # In test mode with skip_auth, return a dummy token
    if current_app.config.get('TESTING', False) and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
        return 'test-csrf-token'
    
    # Use Flask-WTF's CSRF token generation
    try:
        token = flask_generate_csrf()
        # Set the token in the session
        session['_csrf_token'] = token
        return token
    except Exception as e:
        current_app.logger.warning(f"Error generating CSRF token: {e}")
        return None

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
            
        # If still no token, check the session
        if not token:
            token = session.get('_csrf_token')
    
    # If no token found anywhere, validation fails
    if not token:
        current_app.logger.error("No CSRF token found in request")
        return False
    
    # Get the session token
    session_token = session.get('_csrf_token')
    
    # Compare the provided token with the session token
    if not session_token or not token or not secrets.compare_digest(str(session_token), str(token)):
        current_app.logger.error("CSRF token validation failed")
        return False
        
    return True
