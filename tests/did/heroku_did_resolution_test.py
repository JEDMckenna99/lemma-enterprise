#!/usr/bin/env python3
"""
Heroku DID Resolution Test

A simple script to test DID resolution on your Heroku deployment.
This will help verify that the DID resolution is working correctly with your
configured DID method and Heroku environment variables.
"""
import sys
import json
import requests

# The Heroku app URL - replace with your actual URL
HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def test_did_resolution(did=None):
    """Test DID resolution with a specified DID or get the issuer DID from the system."""
    print(f"Testing DID resolution on {HEROKU_URL}")
    
    # If no DID provided, get the issuer DID from the system
    if not did:
        try:
            # Get a credential to extract the issuer DID
            response = requests.get(f"{HEROKU_URL}/api/credential/test-user")
            if response.status_code != 200:
                print(f"❌ Failed to get test credential: {response.status_code}")
                print(f"Response text: {response.text}")
                
                # Try to get issuer DID from a different endpoint
                print("Trying to get issuer DID from verify page...")
                verify_response = requests.get(f"{HEROKU_URL}/verify")
                
                if "issuer" in verify_response.text and "did:" in verify_response.text:
                    # Try to extract DID from HTML
                    import re
                    did_match = re.search(r'did:[a-zA-Z0-9:]+', verify_response.text)
                    if did_match:
                        did = did_match.group(0)
                        print(f"Found issuer DID in page: {did}")
                    else:
                        print("❌ Could not extract DID from verify page")
                        return False
                else:
                    print("❌ Could not find issuer DID in verify page")
                    return False
            else:
                credential = response.json()
                did = credential.get("issuer")
                
                if not did:
                    print("❌ Could not find issuer DID in credential")
                    return False
                
                print(f"Found issuer DID in credential: {did}")
        except Exception as e:
            print(f"❌ Error getting issuer DID: {e}")
            return False
    
    # Now test resolving this DID
    try:
        # First check if the resolve-did endpoint exists
        resolve_url = f"{HEROKU_URL}/api/resolve-did"
        
        print(f"Attempting to resolve DID: {did}")
        response = requests.post(resolve_url, json={"did": did})
        
        if response.status_code == 404:
            print("❌ DID resolution endpoint not found (404)")
            print("Checking if the app supports DID resolution...")
            
            # Try to get the DID document from the credential verify endpoint
            verify_url = f"{HEROKU_URL}/api/verify"
            verify_response = requests.post(verify_url, json={"id": "test", "issuer": did})
            
            if verify_response.status_code == 200:
                print("✅ App supports DID verification")
                print("DID resolution might be internal to the verify process")
                return True
            else:
                print(f"❌ DID verification also failed: {verify_response.status_code}")
                return False
        
        if response.status_code == 200:
            did_doc = response.json()
            print("\n=== DID Document ===")
            print(json.dumps(did_doc, indent=2))
            print("\n=== Analysis ===")
            
            # Analyze the DID document
            if did_doc.get("id") == did:
                print("✅ DID document has correct ID")
            else:
                print(f"❌ DID document has incorrect ID: {did_doc.get('id')}")
            
            # Check for verification methods
            verification_methods = did_doc.get("verificationMethod", [])
            if verification_methods:
                print(f"✅ DID document has {len(verification_methods)} verification method(s)")
                
                # Check the first verification method
                method = verification_methods[0]
                print(f"Verification method ID: {method.get('id')}")
                print(f"Verification method type: {method.get('type')}")
                print(f"Verification method controller: {method.get('controller')}")
                
                # Check for public key
                if "publicKeyJwk" in method:
                    print("✅ DID document has public key in JWK format")
                elif "publicKeyBase58" in method:
                    print("✅ DID document has public key in Base58 format")
                elif "publicKeyMultibase" in method:
                    print("✅ DID document has public key in Multibase format")
                else:
                    print("❌ DID document is missing public key")
            else:
                print("❌ DID document has no verification methods")
            
            # Check for authentication
            authentication = did_doc.get("authentication", [])
            if authentication:
                print(f"✅ DID document has {len(authentication)} authentication method(s)")
            else:
                print("❌ DID document has no authentication methods")
            
            return True
        else:
            print(f"❌ Failed to resolve DID: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"❌ Error resolving DID: {e}")
        return False

def test_verify_flow():
    """Test the verification flow to check DID usage."""
    print_header("Testing Verification Flow")
    
    try:
        # Visit the verification page
        verify_url = f"{HEROKU_URL}/verify"
        response = requests.get(verify_url)
        
        if response.status_code != 200:
            print(f"❌ Failed to access verification page: {response.status_code}")
            return False
        
        print("✅ Successfully accessed verification page")
        
        # Look for DID-related information
        if "did:" in response.text:
            print("✅ DID found in verification page")
        else:
            print("❌ No DID found in verification page")
        
        # Look for credential-related elements
        if "credential" in response.text.lower():
            print("✅ Credential-related content found")
        else:
            print("❌ No credential-related content found")
        
        # Try accessing the API directly
        api_url = f"{HEROKU_URL}/api/health"
        api_response = requests.get(api_url)
        
        if api_response.status_code == 200:
            print("✅ API health endpoint accessible")
            print(f"API response: {api_response.text}")
        else:
            print(f"❌ API health endpoint not accessible: {api_response.status_code}")
        
        return True
    except Exception as e:
        print(f"❌ Error testing verification flow: {e}")
        return False

if __name__ == "__main__":
    # Get URL and DID from command line or use default
    if len(sys.argv) > 1:
        if sys.argv[1].startswith("http"):
            HEROKU_URL = sys.argv[1]
            if len(sys.argv) > 2:
                target_did = sys.argv[2]
            else:
                target_did = None
        else:
            HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
            target_did = sys.argv[1]
    else:
        target_did = None
    
    # First test the verification flow
    test_verify_flow()
    
    # Then test DID resolution
    test_did_resolution(target_did) 