"""
Pytest configuration and fixtures for Lemma Human Verification System tests.
"""
import os
import pytest
import tempfile
import json
from typing import Dict, Any, Generator
from flask import Flask
from flask.testing import FlaskClient

# Add the project root to the path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lemma import create_app
from lemma.core.credential_service import get_credential_service


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create a test Flask application."""
    # Create a temporary directory for test storage
    temp_dir = tempfile.mkdtemp()
    
    # Test configuration
    test_config = {
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-for-testing-only',
        'WTF_CSRF_ENABLED': True,
        'WTF_CSRF_TIME_LIMIT': None,  # Disable CSRF time limit for tests
        'STORAGE_DIR': temp_dir,
        'API_KEY': 'test-api-key',
        'ADMIN_USER': 'test_admin',
        'ADMIN_PASS': 'test_password',
        'DID': 'did:lemma:test',
        'SKIP_AUTH_IN_TESTS': False,  # We want to test auth
        'SKIP_API_KEY_CHECK': False,  # We want to test API keys
    }
    
    app = create_app(test_config)
    
    with app.app_context():
        yield app
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def runner(app: Flask):
    """Create a test runner for the Flask application."""
    return app.test_cli_runner()


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Provide valid API key headers for testing."""
    return {'X-API-Key': 'test-api-key'}


@pytest.fixture
def sample_credential() -> Dict[str, Any]:
    """Provide a sample credential for testing."""
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://lemmanetwork.org/contexts/lemma/v1"
        ],
        "id": "vc_test_credential_123",
        "type": ["VerifiableCredential", "LemmaCredential", "HumanCredential"],
        "issuer": "did:lemma:test",
        "issuanceDate": "2024-01-01T00:00:00Z",
        "expirationDate": "2025-01-01T00:00:00Z",
        "credentialSubject": {
            "id": "did:user:test_user_123",
            "type": "Person",
            "isHuman": True,
            "verifiedBy": "admin"
        },
        "proof": {
            "type": "Ed25519Signature2020",
            "created": "2024-01-01T00:00:00Z",
            "verificationMethod": "did:lemma:test#keys-1",
            "proofPurpose": "assertionMethod",
            "jws": "test_signature_base64"
        }
    }


@pytest.fixture
def sample_presentation(sample_credential: Dict[str, Any]) -> Dict[str, Any]:
    """Provide a sample presentation for testing."""
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://lemmanetwork.org/contexts/lemma/v1"
        ],
        "id": "vp_test_presentation_123",
        "type": ["VerifiablePresentation"],
        "holder": "did:user:test_user_123",
        "verifiableCredential": [sample_credential],
        "created": "2024-01-01T00:00:00Z",
        "challenge": "test_challenge_12345",
        "proof": {
            "type": "Ed25519Signature2020",
            "created": "2024-01-01T00:00:00Z",
            "verificationMethod": "did:lemma:test#keys-1",
            "proofPurpose": "authentication",
            "challenge": "test_challenge_12345",
            "jws": "test_presentation_signature_base64"
        }
    }


@pytest.fixture
def admin_session(client: FlaskClient) -> Dict[str, Any]:
    """Create an authenticated admin session."""
    # Login as admin
    response = client.post('/admin/login', data={
        'username': 'test_admin',
        'password': 'test_password'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    return {'session': client.session}


@pytest.fixture
def csrf_token(client: FlaskClient) -> str:
    """Get a valid CSRF token for testing."""
    response = client.get('/api/generate-csrf')
    assert response.status_code == 200
    return response.json['csrf_token'] 