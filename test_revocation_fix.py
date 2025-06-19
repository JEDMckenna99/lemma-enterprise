#!/usr/bin/env python3

import requests
import json

def test_revocation_endpoint():
    """Test the revocation endpoint with test mode"""
    url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/shield/revoke-credential"
    
    headers = {
        "Content-Type": "application/json",
        "X-CSRFToken": "test"
    }
    
    data = {
        "credential_id": "test-credential-123",
        "reason": "Testing revocation functionality",
        "revoked_by": "user_self_test"  # This triggers test mode
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Revocation endpoint working!")
            return True
        else:
            print("❌ FAILED: Revocation endpoint still has issues")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    print("Testing revocation endpoint fix...")
    test_revocation_endpoint() 