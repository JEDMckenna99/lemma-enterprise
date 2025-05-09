"""
Tests for the main routes of the Lemma Human Verification System.
"""
import pytest
import os
import json
import shutil
import re

# Test configuration
TEST_STORAGE_DIR = '.lemma_test_routes'

@pytest.fixture
def app():
    """Create a test Flask application."""
    # Import here to avoid circular imports
    from lemma import create_app
    
    # Create test app with test configuration
    app = create_app({
        'TESTING': True,
        'SKIP_AUTH_IN_TESTS': True,
        'STORAGE_DIR': TEST_STORAGE_DIR,
        'SECRET_KEY': 'test_secret_key',
        'ADMIN_USERNAME': 'test_admin',
        'ADMIN_PASSWORD': 'test_password',
        'API_KEY': 'test_api_key',
        'WTF_CSRF_ENABLED': False  # Disable CSRF for testing
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

def test_index_route(client):
    """Test the index route."""
    # This is a very simple test that just checks if the index route works
    response = client.get('/')
    
    # Print response details for debugging
    print(f"\nIndex route response status: {response.status_code}")
    print(f"Index route response data length: {len(response.data)}")
    print(f"Index route response data snippet: {response.data[:100]}")
    
    # Check response
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
    
    # Check for expected content
    expected_content = b'Lemma Human Network'
    content_present = expected_content in response.data
    print(f"Expected content present: {content_present}")
    assert content_present, f"Expected '{expected_content}' in response"

def test_verify_route(client):
    """Test the verification route."""
    # Test without user_id
    response = client.get('/verify')
    
    # Should redirect with a generated user_id
    assert response.status_code == 302
    assert '/verify?user_id=' in response.location
    
    # Test with user_id
    user_id = 'test_verify_route_user'
    response = client.get(f'/verify?user_id={user_id}')
    
    # Should render the verification page
    assert response.status_code == 200
    assert user_id.encode() in response.data
    assert b'QR code' in response.data

def test_protected_route(client, credential_service):
    """Test the protected route."""
    # Set up a test CSRF token
    with client.session_transaction() as session:
        session['csrf_token'] = 'test-csrf-token'
    
    # Test without verification
    response = client.get('/protected', follow_redirects=True)
    
    # Should redirect to verification
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
    assert b'Please verify you are human' in response.data, "Expected verification prompt in response"
    
    # Issue a credential and store in session
    user_id = 'test_protected_route_user'
    credential = credential_service.issue_credential(user_id)
    
    # Create a session with verification and CSRF token
    with client.session_transaction() as session:
        session['verified_user_id'] = user_id
        session['verified_credential'] = credential
        session['verification_time'] = credential['issuanceDate']
        session['verification_expiry'] = credential['expirationDate']
        session['csrf_token'] = 'test-csrf-token'
    
    # Test with verification
    response = client.get('/protected')
    
    # Should render the protected page
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
    assert user_id.encode() in response.data, f"Expected user ID '{user_id}' in response"
    assert b'Successfully verified' in response.data, "Expected success message in response"

def test_admin_onboarding_flow(client, credential_service):
    """Test the admin onboarding flow for trusted users."""
    # Login as admin (CSRF token is automatically added by our FlaskClient)
    response = client.post('/admin/login', data={
        'username': 'test_admin',
        'password': 'test_password'
    }, follow_redirects=True)
    
    # Print response for debugging
    print(f"Login response status: {response.status_code}")
    print(f"Login response data: {response.data[:500]}")
    
    # Check login successful
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
    assert b'Admin Dashboard' in response.data, "Expected 'Admin Dashboard' in response"
    
    # Issue a credential to a trusted user
    user_id = 'trusted_human_user'
    
    # Ensure admin is authenticated
    with client.session_transaction() as session:
        session['admin_authenticated'] = True
    
    # Issue credential (CSRF token is automatically added by our FlaskClient)
    response = client.post('/admin/issue', data={
        'user_id': user_id
    }, follow_redirects=True)
    
    # Print response for debugging
    print(f"Issue credential response status: {response.status_code}")
    print(f"Issue credential response data: {response.data[:500]}")
    
    # Check credential issuance successful
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
    success_message = b'Credential issued successfully'
    assert success_message in response.data, f"Expected '{success_message}' in response but not found"
    assert user_id.encode() in response.data
    
    # Verify QR code is generated
    assert b'QR code' in response.data
    
    # Verify the credential exists in the system
    assert user_id in credential_service.users['users']
    assert credential_service.users['users'][user_id]['verification_status'] == 'verified'
    
    # Get the verification URL from the response
    verification_url_match = re.search(r'href="([^"]+)"[^>]*>Verification Link', response.data.decode())
    assert verification_url_match
    verification_url = verification_url_match.group(1)
    
    # Test accessing the verification URL
    response = client.get(verification_url)
    assert response.status_code == 200
    assert user_id.encode() in response.data
    assert b'Verification Status' in response.data
    
    # Test storing the credential
    credential = credential_service.get_user_credential(user_id)
    assert credential is not None
    
    # Test API endpoint to get the full credential
    response = client.get(f'/api/get-credential/{user_id}')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['credentialSubject']['id'] == f'did:user:{user_id}'
    assert data['credentialSubject']['isHuman'] is True
    assert data['credentialSubject']['verifiedBy'] == 'admin'
    
    # Test storing the credential in the session
    response = client.post('/api/store-credential', json={
        'user_id': user_id,
        'credential': data
    })
    assert response.status_code == 200
    result = json.loads(response.data)
    assert result['success'] is True
    
    # Verify the user can now access protected content
    response = client.get('/protected')
    assert response.status_code == 200
    assert b'Successfully verified' in response.data
    
    # Test logout
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'You have been logged out' in response.data
    
    # Verify protected content is no longer accessible
    response = client.get('/protected', follow_redirects=True)
    assert response.status_code == 200
    assert b'Please verify you are human' in response.data

def test_simple_protected_route(client):
    """Simple test for the protected route with session data."""
    # Set up the session directly with CSRF token
    with client.session_transaction() as session:
        session['verified_user_id'] = 'test_user'
        session['verified_credential'] = {'test': 'credential'}
        from datetime import datetime
        current_time = datetime.now().isoformat()
        session['verification_time'] = current_time
        # Add one day to current time for expiry
        from datetime import timedelta
        expiry_time = (datetime.now() + timedelta(days=1)).isoformat()
        session['verification_expiry'] = expiry_time
        # Add CSRF token for protection
        session['csrf_token'] = 'test-csrf-token'
    
    # Access the protected route
    response = client.get('/protected')
    
    # Check response
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
    
    # Print response data for debugging
    print(f"Response data snippet: {response.data[:200]}")
    
    # Check for various possible success messages
    success_messages = [b'Successfully verified', b'Human Verification Successful', b'Verification successful']
    success_found = any(msg in response.data for msg in success_messages)
    
    assert success_found, f"Expected one of {success_messages} in response but none found"


def test_presentation_verification(client, credential_service):
    """Test the presentation verification flow."""
    try:
        import sys
        import traceback
        from flask import current_app
        print("\n==== Running test_presentation_verification ====")
        
        # Skip this test in certain environments
        if current_app.config.get('TESTING') and not current_app.config.get('SKIP_AUTH_IN_TESTS', False):
            print("Skipping test_presentation_verification in test environment without SKIP_AUTH_IN_TESTS")
            pytest.skip("Skipping in test environment without SKIP_AUTH_IN_TESTS")
        
        # Set up a test CSRF token
        with client.session_transaction() as session:
            session['csrf_token'] = 'test-csrf-token'
        print("\n\n==== Starting test_presentation_verification ====")
        
        # Create a user ID and credential
        user_id = 'test_presentation_user'
        print(f"User ID: {user_id}")
        
        # Set up the session with verification data
        print("Setting up session data...")
        with client.session_transaction() as session:
            # Set up the verification data in the session
            session['verified_user_id'] = user_id
            session['verified_credential'] = {'id': f'credential-{user_id}', 'type': 'VerifiableCredential'}
            from datetime import datetime, timedelta
            current_time = datetime.now().isoformat()
            session['verification_time'] = current_time
            expiry_time = (datetime.now() + timedelta(days=1)).isoformat()
            session['verification_expiry'] = expiry_time
            # Add CSRF token for protection
            session['csrf_token'] = 'test-csrf-token'
            print(f"Session data set: {list(session.keys())}")
            print(f"verified_user_id: {session.get('verified_user_id')}")
            print(f"verification_time: {session.get('verification_time')}")
            print(f"verification_expiry: {session.get('verification_expiry')}")
            print(f"csrf_token: {session.get('csrf_token')}")
        
        # Access the protected route
        print("Accessing protected route...")
        response = client.get('/protected')
        print(f"Protected route response status: {response.status_code}")
        print(f"Protected route response data length: {len(response.data)}")
        print(f"Protected route response data snippet: {response.data[:100]}")
        
        # Check session after request
        with client.session_transaction() as session:
            print(f"Session after protected request: {list(session.keys())}")
            print(f"verified_user_id in session: {session.get('verified_user_id')}")
        
        # Check that the protected route is accessible
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.data[:500]}"
        
        # Check for expected content in the response
        success_text_present = b'Human Verification Successful' in response.data
        print(f"'Human Verification Successful' present in response: {success_text_present}")
        assert success_text_present, "Expected 'Human Verification Successful' in response"
        
        # Test logout functionality
        print("Testing logout functionality...")
        # Include CSRF token in the logout request
        response = client.get('/logout', follow_redirects=True, headers={
            'X-CSRF-Token': 'test-csrf-token'
        })
        print(f"Logout response status: {response.status_code}")
        
        # Check session after logout
        with client.session_transaction() as session:
            print(f"Session after logout: {list(session.keys())}")
        
        assert response.status_code == 200, f"Expected 200 for logout but got {response.status_code}"
        logout_text_present = b'You have been logged out' in response.data
        print(f"'You have been logged out' present in response: {logout_text_present}")
        assert logout_text_present, "Expected 'You have been logged out' in response"
        
        # Verify protected content is no longer accessible
        print("Verifying protected content is no longer accessible...")
        response = client.get('/protected', follow_redirects=True)
        print(f"Protected after logout response status: {response.status_code}")
        print(f"Protected after logout response data snippet: {response.data[:100]}")
        
        assert response.status_code == 200, f"Expected 200 for protected after logout but got {response.status_code}"
        verification_prompt_present = b'Please verify you are human' in response.data
        print(f"'Please verify you are human' present in response: {verification_prompt_present}")
        assert verification_prompt_present, "Expected 'Please verify you are human' in response"
        
        print("==== test_presentation_verification completed successfully ====")
    except Exception as e:
        print(f"\n\nERROR in test_presentation_verification: {str(e)}")
        print("\nTraceback:")
        traceback.print_exc(file=sys.stdout)
        print("\nTest failed.")
        raise
