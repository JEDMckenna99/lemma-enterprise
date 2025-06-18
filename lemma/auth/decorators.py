"""
Auth decorators for Lemma Enterprise.
Provides route protection decorators for enhanced security.
"""
from functools import wraps
from datetime import datetime, timedelta
from flask import current_app, session, redirect, url_for, request

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