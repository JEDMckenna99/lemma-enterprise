#!/usr/bin/env python3
"""
Test script to validate 100% claim validation fixes
Tests both admin security and offline verification endpoint
"""

import requests
import json

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_admin_security():
    """Test admin endpoint returns proper security response instead of 200"""
    print("🔒 Testing Admin Security...")
    
    try:
        response = requests.get(f"{BASE_URL}/admin/", allow_redirects=False, timeout=10)
        print(f"Admin endpoint status: {response.status_code}")
        
        if response.status_code == 302:  # Redirect to login (good security)
            print("✅ ADMIN SECURITY FIXED: Properly redirects to login")
            return True
        elif response.status_code == 401 or response.status_code == 403:
            print("✅ ADMIN SECURITY FIXED: Returns proper auth error")
            return True
        elif response.status_code == 200:
            print("❌ ADMIN SECURITY FAILED: Still returns 200 (not secure)")
            return False
        else:
            print(f"⚠️ ADMIN SECURITY UNKNOWN: Returns {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Admin test error: {e}")
        return False

def test_offline_verification():
    """Test offline verification endpoint is accessible"""
    print("\n🔍 Testing Offline Verification...")
    
    try:
        test_data = {"credential_id": "test_credential_123"}
        response = requests.post(f"{BASE_URL}/api/verify-offline", 
                               json=test_data, timeout=10)
        
        print(f"Offline verification status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and 'network_calls' in data:
                network_calls = data.get('network_calls', 1)
                print(f"✅ OFFLINE VERIFICATION WORKING: Success={data.get('success')}, Network calls={network_calls}")
                return True
            else:
                print("⚠️ OFFLINE VERIFICATION PARTIAL: Endpoint works but response format unexpected")
                return False
        elif response.status_code == 404:
            print("❌ OFFLINE VERIFICATION FAILED: Endpoint not found (404)")
            return False
        else:
            print(f"⚠️ OFFLINE VERIFICATION UNKNOWN: Returns {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Offline verification test error: {e}")
        return False

def main():
    print("🎯 Testing 100% Validation Fixes")
    print("=" * 50)
    
    admin_fixed = test_admin_security()
    offline_fixed = test_offline_verification()
    
    print("\n📊 VALIDATION RESULTS:")
    print("=" * 50)
    
    if admin_fixed and offline_fixed:
        print("🎉 100% VALIDATION ACHIEVED!")
        print("✅ Admin Security: FIXED")
        print("✅ Offline Verification: FIXED")
        print("\n🚀 All claims now validated - ready for 100% compliance!")
    elif admin_fixed:
        print("🔄 PARTIAL SUCCESS (50%)")
        print("✅ Admin Security: FIXED")
        print("❌ Offline Verification: NOT FIXED")
    elif offline_fixed:
        print("🔄 PARTIAL SUCCESS (50%)")
        print("❌ Admin Security: NOT FIXED")
        print("✅ Offline Verification: FIXED")
    else:
        print("❌ NO SUCCESS (0%)")
        print("❌ Admin Security: NOT FIXED")
        print("❌ Offline Verification: NOT FIXED")

if __name__ == "__main__":
    main() 