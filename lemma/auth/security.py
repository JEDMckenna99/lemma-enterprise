"""
Security module for Lemma Enterprise.
Handles authentication, password hashing, and secure session management.
"""
import os
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from functools import wraps
from flask import current_app, session, redirect, url_for, request, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password):
    """Hash a password for secure storage using Werkzeug's implementation."""
    return generate_password_hash(password, method='pbkdf2:sha256:150000')

def verify_password(stored_hash, provided_password):
    """Verify a password against a stored hash."""
    return check_password_hash(stored_hash, provided_password)

def get_admin_password_hash():
    """Get the admin password hash, creating it if necessary."""
    # Check if we have a stored hash
    storage_dir = current_app.config['STORAGE_DIR']
    hash_file = os.path.join(storage_dir, "admin_hash.txt")
    
    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            return f.read().strip()
    
    # Create a new hash from the configured password
    password = current_app.config['ADMIN_PASS']
    password_hash = hash_password(password)
    
    # Store the hash securely
    with open(hash_file, 'w') as f:
        f.write(password_hash)
    
    return password_hash

def authenticate_admin(username, password):
    """Authenticate an admin user."""
    if username != current_app.config['ADMIN_USERNAME']:
        return False
    
    # Get the stored password hash
    stored_hash = get_admin_password_hash()
    
    # Verify the password
    return verify_password(stored_hash, password)

def login_admin(username, password):
    """Authenticate and log in an admin user."""
    if authenticate_admin(username, password):
        session['admin_logged_in'] = True
        session['admin_username'] = username
        # Log the admin login for security audit trail
        current_app.logger.info(f"Admin login: {username} from {request.remote_addr} at {datetime.now().isoformat()}")
        return True
    return False

def logout_admin():
    """Log out an admin user."""
    session.clear()

def admin_required(f):
    """Decorator to require admin authentication for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication checks in test environment if configured
        is_testing = current_app.config.get('TESTING', False)
        
        if is_testing and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
            return f(*args, **kwargs)
            
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login', next=request.url))
        
        # Check if the session has expired
        if 'admin_login_time' in session:
            login_time = datetime.fromisoformat(session['admin_login_time'])
            if datetime.now() - login_time > timedelta(hours=2):
                session.clear()
                return redirect(url_for('admin.login', next=request.url, reason='expired'))
        
        # Check if the IP address has changed (potential session hijacking)
        # Skip this check in testing environments
        if not is_testing and session.get('admin_ip') != request.remote_addr:
            session.clear()
            return redirect(url_for('admin.login', next=request.url, reason='ip_changed'))
        
        return f(*args, **kwargs)
    return decorated_function

def api_key_required(f):
    """Decorator to require API key authentication for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication checks in test environment if configured
        is_testing = current_app.config.get('TESTING', False)
        
        if is_testing and current_app.config.get('SKIP_AUTH_IN_TESTS', False):
            return f(*args, **kwargs)
        
        # Check for API key in headers
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({"error": "API key required"}), 401
        
        # Validate API key
        expected_api_key = current_app.config.get('API_KEY')
        if not expected_api_key:
            current_app.logger.error("API_KEY not configured")
            return jsonify({"error": "API authentication not configured"}), 500
        
        if api_key != expected_api_key:
            current_app.logger.warning(f"Invalid API key attempt from {request.remote_addr}")
            return jsonify({"error": "Invalid API key"}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def generate_csrf():
    """Generate a CSRF token for forms."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def validate_csrf_token(token):
    """Validate a CSRF token."""
    if not token or token != session.get('_csrf_token'):
        abort(403)
    return True
