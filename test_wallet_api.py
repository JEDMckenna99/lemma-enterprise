#!/usr/bin/env python3
"""
Wallet and VC API Test Script for Lemma

This script tests the API flow for verifiable credential issuance, 
presentation creation, and verification without requiring browser interaction.
"""
import sys
import json
import requests
import uuid
from urllib.parse import urljoin

# Base URL - change this to your local or Heroku instance
BASE_URL = "http://localhost:5000"

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 50)
    print(f" {title}")
    print("=" * 50)

def get_credential(user_id=None):
    """Get a credential for a user via API."""
    if not user_id:
        user_id = f"test-{uuid.uuid4().hex[:8]}"
    
    print_header(f"Getting Credential for User: {user_id}")
    
    url = urljoin(BASE_URL, f"/api/credential-lookup/{user_id}")
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            credential = response.json()
            print("✅ Successfully retrieved credential")
            print(f"Credential ID: {credential.get('id')}")
            
            # Check DID values in credential
            issuer = credential.get('issuer')
            subject = credential.get('credentialSubject', {}).get('id')
            
            print(f"Issuer DID: {issuer}")
            print(f"Subject DID: {subject}")
            
            return credential, user_id
        else:
            print(f"❌ Failed to get credential: {response.status_code}")
            print(f"Response: {response.text}")
            return None, user_id
    except Exception as e:
        print(f"❌ Exception during credential retrieval: {e}")
        return None, user_id

def create_presentation(credential, challenge="test-challenge"):
    """Create a verifiable presentation from a credential."""
    print_header("Creating Verifiable Presentation")
    
    if not credential:
        print("❌ No credential to create presentation from")
        return None
    
    url = urljoin(BASE_URL, "/api/presentation")
    
    try:
        response = requests.post(
            url,
            json={"credential": credential, "challenge": challenge}
        )
        
        if response.status_code == 200:
            presentation = response.json()
            print("✅ Successfully created verifiable presentation")
            print(f"Presentation type: {presentation.get('type')}")
            print(f"Challenge: {presentation.get('proof', {}).get('challenge')}")
            return presentation
        else:
            print(f"❌ Failed to create presentation: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception during presentation creation: {e}")
        return None

def verify_presentation(presentation):
    """Verify a presentation."""
    print_header("Verifying Presentation")
    
    if not presentation:
        print("❌ No presentation to verify")
        return False
    
    url = urljoin(BASE_URL, "/api/verify")
    
    try:
        response = requests.post(url, json=presentation)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('valid'):
                print("✅ Presentation verified successfully")
                print(f"Issuer: {result.get('issuer')}")
                print(f"Subject: {result.get('subject')}")
                return True
            else:
                print(f"❌ Presentation verification failed: {result.get('reason')}")
                return False
        else:
            print(f"❌ Verification request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False

def wallet_api_test(credential):
    """Test the wallet-related API endpoints."""
    print_header("Testing Wallet APIs")
    
    if not credential:
        print("❌ No credential available for wallet testing")
        return
    
    # 1. Format credential for wallet
    user_id = credential.get("credentialSubject", {}).get("id", "").replace("did:user:", "")
    
    print(f"Formatting credential for wallet storage with user ID: {user_id}")
    
    # Format wallet credential manually (mimicking LemmaWallet.format_for_wallet)
    wallet_credential = {
        "credential": credential,
        "wallet_metadata": {
            "added_at": "2023-07-01T12:00:00.000Z",  # Example timestamp
            "holder_id": user_id,
            "status": "active",
            "display_name": "Lemma Human Verification",
            "fingerprint": credential.get("id", f"fingerprint-{uuid.uuid4().hex}")
        }
    }
    
    print("✅ Credential formatted for wallet storage")
    
    # 2. Test store-credential API if available
    try:
        store_url = urljoin(BASE_URL, "/api/store-credential")
        store_response = requests.post(
            store_url,
            json={"user_id": user_id, "credential": credential}
        )
        
        if store_response.status_code == 200:
            print("✅ Successfully stored credential via API")
            print(f"Response: {store_response.json()}")
        else:
            print(f"❌ Failed to store credential via API: {store_response.status_code}")
            print(f"Response: {store_response.text}")
    except Exception as e:
        print(f"❌ Exception during credential storage API test: {e}")
    
    print("Wallet credential structure for client-side storage:")
    print(json.dumps(wallet_credential, indent=2))
    
    # 3. Demonstrating how to test verify-human endpoint with the credential
    try:
        print("\nTesting verify-human endpoint with the credential...")
        # Generate a challenge
        challenge = "test-challenge-" + uuid.uuid4().hex[:8]
        
        # Create a presentation
        presentation = create_presentation(credential, challenge)
        if not presentation:
            print("❌ Cannot test verify-human without a presentation")
            return
        
        # Use the verify-human endpoint to set session state
        verify_human_url = urljoin(BASE_URL, "/api/verify-human")
        verify_response = requests.post(
            verify_human_url,
            json={"presentation": presentation, "challenge": challenge}
        )
        
        if verify_response.status_code == 200:
            print("✅ Successfully verified human with credential")
            print(f"Response: {verify_response.json()}")
            
            # Try accessing protected content
            protected_url = urljoin(BASE_URL, "/protected")
            # Use same session to maintain cookies
            protected_response = requests.get(
                protected_url,
                cookies=verify_response.cookies
            )
            
            if protected_response.status_code == 200:
                print("✅ Successfully accessed protected content using session verification")
            else:
                print(f"❌ Failed to access protected content: {protected_response.status_code}")
        else:
            print(f"❌ Failed to verify human: {verify_response.status_code}")
            print(f"Response: {verify_response.text}")
    except Exception as e:
        print(f"❌ Exception during verify-human test: {e}")

def main():
    """Run the wallet and VC API flow tests."""
    if len(sys.argv) > 1:
        global BASE_URL
        BASE_URL = sys.argv[1]
    
    print(f"Testing Lemma wallet and VC APIs at: {BASE_URL}")
    
    # Step 1: Get a credential
    credential, user_id = get_credential()
    
    if not credential:
        print("❌ Failed to get a credential, cannot continue testing")
        return 1
    
    # Step 2: Test wallet APIs
    wallet_api_test(credential)
    
    # Step 3: Create a presentation
    presentation = create_presentation(credential)
    
    # Step 4: Verify the presentation
    if presentation:
        verify_presentation(presentation)
    
    print_header("Test Summary")
    print("Completed wallet and VC API flow testing for Lemma")
    print(f"URL tested: {BASE_URL}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 