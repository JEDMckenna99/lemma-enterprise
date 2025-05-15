#!/usr/bin/env python3
"""
Credential Test Script for Lemma

Tests the credential issuance and verification flow for the Lemma system.
"""
import sys
import json
import requests
import uuid
import re
from urllib.parse import urljoin

# Heroku URL
HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def get_health_check():
    """Check if the API is healthy."""
    print_header("API Health Check")
    
    url = urljoin(HEROKU_URL, "/api/health")
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API responded with: {data}")
            return True
        else:
            print(f"❌ API health check failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during API health check: {e}")
        return False

def get_credential(user_id="test-user"):
    """Try to get a credential for a user."""
    print_header(f"Getting Credential for User: {user_id}")
    
    url = urljoin(HEROKU_URL, f"/api/credential/{user_id}")
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            credential = response.json()
            print("✅ Successfully retrieved credential")
            
            # Check DID values in credential
            issuer = credential.get('issuer')
            subject = credential.get('credentialSubject', {}).get('id')
            
            print(f"Issuer DID: {issuer}")
            print(f"Subject DID: {subject}")
            
            # Check if credential has proper structure
            if '@context' in credential and 'id' in credential and 'type' in credential:
                print("✅ Credential has proper W3C VC structure")
            else:
                print("❌ Credential is missing required W3C VC fields")
            
            # Check if credential has a proof
            if 'proof' in credential:
                print("✅ Credential has a proof section")
                print(f"Proof type: {credential['proof'].get('type')}")
                print(f"Verification method: {credential['proof'].get('verificationMethod')}")
            else:
                print("❌ Credential is missing proof section")
            
            return credential
        else:
            print(f"❌ Failed to retrieve credential: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception during credential retrieval: {e}")
        return None

def verify_credential(credential):
    """Verify a credential."""
    print_header("Verifying Credential")
    
    if credential is None:
        print("❌ No credential to verify")
        return False
    
    url = urljoin(HEROKU_URL, "/api/verify")
    
    try:
        print("Sending credential for verification...")
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
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False

def test_protected_access():
    """Test accessing the protected page."""
    print_header("Testing Protected Page Access")
    
    url = urljoin(HEROKU_URL, "/protected")
    
    try:
        # Use a session to maintain cookies
        session = requests.Session()
        
        # First, get a credential
        credential = get_credential()
        if not credential:
            print("❌ Cannot test protected access without a credential")
            return False
        
        # Create a verification session
        verify_human_url = urljoin(HEROKU_URL, "/api/verify-human")
        verify_data = {"credential": credential}
        verify_response = session.post(verify_human_url, json=verify_data)
        
        if verify_response.status_code != 200:
            print(f"❌ Failed to create verification session: {verify_response.status_code}")
            print(f"Response: {verify_response.text}")
            return False
        
        print("✅ Successfully created verification session")
        
        # Now try to access the protected page
        protected_response = session.get(url)
        
        if protected_response.status_code == 200:
            print("✅ Successfully accessed protected page")
            
            # Check if the page contains protected content
            if "protected" in protected_response.text.lower() and "content" in protected_response.text.lower():
                print("✅ Protected content found on the page")
                return True
            else:
                print("❌ Protected content not found on the page")
                return False
        else:
            print(f"❌ Failed to access protected page: {protected_response.status_code}")
            print(f"Response: {protected_response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during protected page test: {e}")
        return False

def main():
    """Run the credential tests."""
    if len(sys.argv) > 1:
        global HEROKU_URL
        HEROKU_URL = sys.argv[1]
    
    print(f"Testing Lemma credentials at: {HEROKU_URL}")
    
    # Step 1: Health check
    if not get_health_check():
        print("❌ API health check failed, proceeding with caution...")
    
    # Step 2: Get a credential
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    credential = get_credential(user_id)
    
    if not credential:
        print("❌ Failed to get a fresh credential, trying with default test user...")
        credential = get_credential()
    
    if not credential:
        print("❌ Unable to get any credential, cannot continue testing")
        return 1
    
    # Step 3: Verify the credential
    verify_credential(credential)
    
    # Step 4: Test protected access
    test_protected_access()
    
    print_header("Test Summary")
    print("Completed credential testing for Lemma")
    print(f"URL tested: {HEROKU_URL}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 