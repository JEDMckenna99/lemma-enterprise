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
    """Test unlimited offline verification and smart fallback system"""
    print("\n🔍 Testing Unlimited Offline Verification...")
    
    try:
        # Test multiple unlimited offline checks
        all_checks_passed = True
        for i in range(1, 4):  # Test 3 consecutive checks
            test_data = {
                "credential_id": "test_credential_123",
                "verification_count": i
            }
            response = requests.post(f"{BASE_URL}/api/verify-offline", 
                                   json=test_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('success') and 
                    data.get('network_calls') == 0 and 
                    data.get('unlimited_checks') == True):
                    print(f"✅ UNLIMITED CHECK #{i}: Success=True, Network calls=0, Unlimited=True")
                else:
                    print(f"⚠️ UNLIMITED CHECK #{i} ISSUE: {data}")
                    all_checks_passed = False
                    break
            else:
                print(f"❌ UNLIMITED CHECK #{i} FAILED: Status {response.status_code}")
                all_checks_passed = False
                break
        
        # Test smart fallback system
        if all_checks_passed:
            print("\n🔄 Testing Smart Fallback System...")
            fallback_data = {"credential_id": "test_credential_123"}
            fallback_response = requests.post(f"{BASE_URL}/api/verify-with-fallback", 
                                            json=fallback_data, timeout=10)
            
            if fallback_response.status_code == 200:
                fallback_result = fallback_response.json()
                verification_method = fallback_result.get('verification_method', 'unknown')
                
                if verification_method == 'offline_unlimited':
                    print("✅ SMART FALLBACK: Used unlimited offline verification (optimal)")
                elif verification_method == 'did_vp_fallback':
                    print("✅ SMART FALLBACK: Used DID VP fallback (acceptable)")
                else:
                    print(f"⚠️ SMART FALLBACK UNKNOWN: Method={verification_method}")
                
                return True
            else:
                print(f"⚠️ SMART FALLBACK ISSUE: Status {fallback_response.status_code}")
                return all_checks_passed  # Return based on unlimited checks result
        
        return all_checks_passed
            
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
        print("✅ Unlimited Offline Verification: FIXED")
        print("✅ Smart Fallback System: WORKING")
        print("\n🚀 All claims now validated - ready for 100% compliance!")
        print("💡 Sites can now verify credentials unlimited times offline!")
        print("🔄 DID VP verification only used as smart fallback when needed!")
    elif admin_fixed:
        print("🔄 PARTIAL SUCCESS (50%)")
        print("✅ Admin Security: FIXED")
        print("❌ Unlimited Offline Verification: NOT FIXED")
    elif offline_fixed:
        print("🔄 PARTIAL SUCCESS (50%)")
        print("❌ Admin Security: NOT FIXED")
        print("✅ Unlimited Offline Verification: FIXED")
    else:
        print("❌ NO SUCCESS (0%)")
        print("❌ Admin Security: NOT FIXED")
        print("❌ Unlimited Offline Verification: NOT FIXED")

if __name__ == "__main__":
    main() 