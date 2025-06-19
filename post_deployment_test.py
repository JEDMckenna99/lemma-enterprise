#!/usr/bin/env python3
"""
Post-Deployment Security Verification
Run this after deploying security fixes to production
"""

import requests

BASE_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
OLD_HARDCODED_KEY = '63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e'

def test_security_fixes():
    print("🛡️ Testing Security Fixes Post-Deployment")
    print("=" * 50)
    
    # Test 1: Old hardcoded API key should be blocked
    print("\n🔐 Test 1: Hardcoded API Key Block")
    try:
        response = requests.post(
            f"{BASE_URL}/api/issue-credential",
            headers={'X-API-Key': OLD_HARDCODED_KEY},
            json={'user_id': 'test_security'},
            timeout=10
        )
        
        if response.status_code in [401, 403]:
            print("✅ PASS: Old hardcoded API key is blocked")
        elif response.status_code == 200:
            print("❌ FAIL: Old hardcoded API key still works - VULNERABILITY ACTIVE!")
        else:
            print(f"⚠️  Unexpected response: {response.status_code}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 2: API endpoints require keys
    print("\n🔐 Test 2: API Key Requirement")
    try:
        response = requests.post(
            f"{BASE_URL}/api/issue-credential",
            json={'user_id': 'test'},
            timeout=10
        )
        
        if response.status_code == 401:
            print("✅ PASS: API endpoints require authentication")
        else:
            print(f"❌ FAIL: API endpoint accessible without key: {response.status_code}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 3: OPRF endpoint security
    print("\n🔐 Test 3: OPRF Endpoint Security")
    try:
        response = requests.get(f"{BASE_URL}/api/oprf/status", timeout=10)
        
        if response.status_code in [401, 403]:
            print("✅ PASS: OPRF endpoint requires authentication")
        elif response.status_code == 200:
            print("❌ FAIL: OPRF endpoint accessible without API key")
        else:
            print(f"⚠️  Response: {response.status_code}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Security Verification Complete!")
    print("All tests should show ✅ PASS after successful deployment")

if __name__ == "__main__":
    test_security_fixes() 