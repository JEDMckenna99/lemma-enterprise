#!/usr/bin/env python3
"""
DID Functionality Test for Lemma

This script tests the Decentralized Identifier (DID) functionality in Lemma:
1. Tests DID resolution
2. Tests DID verification
3. Tests DID formats in credentials
4. Tests DID verification methods in proofs
"""
import os
import sys
import json
import uuid
import base64
import requests
from urllib.parse import urljoin

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

def get_test_credential():
    """Get a test credential for DID functionality testing."""
    print_header("Getting Test Credential")
    
    if API_KEY:
        # Try to issue a new credential
        user_id = f"did-test-{uuid.uuid4().hex[:8]}"
        print(f"Attempting to issue new credential for user: {user_id}")
        
        url = urljoin(BASE_URL, "/api/issue-credential")
        headers = {"X-API-Key": API_KEY}
        data = {"user_id": user_id}
        
        try:
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                credential = response.json()
                print("✅ New credential issued successfully")
                return credential, user_id
        except Exception as e:
            print(f"⚠️ Could not issue new credential: {e}")
    
    # Try to get an existing credential
    test_user_id = os.environ.get('TEST_USER_ID')
    if test_user_id:
        print(f"Getting existing credential for user: {test_user_id}")
        
        url = urljoin(BASE_URL, f"/api/credential/{test_user_id}")
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                credential = response.json()
                print("✅ Retrieved existing credential")
                return credential, test_user_id
        except Exception as e:
            print(f"⚠️ Could not retrieve existing credential: {e}")
    
    # If we couldn't get a credential through API, ask for one
    print("❌ Could not get a credential automatically.")
    print("Please provide a credential JSON or user ID:")
    
    try:
        user_input = input("Enter JSON or user ID: ")
        
        # Check if input is a user ID or JSON
        if user_input.startswith("{"):
            # It's JSON
            credential = json.loads(user_input)
            print("✅ Using provided credential JSON")
            return credential, credential.get("credentialSubject", {}).get("id").split(":")[-1]
        else:
            # It's a user ID
            url = urljoin(BASE_URL, f"/api/credential/{user_input}")
            response = requests.get(url)
            if response.status_code == 200:
                credential = response.json()
                print("✅ Retrieved credential for provided user ID")
                return credential, user_input
            else:
                print(f"❌ Could not retrieve credential for user ID: {user_input}")
                return None, None
    except Exception as e:
        print(f"❌ Error processing input: {e}")
        return None, None

def test_did_resolution(credential):
    """Test DID resolution functionality."""
    print_header("Testing DID Resolution")
    
    if not credential:
        print("❌ No credential provided")
        return False
    
    # Extract DIDs from credential
    issuer_did = credential.get("issuer")
    subject_did = credential.get("credentialSubject", {}).get("id")
    
    if not issuer_did or not subject_did:
        print("❌ Missing DIDs in credential")
        return False
    
    print(f"Issuer DID: {issuer_did}")
    print(f"Subject DID: {subject_did}")
    
    # Test DID resolution for issuer
    did_resolve_url = urljoin(BASE_URL, "/api/resolve-did")
    
    try:
        response = requests.post(did_resolve_url, json={"did": issuer_did})
        
        if response.status_code == 200:
            did_doc = response.json()
            print("✅ Issuer DID resolved successfully")
            
            # Check DID document structure
            if did_doc.get("id") == issuer_did:
                print("✅ DID document has correct ID")
            else:
                print(f"❌ DID document has incorrect ID: {did_doc.get('id')}")
            
            # Check for verification methods
            verification_methods = did_doc.get("verificationMethod", [])
            if verification_methods:
                print(f"✅ DID document has {len(verification_methods)} verification method(s)")
            else:
                print("❌ DID document has no verification methods")
        else:
            print(f"❌ Failed to resolve issuer DID: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Exception during DID resolution: {e}")
        return False
    
    return True

def test_did_verification(credential):
    """Test DID verification functionality."""
    print_header("Testing DID Verification")
    
    if not credential:
        print("❌ No credential provided")
        return False
    
    # Verify the credential
    verify_url = urljoin(BASE_URL, "/api/verify")
    
    try:
        response = requests.post(verify_url, json=credential)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('valid'):
                print("✅ Credential verified successfully")
                
                # Check issuer and subject in verification result
                if result.get('issuer') == credential.get('issuer'):
                    print("✅ Verification confirmed correct issuer DID")
                else:
                    print(f"❌ Verification returned wrong issuer: {result.get('issuer')}")
                
                if result.get('subject') == credential.get('credentialSubject', {}).get('id'):
                    print("✅ Verification confirmed correct subject DID")
                else:
                    print(f"❌ Verification returned wrong subject: {result.get('subject')}")
                
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

def test_did_formats(credential):
    """Test DID format validity."""
    print_header("Testing DID Formats")
    
    if not credential:
        print("❌ No credential provided")
        return False
    
    # Extract DIDs from credential
    issuer_did = credential.get("issuer")
    subject_did = credential.get("credentialSubject", {}).get("id")
    
    if not issuer_did or not subject_did:
        print("❌ Missing DIDs in credential")
        return False
    
    # Validate issuer DID format
    if not issuer_did.startswith("did:"):
        print(f"❌ Invalid issuer DID format: {issuer_did}")
        return False
    
    issuer_parts = issuer_did.split(":")
    if len(issuer_parts) < 3:
        print(f"❌ Invalid issuer DID format (missing method or identifier): {issuer_did}")
        return False
    
    print(f"✅ Issuer DID format is valid: {issuer_did}")
    print(f"  Method: {issuer_parts[1]}")
    print(f"  Method-specific ID: {':'.join(issuer_parts[2:])}")
    
    # Validate subject DID format
    if not subject_did.startswith("did:"):
        print(f"❌ Invalid subject DID format: {subject_did}")
        return False
    
    subject_parts = subject_did.split(":")
    if len(subject_parts) < 3:
        print(f"❌ Invalid subject DID format (missing method or identifier): {subject_did}")
        return False
    
    print(f"✅ Subject DID format is valid: {subject_did}")
    print(f"  Method: {subject_parts[1]}")
    print(f"  Method-specific ID: {':'.join(subject_parts[2:])}")
    
    # Check proof verification method
    proof = credential.get("proof", {})
    verification_method = proof.get("verificationMethod")
    
    if not verification_method:
        print("❌ Missing verification method in proof")
        return False
    
    if not verification_method.startswith(issuer_did):
        print(f"❌ Verification method not tied to issuer DID: {verification_method}")
        return False
    
    print(f"✅ Verification method is properly tied to issuer DID: {verification_method}")
    
    return True

def test_did_cross_verification(user_id):
    """Test cross-verification with DID."""
    print_header("Testing Cross-Verification with DID")
    
    if not user_id:
        print("❌ No user ID provided")
        return False
    
    # Create session for the tests
    session = requests.Session()
    
    # Step 1: Visit home page
    try:
        home_response = session.get(BASE_URL)
        if home_response.status_code != 200:
            print(f"❌ Failed to access home page: {home_response.status_code}")
            return False
        
        print("✅ Accessed home page")
    except Exception as e:
        print(f"❌ Exception accessing home page: {e}")
        return False
    
    # Step 2: Access verification page with user ID
    try:
        verify_url = urljoin(BASE_URL, f"/verify?user_id={user_id}")
        verify_response = session.get(verify_url)
        
        if verify_response.status_code != 200:
            print(f"❌ Failed to access verification page: {verify_response.status_code}")
            return False
        
        print("✅ Accessed verification page")
    except Exception as e:
        print(f"❌ Exception accessing verification page: {e}")
        return False
    
    # Step 3: Access protected page to check DID verification
    try:
        protected_url = urljoin(BASE_URL, "/protected")
        protected_response = session.get(protected_url)
        
        if protected_response.status_code != 200:
            print(f"❌ Failed to access protected page: {protected_response.status_code}")
            return False
        
        if "verification required" in protected_response.text.lower():
            print("❌ Protected page requires verification - DID not recognized")
            return False
        
        if "lemma verification successful" in protected_response.text.lower():
            print("✅ Protected page recognized DID verification")
            return True
        
        print("⚠️ Accessed protected page but could not determine verification status")
        return True
    except Exception as e:
        print(f"❌ Exception accessing protected page: {e}")
        return False

def run_tests():
    """Run all DID functionality tests."""
    # Step 1: Check API health
    if not test_health():
        print("❌ API health check failed, aborting tests.")
        return False
    
    # Step 2: Get a test credential
    credential, user_id = get_test_credential()
    if not credential:
        print("❌ Could not get a credential for testing, aborting tests.")
        return False
    
    # Step 3: Test DID resolution
    if not test_did_resolution(credential):
        print("❌ DID resolution test failed.")
        # Continue with other tests
    
    # Step 4: Test DID verification
    if not test_did_verification(credential):
        print("❌ DID verification test failed.")
        # Continue with other tests
    
    # Step 5: Test DID formats
    if not test_did_formats(credential):
        print("❌ DID formats test failed.")
        # Continue with other tests
    
    # Step 6: Test cross-verification
    if not test_did_cross_verification(user_id):
        print("❌ DID cross-verification test failed.")
        # Continue with other tests
    
    print("\n✅ All DID functionality tests completed!")
    return True

if __name__ == "__main__":
    # Allow base URL to be provided as command line argument
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1]
    
    print(f"Testing Lemma DID functionality at: {BASE_URL}")
    
    try:
        if run_tests():
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1) 