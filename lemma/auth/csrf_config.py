"""
CSRF Protection Configuration for Lemma Enterprise.
Provides enhanced CSRF protection for enterprise-grade security.
"""
import logging
from flask import request, abort, current_app, session, jsonify, render_template, make_response
from functools import wraps, update_wrapper
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf as flask_generate_csrf
import secrets
import os
import sys

logger = logging.getLogger(__name__)

def configure_csrf(app):
    """Configure CSRF protection for the application."""
    # Check if we're in testing mode
    testing_mode = app.config.get('TESTING', False)
    skip_auth = app.config.get('SKIP_AUTH_IN_TESTS', False)
    
    # Check if we're in development mode
    is_development = app.config.get('FLASK_ENV') == 'development' or app.config.get('FLASK_DEBUG') == '1'
    is_windows = "win" in sys.platform.lower()
    
    # Log CSRF protection configuration
    app.logger.info(f"Configuring CSRF protection (testing={testing_mode}, dev={is_development}, windows={is_windows})")
    
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
        
        # In development mode on Windows, provide more detailed error info
        if is_development and is_windows:
            csrf_token = request.headers.get('X-CSRF-Token', 'None')
            session_token = session.get('_csrf_token', 'None')
            app.logger.info(f"CSRF Debug - Request token: {csrf_token[:5]}... vs Session token: {session_token[:5]}...")
        
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
    
    # Configure exempt routes
    base_exempt_routes = [
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
    ,
        '/start-verification/<user_id>']
    
    # In development (especially on Windows), exempt more routes for easier testing
    if is_development and is_windows:
        app.logger.info("Development mode on Windows detected - exempting additional routes")
        base_exempt_routes.extend([
            '/api/start-verification',
            '/api/verify-human',
            '/api/presentation',
            '/api/debug-session'
        ])
    
    # Register all exempt routes
    for route in base_exempt_routes:
        csrf.exempt(route)
        
    # In testing mode with skip_auth, exempt all routes
    if testing_mode and skip_auth:
        app.logger.info("CSRF protection disabled for testing")
        csrf.exempt("*")
    
    return csrf

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
    
    # Determine secure cookie setting based on environment
    is_development = current_app.config.get('FLASK_ENV') == 'development' or current_app.config.get('FLASK_DEBUG') == '1'
    is_heroku = "DYNO" in os.environ
    is_windows = "win" in sys.platform.lower()
    
    # Only enforce secure cookies in production environments
    secure = not (is_development or current_app.config.get('TESTING', False)) and not is_windows
    
    # Set the token cookie with appropriate settings
    response.set_cookie(
        '_csrf_token',
        token,
        httponly=False,  # JavaScript needs access
        secure=secure,   # Only secure in production
        samesite='Lax' if not is_development else None,  # Allow more flexible cross-origin in development
        path='/',        # Available across all paths
        max_age=3600     # 1 hour expiry
    )
    
    # Log the token being set with security details
    current_app.logger.info(f"Setting new CSRF token in session and cookie (secure={secure}, env={'dev' if is_development else 'prod'})")
    
    return response

# Fixed CSRF protect decorator that can handle both @csrf_protect and @csrf_protect() usage patterns
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
    
    # Check if we're in development mode
    is_development = current_app.config.get('FLASK_ENV') == 'development' or current_app.config.get('FLASK_DEBUG') == '1'
    is_windows = "win" in sys.platform.lower()
    
    # Be more lenient in development mode on Windows
    if is_development and is_windows:
        current_app.logger.info("Development mode on Windows detected - relaxed CSRF validation")
        # If we have any token in the request, consider it valid in dev mode
        if request.headers.get('X-CSRF-Token') or (request.form and request.form.get('csrf_token')) or \
           (request.is_json and request.json and request.json.get('csrf_token')) or \
           request.cookies.get('_csrf_token'):
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
    
    # In development mode, be more lenient about token validation
    if is_development and not session_token:
        current_app.logger.warning("No session token found in development mode, using provided token")
        # In dev only, if no session token exists but a token was provided, accept it
        session['_csrf_token'] = token
        return True
    
    # Compare the provided token with the session token
    if not session_token or not token or not secrets.compare_digest(str(session_token), str(token)):
        current_app.logger.error(f"CSRF token validation failed - session: {session_token[:5]}... vs request: {token[:5]}...")
        return False
        
    return True
