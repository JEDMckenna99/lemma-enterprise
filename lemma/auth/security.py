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
from typing import List, Set

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
        # SECURITY: Regenerate session ID to prevent session fixation
        session.regenerate_id()
        
        session['admin_logged_in'] = True
        session['admin_username'] = username
        session['admin_login_time'] = datetime.now().isoformat()
        session['admin_ip'] = request.remote_addr
        session['session_token'] = secrets.token_hex(32)  # Additional session validation
        
        # Log the admin login for security audit trail
        current_app.logger.info(f"Admin login: {username} from {request.remote_addr} at {datetime.now().isoformat()}")
        return True
    return False

def logout_admin():
    """Log out an admin user."""
    # SECURITY: Clear all session data and regenerate session ID
    admin_username = session.get('admin_username', 'unknown')
    session.clear()
    session.regenerate_id()
    
    # Log the logout for security audit trail  
    current_app.logger.info(f"Admin logout: {admin_username} from {request.remote_addr} at {datetime.now().isoformat()}")

def admin_required(f):
    """Decorator to require admin authentication for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # SECURITY: Never skip authentication in production
        if current_app.config.get('ENV') == 'production':
            # Force authentication check in production - no bypasses allowed
            if not session.get('admin_logged_in'):
                return redirect(url_for('admin.login', next=request.url))
        else:
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
        # SECURITY: Never skip authentication in production
        if current_app.config.get('ENV') == 'production':
            # Force API key check in production - no bypasses allowed
            api_key = request.headers.get('X-API-Key')
            if not api_key:
                return jsonify({"error": "API key required"}), 401
            # Validate API key against configured key
            expected_api_key = current_app.config.get('API_KEY')
            if not expected_api_key or api_key != expected_api_key:
                return jsonify({"error": "Invalid API key"}), 401
        else:
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

# ROLE-BASED ACCESS CONTROL (RBAC) SYSTEM
class Permission:
    """Define system permissions for RBAC."""
    VERIFY = 'verify'           # Verify credentials
    ISSUE = 'issue'             # Issue new credentials
    REVOKE = 'revoke'           # Revoke credentials
    ADMIN = 'admin'             # Administrative access
    BILLING = 'billing'         # Billing and payment access
    READONLY = 'readonly'       # Read-only access
    AUDIT = 'audit'             # Audit log access
    CONFIG = 'config'           # Configuration management
    OPRF = 'oprf'              # OPRF service access
    SHIELD = 'shield'           # Shield widget access

class Role:
    """Define system roles with associated permissions."""
    
    # Role definitions with their permissions
    ROLES = {
        'super_admin': {
            'permissions': [Permission.VERIFY, Permission.ISSUE, Permission.REVOKE, 
                          Permission.ADMIN, Permission.BILLING, Permission.AUDIT, 
                          Permission.CONFIG, Permission.OPRF, Permission.SHIELD],
            'description': 'Full system access'
        },
        'admin': {
            'permissions': [Permission.VERIFY, Permission.ISSUE, Permission.REVOKE, 
                          Permission.ADMIN, Permission.AUDIT, Permission.SHIELD],
            'description': 'Administrative access without billing'
        },
        'issuer': {
            'permissions': [Permission.VERIFY, Permission.ISSUE, Permission.SHIELD],
            'description': 'Can issue and verify credentials'
        },
        'verifier': {
            'permissions': [Permission.VERIFY, Permission.SHIELD],
            'description': 'Can only verify credentials'
        },
        'billing_admin': {
            'permissions': [Permission.BILLING, Permission.READONLY, Permission.AUDIT],
            'description': 'Billing and financial access'
        },
        'auditor': {
            'permissions': [Permission.READONLY, Permission.AUDIT],
            'description': 'Read-only access for auditing'
        },
        'api_client': {
            'permissions': [Permission.VERIFY, Permission.OPRF],
            'description': 'API client access for verification'
        }
    }
    
    @classmethod
    def get_permissions(cls, role_name: str) -> List[str]:
        """Get permissions for a role."""
        role = cls.ROLES.get(role_name, {})
        return role.get('permissions', [])

    @classmethod
    def validate_role(cls, role_name: str) -> bool:
        """Validate if a role exists."""
        return role_name in cls.ROLES

    @classmethod
    def get_role_description(cls, role_name: str) -> str:
        """Get role description."""
        role = cls.ROLES.get(role_name, {})
        return role.get('description', 'Unknown role')

class UserPermissions:
    """Manage user permissions and roles."""
    
    def __init__(self, user_id: str, roles: List[str] = None, api_key_scopes: List[str] = None):
        self.user_id = user_id
        self.roles = roles or []
        self.api_key_scopes = api_key_scopes or []
        self._permissions_cache = None
    
    @property
    def permissions(self) -> Set[str]:
        """Get all permissions for this user."""
        if self._permissions_cache is None:
            perms = set()
            
            # Add permissions from roles
            for role in self.roles:
                perms.update(Role.get_permissions(role))
            
            # Add permissions from API key scopes
            perms.update(self.api_key_scopes)
            
            self._permissions_cache = perms
       
        return self._permissions_cache
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions
    
    def has_any_permission(self, permissions: List[str]) -> bool:
        """Check if user has any of the specified permissions."""
        return bool(set(permissions) & self.permissions)
    
    def has_all_permissions(self, permissions: List[str]) -> bool:
        """Check if user has all of the specified permissions."""
        return set(permissions).issubset(self.permissions)
    
    def add_role(self, role: str):
        """Add a role to the user."""
        if Role.validate_role(role) and role not in self.roles:
            self.roles.append(role)
            self._permissions_cache = None  # Clear cache
    
    def remove_role(self, role: str):
        """Remove a role from the user."""
        if role in self.roles:
            self.roles.remove(role)
            self._permissions_cache = None  # Clear cache

def get_current_user_permissions() -> UserPermissions:
    """Get permissions for the current user."""
    from flask import session, request, current_app
    
    # Check if user is logged in via session
    if session.get('admin_logged_in'):
        user_id = session.get('admin_user_id', 'admin')
        roles = session.get('admin_roles', ['admin'])
        return UserPermissions(user_id=user_id, roles=roles)
    
    # Check API key authentication
    api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not api_key:
        api_key = request.headers.get('X-API-Key')
    
    if api_key:
        # Get API key scopes from the API key manager
        try:
            from lemma.auth.api_key_manager import APIKeyManager
            api_manager = APIKeyManager()
            key_info = api_manager.validate_key(api_key)
            
            if key_info and key_info.get('valid'):
                scopes = key_info.get('scopes', [])
                return UserPermissions(
                    user_id=f"api_key_{key_info.get('key_id', 'unknown')}",
                    api_key_scopes=scopes
                )
        except Exception as e:
            logger.warning(f"Failed to validate API key for permissions: {e}")
    
    # Return empty permissions for unauthenticated users
    return UserPermissions(user_id='anonymous')

def require_permission(permission: str):
    """Decorator to require a specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_perms = get_current_user_permissions()
            
            if not user_perms.has_permission(permission):
                logger.warning(f"Permission denied: User {user_perms.user_id} lacks permission '{permission}'")
                return jsonify({
                    'error': 'Insufficient permissions',
                    'required_permission': permission,
                    'user_permissions': list(user_perms.permissions)
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_any_permission(*permissions):
    """Decorator to require any of the specified permissions."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_perms = get_current_user_permissions()
            
            if not user_perms.has_any_permission(list(permissions)):
                logger.warning(f"Permission denied: User {user_perms.user_id} lacks any of permissions {permissions}")
                return jsonify({
                    'error': 'Insufficient permissions',
                    'required_permissions': list(permissions),
                    'user_permissions': list(user_perms.permissions)
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_all_permissions(*permissions):
    """Decorator to require all of the specified permissions."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_perms = get_current_user_permissions()
            
            if not user_perms.has_all_permissions(list(permissions)):
                missing_perms = set(permissions) - user_perms.permissions
                logger.warning(f"Permission denied: User {user_perms.user_id} missing permissions {missing_perms}")
                return jsonify({
                    'error': 'Insufficient permissions',
                    'missing_permissions': list(missing_perms),
                    'user_permissions': list(user_perms.permissions)
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
