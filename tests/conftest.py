"""
Pytest configuration for Lemma Enterprise tests.
"""
import pytest
import os
import shutil

# Test configuration
TEST_STORAGE_DIR = '.lemma_test'

@pytest.fixture
def app():
    """Create a test Flask application."""
    # Import here to avoid circular imports
    from lemma import create_app
    
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

@pytest.fixture
def client(app, csrf_token):
    """Create a test client with CSRF token."""
    # Create a test client with session support
    client = app.test_client(use_cookies=True)
    
    # Set up CSRF token in session for all requests
    with client.session_transaction() as session:
        session['_csrf_token'] = csrf_token
        session['csrf_token'] = csrf_token
    
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
