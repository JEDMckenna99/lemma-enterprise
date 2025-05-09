"""
Tests for the credential service module.
"""
import pytest
import os
import json
import shutil
from datetime import datetime, timedelta

# Test configuration
TEST_STORAGE_DIR = '.lemma_test'

@pytest.fixture
def app():
    """Create a test Flask application."""
    # Import here to avoid circular imports
    from lemma import create_app
    
    # Create test app with test configuration
    app = create_app({
        'TESTING': True,
        'STORAGE_DIR': TEST_STORAGE_DIR,
        'SECRET_KEY': 'test_secret_key',
        'ADMIN_USERNAME': 'test_admin',
        'ADMIN_PASSWORD': 'test_password',
        'API_KEY': 'test_api_key'
    })
    
    # Set up test context
    with app.app_context():
        yield app
    
    # Clean up test data
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)

@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()

@pytest.fixture
def credential_service(app):
    """Get the credential service instance."""
    from lemma.core.credential_service import get_credential_service
    with app.app_context():
        return get_credential_service()

def test_issue_credential(credential_service):
    """Test issuing a credential."""
    # Issue a credential
    user_id = 'test_user'
    credential = credential_service.issue_credential(user_id)
    
    # Verify the credential structure
    assert credential['credentialSubject']['isHuman'] is True
    assert credential['credentialSubject']['id'] == f'did:user:{user_id}'
    assert credential['credentialSubject']['verifiedBy'] == 'admin'
    assert 'proof' in credential
    assert credential['proof']['type'] == 'Ed25519Signature2020'
    
    # Verify the credential was stored in the registry
    assert user_id in credential_service.users['users']
    assert credential_service.users['users'][user_id]['verification_status'] == 'verified'
    
    # Verify the credential ID is in the registry
    credential_id = credential['id']
    assert credential_id in credential_service.registry['credentials']

def test_verify_credential(credential_service):
    """Test verifying a credential."""
    # Issue a credential
    user_id = 'test_verify_user'
    credential = credential_service.issue_credential(user_id)
    
    # Verify the credential
    verification_result = credential_service.verify_credential(credential)
    
    # Check verification result
    assert verification_result['valid'] is True
    assert verification_result['issuer'] == credential['issuer']
    assert verification_result['subject'] == credential['credentialSubject']['id']

def test_revoke_credential(credential_service):
    """Test revoking a credential."""
    # Issue a credential
    user_id = 'test_revoke_user'
    credential = credential_service.issue_credential(user_id)
    
    # Get the credential ID
    credential_id = credential['id']
    
    # Revoke the credential
    result = credential_service.revoke_credential(credential_id)
    
    # Check revocation result
    assert result is True
    
    # Verify the credential is marked as revoked
    assert credential_service.registry['credentials'][credential_id]['revoked'] is True
    
    # Verify the credential is no longer valid
    verification_result = credential_service.verify_credential(credential)
    assert verification_result['valid'] is False
    assert 'revoked' in verification_result['reason'].lower()

def test_create_presentation(credential_service):
    """Test creating a presentation."""
    # Issue a credential
    user_id = 'test_presentation_user'
    credential = credential_service.issue_credential(user_id)
    
    # Create a challenge
    challenge = 'test_challenge'
    
    # Create a presentation
    presentation = credential_service.create_presentation(credential, challenge)
    
    # Verify presentation structure
    assert presentation['type'] == ['VerifiablePresentation']
    assert presentation['holder'] == credential['credentialSubject']['id']
    assert presentation['verifiableCredential'][0]['id'] == credential['id']
    assert presentation['challenge'] == challenge
    assert 'proof' in presentation
    assert presentation['proof']['challenge'] == challenge

def test_verify_presentation(credential_service):
    """Test verifying a presentation."""
    # Issue a credential
    user_id = 'test_verify_presentation_user'
    credential = credential_service.issue_credential(user_id)
    
    # Create a challenge
    challenge = 'test_challenge'
    
    # Create a presentation
    presentation = credential_service.create_presentation(credential, challenge)
    
    # Verify the presentation
    verification_result = credential_service.verify_presentation(presentation, challenge)
    
    # Check verification result
    assert verification_result['valid'] is True
    assert verification_result['holder'] == credential['credentialSubject']['id']
    assert verification_result['challenge'] == challenge

def test_expired_credential(credential_service):
    """Test handling of expired credentials."""
    # Issue a credential
    user_id = 'test_expired_user'
    credential = credential_service.issue_credential(user_id)
    
    # Modify expiration date to make it expired
    credential_id = credential['id']
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    credential['expirationDate'] = yesterday
    
    # Update registry with expired date
    credential_service.registry['credentials'][credential_id]['expires_at'] = yesterday
    credential_service._save_registry()
    
    # Verify the credential is expired
    verification_result = credential_service.verify_credential(credential)
    assert verification_result['valid'] is False
    assert 'expired' in verification_result['reason'].lower()

def test_tampered_credential(credential_service):
    """Test handling of tampered credentials."""
    # Issue a credential
    user_id = 'test_tampered_user'
    credential = credential_service.issue_credential(user_id)
    
    # Save the proof
    proof = credential.pop('proof')
    
    # Tamper with the credential
    credential['credentialSubject']['isHuman'] = False
    
    # Restore the proof (which is now invalid for the tampered credential)
    credential['proof'] = proof
    
    # Verify the credential is detected as tampered
    verification_result = credential_service.verify_credential(credential)
    assert verification_result['valid'] is False
    assert 'invalid signature' in verification_result['reason'].lower()

def test_challenge_mismatch(credential_service):
    """Test handling of challenge mismatch in presentations."""
    # Issue a credential
    user_id = 'test_challenge_user'
    credential = credential_service.issue_credential(user_id)
    
    # Create a presentation with one challenge
    challenge1 = 'original_challenge'
    presentation = credential_service.create_presentation(credential, challenge1)
    
    # Verify with a different challenge
    challenge2 = 'different_challenge'
    verification_result = credential_service.verify_presentation(presentation, challenge2)
    
    # Check verification result
    assert verification_result['valid'] is False
    assert 'challenge mismatch' in verification_result['reason'].lower()
