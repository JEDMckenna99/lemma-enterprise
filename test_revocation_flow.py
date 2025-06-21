#!/usr/bin/env python3
"""
Test script to verify the revocation flow is working correctly
"""

import requests
import json
import time

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_revocation_flow():
    print("🔧 Testing Revocation Flow...")
    
    # Test 1: Basic API health check
    print("\n1️⃣ Testing API Health...")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        if response.status_code == 200:
            print("✅ API is healthy")
        else:
            print(f"⚠️ API returned: {response.status_code}")
    except Exception as e:
        print(f"❌ API health check failed: {e}")
        return
    
    # Test 2: Test revocation API with test credential
    print("\n2️⃣ Testing Revocation API...")
    test_credential_id = "test-credential-for-revocation-flow-12345"
    
    revoke_data = {
        "credential_id": test_credential_id,
        "reason": "Testing revocation flow from admin dashboard",
        "revoked_by": "test_system"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/shield/revoke-credential",
            json=revoke_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Revocation API successful")
            print(f"   - Response time: {result.get('response_time_ms', 0)}ms")
            print(f"   - Method: {result.get('method', 'unknown')}")
            print(f"   - Steps completed: {len(result.get('flow_steps_completed', []))}")
            
            # Test 3: Check if revocation is detected
            print("\n3️⃣ Testing Revocation Detection...")
            time.sleep(2)  # Allow propagation
            
            status_data = {
                "credentials": [{"id": test_credential_id}]
            }
            
            status_response = requests.post(
                f"{BASE_URL}/api/shield/status",
                json=status_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if status_response.status_code == 200:
                status_result = status_response.json()
                shield_action = status_result.get("shield_action", "unknown")
                
                if shield_action == "require_verification":
                    print("✅ Revocation detection working correctly")
                    print("   - Shield action: require_verification")
                    print("   - Revoked credentials detected")
                    return True
                else:
                    print(f"⚠️ Unexpected shield action: {shield_action}")
                    print(f"   - Full response: {json.dumps(status_result, indent=2)}")
                    return False
            else:
                print(f"❌ Status check failed: {status_response.status_code}")
                print(f"   - Response: {status_response.text}")
                return False
                
        else:
            print(f"❌ Revocation API failed: {response.status_code}")
            print(f"   - Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Revocation test failed: {e}")
        return False

def test_admin_dashboard():
    print("\n4️⃣ Testing Admin Dashboard Access...")
    try:
        response = requests.get(f"{BASE_URL}/admin/dashboard", timeout=10)
        if response.status_code in [200, 302]:  # 302 for redirect to login
            print("✅ Admin dashboard accessible")
            return True
        else:
            print(f"⚠️ Admin dashboard returned: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Admin dashboard test failed: {e}")
        return False

if __name__ == "__main__":
    print("🛡️ LEMMA REVOCATION FLOW TEST")
    print("=" * 50)
    
    # Run tests
    revocation_works = test_revocation_flow()
    admin_works = test_admin_dashboard()
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS:")
    print(f"   Revocation Flow: {'✅ PASS' if revocation_works else '❌ FAIL'}")
    print(f"   Admin Dashboard: {'✅ PASS' if admin_works else '❌ FAIL'}")
    
    if revocation_works and admin_works:
        print("\n🎉 All tests passed! The revocation flow should work in the admin dashboard.")
        print("\n📋 To test manually:")
        print("   1. Go to: https://lemma-enterprise-0f6ba17076c1.herokuapp.com/admin/dashboard")
        print("   2. Click 'Manage Credentials' tab")
        print("   3. Click 'Revoke' button on any credential")
        print("   4. Navigate to a protected page (e.g., /shield-demo)")
        print("   5. Shield should reappear requiring re-verification")
    else:
        print("\n❌ Some tests failed. Check the revocation system.") 