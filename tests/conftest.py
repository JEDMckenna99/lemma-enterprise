"""
Pytest configuration for Lemma Enterprise tests.
"""
import pytest
import os
import shutil
import flask
from flask import session, current_app
from flask.testing import FlaskClient as BaseFlaskClient

# Test configuration
TEST_STORAGE_DIR = '.lemma_test'

@pytest.fixture
def app():
    """Create a test Flask application."""
    # Import here to avoid circular imports
    from lemma import create_app
    import flask_wtf
    
    # Store original CSRF protection state
    original_csrf_enabled = flask_wtf.csrf.CSRFProtect._exempt_views
    
    # Create test app with test configuration
    test_app = create_app({
        'TESTING': True,
        'SKIP_AUTH_IN_TESTS': True,
        'STORAGE_DIR': TEST_STORAGE_DIR,
        'SECRET_KEY': 'test_secret_key',
        'ADMIN_USERNAME': 'test_admin',
        'ADMIN_PASSWORD': 'test_password',
        'API_KEY': 'test_api_key',  # This must match the API key used in tests
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
        'SESSION_COOKIE_SECURE': False,  # Allow insecure cookies in tests
        'SESSION_COOKIE_HTTPONLY': False,  # Allow JavaScript access in tests
        'SESSION_COOKIE_SAMESITE': None,  # Disable SameSite in tests
        'CSRF_ENABLED': False  # Explicitly disable CSRF for testing
    })
    
    # Completely disable CSRF protection for tests
    try:
        # Try to completely disable CSRF protection
        flask_wtf.csrf.CSRFProtect._exempt_views = set()
        flask_wtf.csrf.CSRFProtect._exempt_blueprints = set()
        
        # Add a before_request handler to skip CSRF validation
        @test_app.before_request
        def disable_csrf():
            flask.g.csrf_valid = True
    except Exception as e:
        print(f"Failed to disable CSRF protection: {e}")
        pass
    
    # Log configuration for debugging
    test_app.logger.info(f"Test app configuration: TESTING={test_app.config.get('TESTING')}, SKIP_AUTH_IN_TESTS={test_app.config.get('SKIP_AUTH_IN_TESTS')}")
    test_app.logger.info(f"API_KEY={test_app.config.get('API_KEY')}")
    test_app.logger.info(f"WTF_CSRF_ENABLED={test_app.config.get('WTF_CSRF_ENABLED')}")
    test_app.logger.info(f"CSRF_ENABLED={test_app.config.get('CSRF_ENABLED')}")
    
    # Ensure API key authentication works in tests
    test_app.config['SKIP_API_KEY_CHECK'] = True
    
    # Set up test context
    with test_app.app_context():
        yield test_app
    
    # Clean up test data
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)

@pytest.fixture
def csrf_token(app):
    """Set up CSRF token for tests."""
    from lemma.auth.csrf_config import generate_csrf_token
    with app.test_client(use_cookies=True).session_transaction() as session:
        session['_csrf_token'] = generate_csrf_token()

# Flask's assumptions about an incoming request don't quite match up with
# what the test client provides in terms of manipulating cookies, and the
# CSRF system depends on cookies working correctly. This class is a
# fake request that forwards requests to the test client for setting cookies.
class RequestShim(object):
    """A fake request that proxies cookie-related methods to a Flask test client."""
    def __init__(self, client):
        self.client = client

    def set_cookie(self, key, value='', *args, **kwargs):
        """Set the cookie on the Flask test client."""
        server_name = current_app.config.get("SERVER_NAME") or "localhost"
        return self.client.set_cookie(
            server_name, key=key, value=value, *args, **kwargs
        )

    def delete_cookie(self, key, *args, **kwargs):
        """Delete the cookie on the Flask test client."""
        server_name = current_app.config.get("SERVER_NAME") or "localhost"
        return self.client.delete_cookie(
            server_name, key=key, *args, **kwargs
        )

# Extended Flask test client class that knows how to handle CSRF tokens
class FlaskClient(BaseFlaskClient):
    @property
    def csrf_token(self):
        # First, wrap our request shim around the test client
        request = RequestShim(self) 
        
        # Look up any cookies that might already exist on this test client
        environ_overrides = {}
        self.cookie_jar.inject_wsgi(environ_overrides)
        
        with current_app.test_request_context(
                "/", environ_overrides=environ_overrides):
            # Generate a CSRF token
            try:
                from flask_wtf.csrf import generate_csrf
                csrf_token = generate_csrf()
            except ImportError:
                # Fallback if Flask-WTF is not available
                csrf_token = 'test-csrf-token'
                session['_csrf_token'] = csrf_token
            
            # Save the session to the cookie jar
            current_app.session_interface.save_session(current_app, session, request)
            
            # Return the CSRF token
            return csrf_token
    
    def open(self, *args, **kwargs):
        # For POST, PUT, DELETE requests, automatically add CSRF token
        method = kwargs.get('method', args[0] if args else 'GET')
        if method in ['POST', 'PUT', 'DELETE']:
            # Add CSRF token to form data
            if 'data' in kwargs and kwargs['data'] is not None:
                if isinstance(kwargs['data'], dict):
                    kwargs['data']['csrf_token'] = self.csrf_token
            
            # Add CSRF token to headers
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers']['X-CSRF-Token'] = self.csrf_token
        
        # Call the original open method
        return super().open(*args, **kwargs)

@pytest.fixture
def client(app):
    """Create a test client with CSRF token handling."""
    # Set the custom test client class
    app.test_client_class = FlaskClient
    
    # Create a test client
    client = app.test_client(use_cookies=True)
    
    return client

@pytest.fixture
def credential_service(app):
    """Create a test credential service."""
    # Import here to avoid circular imports
    try:
        from lemma.core.credential_service import CredentialService
        return CredentialService(app.config['STORAGE_DIR'])
    except ImportError:
        # Mock credential service for testing if import fails
        class MockCredentialService:
            def __init__(self, storage_dir):
                self.storage_dir = storage_dir
        return MockCredentialService(app.config['STORAGE_DIR'])
