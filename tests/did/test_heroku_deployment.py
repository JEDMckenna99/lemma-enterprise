#!/usr/bin/env python3
"""
Test script for Lemma Heroku deployment

Tests the verification flow end-to-end on the deployed Heroku instance:
1. Issues a credential to a test user
2. Retrieves the credential
3. Verifies the credential
4. Creates a presentation with the credential
5. Verifies the presentation
"""
import os
import sys
import json
import uuid
import requests
from urllib.parse import urljoin
import time

# Base URL for the Heroku deployment
BASE_URL = os.environ.get('HEROKU_URL', 'https://your-lemma-app.herokuapp.com')

# API key for protected endpoints
API_KEY = os.environ.get('LEMMA_API_KEY', None)

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 50)
    print(f" {title}")
    print("=" * 50)

def test_health():
    """Test the API health endpoint."""
    print_header("Testing API Health")
    
    url = urljoin(BASE_URL, "/api/health")
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'ok':
                print("✅ API health check passed")
                return True
            else:
                print(f"❌ API returned unexpected data: {data}")
                return False
        else:
            print(f"❌ API health check failed with status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception during API health check: {e}")
        return False

def issue_test_credential():
    """Issue a credential to a test user."""
    print_header("Testing Credential Issuance")
    
    if not API_KEY:
        print("❌ No API key provided. Set LEMMA_API_KEY environment variable.")
        return None
    
    # Generate a test user ID
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    print(f"Generated test user ID: {user_id}")
    
    # Issue a credential via the API
    url = urljoin(BASE_URL, "/api/issue-credential")
    headers = {"X-API-Key": API_KEY}
    data = {"user_id": user_id}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            credential = response.json()
            print("✅ Credential issued successfully")
            print(f"Credential ID: {credential.get('id')}")
            return user_id, credential
        else:
            print(f"❌ Credential issuance failed: {response.status_code}")
            print(response.text)
            return None, None
    except Exception as e:
        print(f"❌ Exception during credential issuance: {e}")
        return None, None

def get_credential(user_id):
    """Get a credential for a user."""
    print_header(f"Getting Credential for User {user_id}")
    
    if not user_id:
        print("❌ No user ID provided")
        return None
    
    url = urljoin(BASE_URL, f"/api/credential/{user_id}")
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            credential = response.json()
            print("✅ Credential retrieved successfully")
            return credential
        else:
            print(f"❌ Failed to retrieve credential: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ Exception during credential retrieval: {e}")
        return None

def verify_credential(credential):
    """Verify a credential."""
    print_header("Verifying Credential")
    
    if not credential:
        print("❌ No credential provided")
        return False
    
    url = urljoin(BASE_URL, "/api/verify")
    
    try:
        response = requests.post(url, json=credential)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('valid'):
                print("✅ Credential verified successfully")
                print(f"Issuer: {result.get('issuer')}")
                print(f"Subject: {result.get('subject')}")
                return True
            else:
                print(f"❌ Credential verification failed: {result.get('reason')}")
                return False
        else:
            print(f"❌ Verification request failed: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False

def create_presentation(credential):
    """Create a presentation from a credential."""
    print_header("Creating Presentation")
    
    if not credential:
        print("❌ No credential provided")
        return None
    
    # First get a challenge
    challenge_url = urljoin(BASE_URL, "/api/generate-challenge")
    
    try:
        challenge_response = requests.get(challenge_url)
        if challenge_response.status_code != 200:
            print(f"❌ Failed to get challenge: {challenge_response.status_code}")
            return None
        
        challenge = challenge_response.json().get('challenge')
        
        # Create presentation
        presentation_url = urljoin(BASE_URL, "/api/presentation")
        presentation_data = {
            "credential": credential,
            "challenge": challenge
        }
        
        presentation_response = requests.post(presentation_url, json=presentation_data)
        
        if presentation_response.status_code == 200:
            presentation = presentation_response.json()
            print("✅ Presentation created successfully")
            return presentation, challenge
        else:
            print(f"❌ Failed to create presentation: {presentation_response.status_code}")
            print(presentation_response.text)
            return None, None
    except Exception as e:
        print(f"❌ Exception during presentation creation: {e}")
        return None, None

def verify_presentation(presentation, challenge):
    """Verify a presentation."""
    print_header("Verifying Presentation")
    
    if not presentation or not challenge:
        print("❌ No presentation or challenge provided")
        return False
    
    url = urljoin(BASE_URL, "/api/verify-presentation")
    data = {
        "presentation": presentation,
        "challenge": challenge
    }
    
    try:
        response = requests.post(url, json=data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('valid'):
                print("✅ Presentation verified successfully")
                return True
            else:
                print(f"❌ Presentation verification failed: {result.get('reason')}")
                return False
        else:
            print(f"❌ Verification request failed: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False

def test_did_values(credential):
    """Check DID values in the credential."""
    print_header("Checking DID Values")
    
    if not credential:
        print("❌ No credential provided")
        return False
    
    # Check issuer DID
    issuer = credential.get('issuer')
    if not issuer or not issuer.startswith('did:'):
        print(f"❌ Invalid issuer DID: {issuer}")
        return False
    
    print(f"✅ Issuer DID: {issuer}")
    
    # Check subject DID
    subject = credential.get('credentialSubject', {}).get('id')
    if not subject or not subject.startswith('did:'):
        print(f"❌ Invalid subject DID: {subject}")
        return False
    
    print(f"✅ Subject DID: {subject}")
    
    # Check verification method in proof
    proof = credential.get('proof', {})
    verification_method = proof.get('verificationMethod')
    if not verification_method or not verification_method.startswith(issuer):
        print(f"❌ Invalid verification method: {verification_method}")
        return False
    
    print(f"✅ Verification method: {verification_method}")
    
    return True

def run_tests():
    """Run all tests."""
    # Step 1: Check API health
    if not test_health():
        print("❌ API health check failed, aborting tests.")
        return False
    
    # Step 2: Issue credential
    user_id, credential = issue_test_credential()
    if not user_id or not credential:
        # Try to get an existing credential
        test_user_id = os.environ.get('TEST_USER_ID')
        if test_user_id:
            print(f"🔄 Using existing test user ID: {test_user_id}")
            user_id = test_user_id
            credential = get_credential(user_id)
    
    if not credential:
        print("❌ Could not get a credential, aborting tests.")
        return False
    
    # Step 3: Verify credential
    if not verify_credential(credential):
        print("❌ Credential verification failed, aborting tests.")
        return False
    
    # Step 4: Check DID values
    if not test_did_values(credential):
        print("❌ DID values check failed, aborting tests.")
        return False
    
    # Step 5: Create presentation
    presentation, challenge = create_presentation(credential)
    if not presentation or not challenge:
        print("❌ Presentation creation failed, aborting tests.")
        return False
    
    # Step 6: Verify presentation
    if not verify_presentation(presentation, challenge):
        print("❌ Presentation verification failed, aborting tests.")
        return False
    
    print("\n✅ All tests passed successfully!")
    return True

if __name__ == "__main__":
    # Allow base URL to be provided as command line argument
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1]
    
    print(f"Testing Lemma deployment at: {BASE_URL}")
    
    if run_tests():
        sys.exit(0)
    else:
        sys.exit(1) 