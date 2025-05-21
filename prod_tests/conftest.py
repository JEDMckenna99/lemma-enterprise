"""
Pytest configuration for Lemma Enterprise production readiness tests.
"""
import os
import time
import pytest
import hashlib
import requests
from datetime import datetime
from typing import Dict, Tuple, List, Any
import base64

# Production test configuration
PROD_TEST_STORAGE_DIR = '.lemma_prod_test'
DEFAULT_SERVER_URL = "http://localhost:5000"
DEFAULT_OPRF_SERVER_URL = "http://localhost:8080"

@pytest.fixture
def app():
    """Create a test Flask application."""
    # Import here to avoid circular imports
    from lemma import create_app
    
    # Create test app with production-like configuration
    test_app = create_app({
        'TESTING': True,
        'STORAGE_DIR': PROD_TEST_STORAGE_DIR,
        'SECRET_KEY': 'prod_test_secret_key',
        'ADMIN_USERNAME': 'prod_test_admin',
        'ADMIN_PASSWORD': 'prod_test_password',
        'API_KEY': os.environ.get('LEMMA_API_KEY', 'prod_test_api_key'),
        'SKIP_AUTH_IN_TESTS': True
    })
    
    # Set up test context
    with test_app.app_context():
        yield test_app

@pytest.fixture
def client(app):
    """Create a test client for production tests."""
    return app.test_client(use_cookies=True)

@pytest.fixture
def api_key():
    """Get API key for tests."""
    return os.environ.get('LEMMA_API_KEY', 'prod_test_api_key')

@pytest.fixture
def credential_service(app):
    """Get the credential service instance."""
    from lemma.core.credential_service import get_credential_service
    with app.app_context():
        return get_credential_service()

@pytest.fixture
def oprf_client():
    """Create an OPRF client for tests."""
    try:
        from lemma.core.cascaded_bloom import OPRFClient
        return OPRFClient(server_url=DEFAULT_OPRF_SERVER_URL)
    except ImportError:
        pytest.skip("OPRF client not available")

@pytest.fixture
def mock_oprf_client():
    """Create a mock OPRF client for tests when the real service is not available."""
    try:
        from lemma.core.cascaded_bloom import OPRFClient
        client = OPRFClient(server_url=DEFAULT_OPRF_SERVER_URL)
        
        # Force using mock implementation for testing
        client.using_mock = True
        
        # Mock public key retrieval
        client.public_key = "mock_public_key_for_testing"
        
        # Mock the evaluate method
        original_evaluate = client.evaluate
        def mock_evaluate(alpha):
            # Simulate OPRF evaluation with a hash
            return hashlib.sha256(alpha).digest()
        client.evaluate = mock_evaluate
        
        # Mock the get_evaluation method
        def mock_get_evaluation(credential_id):
            alpha, r = client.blind(credential_id)
            beta = client.evaluate(alpha)
            return client.unblind(beta, r)
        client.get_evaluation = mock_get_evaluation
        
        # Mock the generate_witness method
        def mock_generate_witness(credential_id, epoch):
            alpha, r = client.blind(credential_id)
            beta = client.evaluate(alpha)
            return {
                "epoch": epoch,
                "alpha": base64.b64encode(alpha).decode('utf-8'),
                "beta": base64.b64encode(beta).decode('utf-8'),
                "r": base64.b64encode(r).decode('utf-8'),
                "type": "oprf_witness"
            }
        client.generate_witness = mock_generate_witness
        
        # Mock the get_public_key method
        def mock_get_public_key():
            return client.public_key
        client.get_public_key = mock_get_public_key
        
        return client
    except ImportError:
        pytest.skip("OPRF client not available")

@pytest.fixture
def epoch():
    """Get the current epoch."""
    return datetime.now().strftime("%Y-%m-%d")

@pytest.fixture
def mock_stripe_verification():
    """Mock Stripe verification response."""
    return {
        "id": f"vs_{hashlib.md5(str(time.time()).encode()).hexdigest()}",
        "object": "identity.verification_session",
        "client_secret": "vs_client_secret_mock",
        "last_verification_report": {
            "id": f"vr_{hashlib.md5(str(time.time()).encode()).hexdigest()}",
            "verified_outputs": {
                "id_number": "123456789",
                "dob": "1990-01-01",
                "address": {
                    "line1": "123 Main St",
                    "city": "San Francisco",
                    "state": "CA",
                    "postal_code": "94105",
                    "country": "US"
                }
            }
        },
        "status": "verified",
        "type": "document",
        "url": "https://verify.stripe.com/mock_verification"
    }

@pytest.fixture
def generate_user_id():
    """Generate a unique user ID for testing."""
    return f"test_user_{int(time.time())}"

@pytest.fixture
def generate_credential(client, api_key, generate_user_id):
    """Generate a credential for a user."""
    def _generate(user_id=None):
        if user_id is None:
            user_id = generate_user_id
        
        response = client.post(
            '/api/issue-credential',
            json={'user_id': user_id},
            headers={'X-API-Key': api_key}
        )
        
        assert response.status_code == 200, f"Failed to issue credential: {response.data}"
        return response.json
    
    return _generate

@pytest.fixture
def generate_challenge(client):
    """Generate a challenge for presentation creation."""
    response = client.get('/api/generate-challenge')
    assert response.status_code == 200, f"Failed to generate challenge: {response.data}"
    return response.json['challenge']

@pytest.fixture
def create_presentation(client, generate_credential, generate_challenge):
    """Create a verifiable presentation."""
    def _create(credential=None, challenge=None):
        if credential is None:
            credential = generate_credential()['credential']
        
        if challenge is None:
            challenge = generate_challenge
        
        response = client.post(
            '/api/presentation',
            json={'credential': credential, 'challenge': challenge}
        )
        
        assert response.status_code == 200, f"Failed to create presentation: {response.data}"
        return response.json
    
    return _create

@pytest.fixture
def verify_presentation(client):
    """Verify a presentation."""
    def _verify(presentation, challenge):
        response = client.post(
            '/api/verify-presentation',
            json={'presentation': presentation, 'challenge': challenge}
        )
        
        return response
    
    return _verify

@pytest.fixture
def check_file_size(app):
    """Check the size of a file."""
    def _check(file_path, max_size_kb=1000):
        full_path = os.path.join(app.root_path, file_path)
        if not os.path.exists(full_path):
            return False, 0
        
        size_bytes = os.path.getsize(full_path)
        size_kb = size_bytes / 1024
        
        return size_kb <= max_size_kb, size_kb
    
    return _check

@pytest.fixture
def measure_execution_time():
    """Measure the execution time of a function."""
    def _measure(func, *args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        
        elapsed_time = end_time - start_time
        return result, elapsed_time
    
    return _measure 