"""
Test script for credential verification with OPRF revocation checks.
This script tests the full credential verification flow, including revocation checks.
"""

import requests
import json
import os
import sys
import time
import base64
import random
import string
import uuid

# Configuration
MAIN_APP_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'

def generate_random_string(length=10):
    """Generate a random string for testing purposes"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_mock_credential():
    """Generate a mock credential for testing"""
    # Generate a unique ID for the credential
    credential_id = f"urn:uuid:{uuid.uuid4()}"
    
    # Create a mock credential
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://lemma.example/contexts/human/v1"
        ],
        "id": credential_id,
        "type": ["VerifiableCredential", "HumanCredential"],
        "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
        "issuanceDate": "2025-05-22T15:30:45Z",
        "expirationDate": "2026-01-01T00:00:00Z",
        "credentialSubject": {
            "id": f"did:test:{generate_random_string(20)}",
            "isHuman": True,
            "verificationLevel": "basic"
        },
        "proof": {
            "type": "Ed25519Signature2020",
            "created": "2025-05-22T15:30:45Z",
            "verificationMethod": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com#key-1",
            "proofPurpose": "assertionMethod",
            "proofValue": base64.b64encode(os.urandom(64)).decode('utf-8')
        }
    }

def generate_mock_presentation(credential):
    """Generate a mock presentation containing the credential"""
    # Generate a challenge and domain for the presentation
    challenge = generate_random_string(10)
    domain = "verifier.example.com"
    
    # Create a mock presentation
    presentation = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://lemma.example/contexts/human/v1"
        ],
        "type": ["VerifiablePresentation"],
        "verifiableCredential": [credential],
        "proof": {
            "type": "Ed25519Signature2020",
            "created": "2025-05-22T15:35:22Z",
            "verificationMethod": f"did:test:{generate_random_string(20)}#key-1",
            "proofPurpose": "authentication",
            "challenge": challenge,
            "domain": domain,
            "proofValue": base64.b64encode(os.urandom(64)).decode('utf-8')
        }
    }
    
    return presentation, challenge, domain

def test_oprf_status():
    """Test the OPRF status endpoint"""
    print(f"\nTesting OPRF status at {MAIN_APP_URL}/api/oprf/status...")
    try:
        response = requests.get(f"{MAIN_APP_URL}/api/oprf/status", timeout=10)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("OPRF service is available!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing OPRF status: {e}")
        return False

def test_credential_verification_without_revocation():
    """Test credential verification without revocation checks"""
    print("\nTesting credential verification without revocation checks...")
    try:
        # Generate a mock credential and presentation
        credential = generate_mock_credential()
        presentation, challenge, domain = generate_mock_presentation(credential)
        
        # Create the verification request
        verification_data = {
            "presentation": presentation,
            "challenge": challenge,
            "domain": domain,
            "check_revocation": False
        }
        
        # Send the verification request
        response = requests.post(
            f"{MAIN_APP_URL}/api/credentials/verify", 
            json=verification_data,
            timeout=10
        )
        
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("Credential verification successful!")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            # Check if revocation was not checked
            if "revocation_checked" in result and not result["revocation_checked"]:
                print("✅ Revocation check was correctly skipped!")
                return True
            else:
                print("❌ Revocation check was performed when it should have been skipped.")
                return False
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing credential verification: {e}")
        return False

def test_credential_verification_with_revocation():
    """Test credential verification with revocation checks"""
    print("\nTesting credential verification with revocation checks...")
    try:
        # Generate a mock credential and presentation
        credential = generate_mock_credential()
        presentation, challenge, domain = generate_mock_presentation(credential)
        
        # Create the verification request
        verification_data = {
            "presentation": presentation,
            "challenge": challenge,
            "domain": domain,
            "check_revocation": True
        }
        
        # Send the verification request
        response = requests.post(
            f"{MAIN_APP_URL}/api/credentials/verify", 
            json=verification_data,
            timeout=10
        )
        
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("Credential verification successful!")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            # Check if revocation was checked
            if "revocation_checked" in result and result["revocation_checked"]:
                print("✅ Revocation check was performed!")
                
                # Check the revocation status
                if "revocation_status" in result:
                    print(f"Revocation status: {result['revocation_status']}")
                    
                    # We expect the credential to not be revoked
                    if result["revocation_status"] == "not_revoked":
                        print("✅ Credential is correctly marked as not revoked!")
                        return True
                    else:
                        print("❌ Unexpected revocation status.")
                        return False
                else:
                    print("❌ Revocation status not included in response.")
                    return False
            else:
                print("❌ Revocation check was not performed when requested.")
                return False
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing credential verification with revocation: {e}")
        return False

def main():
    print("=== Credential Verification Test with OPRF Revocation ===\n")
    
    # Test OPRF status
    oprf_status_ok = test_oprf_status()
    
    # Test credential verification without revocation
    verification_without_revocation_ok = test_credential_verification_without_revocation()
    
    # Test credential verification with revocation
    verification_with_revocation_ok = test_credential_verification_with_revocation()
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"OPRF Status: {'✅ PASS' if oprf_status_ok else '❌ FAIL'}")
    print(f"Verification without Revocation: {'✅ PASS' if verification_without_revocation_ok else '❌ FAIL'}")
    print(f"Verification with Revocation: {'✅ PASS' if verification_with_revocation_ok else '❌ FAIL'}")
    
    # Overall result
    if oprf_status_ok and verification_without_revocation_ok and verification_with_revocation_ok:
        print("\n✅ All tests passed! The credential verification endpoint is working properly with OPRF revocation checks.")
        return 0
    else:
        print("\n❌ Some tests failed. The credential verification endpoint may not be fully functional.")
        return 1

if __name__ == "__main__":
    sys.exit(main())