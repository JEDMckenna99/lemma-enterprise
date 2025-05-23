import requests
import json
import os
import sys
import time
import base64
import random
import string

# Configuration
OPRF_SERVICE_URL = os.environ.get('OPRF_SERVICE_INTERNAL', 'https://lemma-oprf-service.herokuapp.com')
MAIN_APP_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'

def generate_random_string(length=10):
    """Generate a random string for testing purposes"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def test_oprf_status():
    """Test the OPRF service status endpoint"""
    print(f"Testing OPRF service status at {OPRF_SERVICE_URL}/status...")
    try:
        response = requests.get(f"{OPRF_SERVICE_URL}/status", timeout=10)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("OPRF service is running!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error connecting to OPRF service: {e}")
        return False

def test_oprf_evaluate():
    """Test the OPRF evaluation endpoint with a sample input"""
    print(f"\nTesting OPRF evaluation at {OPRF_SERVICE_URL}/evaluate...")
    try:
        # Create a sample blinded element (this is just for testing)
        sample_data = {
            "blinded_element": "X" + "1" * 64,
            "key_id": "test"
        }
        
        response = requests.post(
            f"{OPRF_SERVICE_URL}/evaluate", 
            json=sample_data,
            timeout=10
        )
        
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("OPRF evaluation successful!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing OPRF evaluation: {e}")
        return False

def test_main_app_oprf_integration():
    """Test the main app's integration with the OPRF service"""
    print(f"\nTesting main app's OPRF integration at {MAIN_APP_URL}/api/oprf/status...")
    try:
        response = requests.get(f"{MAIN_APP_URL}/api/oprf/status", timeout=10)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("Main app successfully connected to OPRF service!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        elif response.status_code == 404:
            print("API endpoint not found. This might be expected if the app doesn't expose a direct status endpoint.")
            # Try an alternative test - the credential verification flow
            return test_credential_verification_flow()
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing main app OPRF integration: {e}")
        # Try an alternative test - the credential verification flow
        return test_credential_verification_flow()

def test_credential_verification_flow():
    """Test the credential verification flow which should use the OPRF service for revocation checking"""
    print("\nTesting credential verification flow with OPRF revocation check...")
    try:
        # Create a mock credential presentation
        mock_presentation = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://lemma.example/contexts/human/v1"
            ],
            "type": ["VerifiablePresentation"],
            "verifiableCredential": [{
                "@context": [
                    "https://www.w3.org/2018/credentials/v1",
                    "https://lemma.example/contexts/human/v1"
                ],
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
            }],
            "proof": {
                "type": "Ed25519Signature2020",
                "created": "2025-05-22T15:35:22Z",
                "verificationMethod": f"did:test:{generate_random_string(20)}#key-1",
                "proofPurpose": "authentication",
                "challenge": generate_random_string(10),
                "domain": "verifier.example.com",
                "proofValue": base64.b64encode(os.urandom(64)).decode('utf-8')
            }
        }
        
        # Send the verification request
        verification_data = {
            "presentation": mock_presentation,
            "challenge": generate_random_string(10),
            "domain": "verifier.example.com",
            "check_revocation": True
        }
        
        response = requests.post(
            f"{MAIN_APP_URL}/api/credentials/verify", 
            json=verification_data,
            timeout=10
        )
        
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("Credential verification request processed!")
            print(f"Response: {json.dumps(result, indent=2)}")
            
            # Check if revocation was checked
            if "revocation_checked" in result and result["revocation_checked"]:
                print("✅ Revocation check was performed!")
                return True
            else:
                print("❌ Revocation check was not performed or not reported in the response.")
                return False
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing credential verification flow: {e}")
        return False

def main():
    print("=== OPRF Service and Integration Test ===\n")
    
    # Test OPRF service status
    oprf_status_ok = test_oprf_status()
    
    # Test OPRF evaluation
    oprf_eval_ok = test_oprf_evaluate()
    
    # Test main app integration
    main_app_integration_ok = test_main_app_oprf_integration()
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"OPRF Service Status: {'✅ PASS' if oprf_status_ok else '❌ FAIL'}")
    print(f"OPRF Evaluation: {'✅ PASS' if oprf_eval_ok else '❌ FAIL'}")
    print(f"Main App Integration: {'✅ PASS' if main_app_integration_ok else '❌ FAIL'}")
    
    # Overall result
    if oprf_status_ok and oprf_eval_ok and main_app_integration_ok:
        print("\n✅ All tests passed! The revocation layer is working properly.")
        return 0
    else:
        print("\n❌ Some tests failed. The revocation layer may not be fully functional.")
        return 1

if __name__ == "__main__":
    sys.exit(main())