"""
Test IAM Permission Types API
Tests the new permission types system
"""

import requests
import json

# Test configuration
BASE_URL = "http://localhost:5000"  # Local development
# BASE_URL = "https://lemma.id"  # Production

# Mock site for testing (you'll need to create this first)
TEST_SITE_ID = "site_test123"
TEST_ADMIN_EMAIL = "admin@test.com"

def test_create_permission_type():
    """Test creating a new permission type"""
    print("\n🧪 TEST 1: Create Permission Type")
    print("=" * 60)
    
    url = f"{BASE_URL}/api/iam/sites/{TEST_SITE_ID}/permission-types"
    
    # Test data - create a time-bound premium subscription
    data = {
        "name": "premium_tier_1",
        "type": "time-bound",
        "description": "Premium subscription tier 1",
        "config": {
            "duration_days": 365,
            "auto_renew": False
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Admin-Email": TEST_ADMIN_EMAIL
    }
    
    print(f"POST {url}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📋 Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 201:
            print("\n✅ TEST PASSED - Permission type created successfully!")
            return response.json()['permission_type_id']
        else:
            print(f"\n❌ TEST FAILED - Expected 201, got {response.status_code}")
            return None
            
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        return None


def test_list_permission_types():
    """Test listing permission types"""
    print("\n🧪 TEST 2: List Permission Types")
    print("=" * 60)
    
    url = f"{BASE_URL}/api/iam/sites/{TEST_SITE_ID}/permission-types"
    
    headers = {
        "X-Admin-Email": TEST_ADMIN_EMAIL
    }
    
    print(f"GET {url}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📋 Response Body:")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print(f"\n✅ TEST PASSED - Found {result['count']} permission types")
            return True
        else:
            print(f"\n❌ TEST FAILED - Expected 200, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        return False


def test_grant_permission():
    """Test granting a permission to a user"""
    print("\n🧪 TEST 3: Grant Permission to User")
    print("=" * 60)
    
    url = f"{BASE_URL}/api/iam/sites/{TEST_SITE_ID}/permissions/grant"
    
    data = {
        "email": "testuser@example.com",
        "permission": "premium_tier_1",
        "metadata": {
            "reason": "Test subscription",
            "order_id": "TEST-001"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Admin-Email": TEST_ADMIN_EMAIL
    }
    
    print(f"POST {url}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📋 Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 201:
            print("\n✅ TEST PASSED - Permission granted successfully!")
            return response.json()['instance_id']
        else:
            print(f"\n❌ TEST FAILED - Expected 201, got {response.status_code}")
            return None
            
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        return None


def test_search_users():
    """Test searching users by permission"""
    print("\n🧪 TEST 4: Search Users by Permission")
    print("=" * 60)
    
    url = f"{BASE_URL}/api/iam/sites/{TEST_SITE_ID}/users/search?permission=premium_tier_1"
    
    headers = {
        "X-Admin-Email": TEST_ADMIN_EMAIL
    }
    
    print(f"GET {url}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📋 Response Body:")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print(f"\n✅ TEST PASSED - Found {result['count']} users with permission")
            return True
        else:
            print(f"\n❌ TEST FAILED - Expected 200, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        return False


def test_get_stats():
    """Test getting IAM statistics"""
    print("\n🧪 TEST 5: Get IAM Statistics")
    print("=" * 60)
    
    url = f"{BASE_URL}/api/iam/sites/{TEST_SITE_ID}/stats"
    
    headers = {
        "X-Admin-Email": TEST_ADMIN_EMAIL
    }
    
    print(f"GET {url}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📋 Response Body:")
        result = response.json()
        print(json.dumps(result, indent=2))
        
        if response.status_code == 200:
            print("\n✅ TEST PASSED - Stats retrieved successfully!")
            print(f"   Permission Types: {result['permission_types']}")
            print(f"   Active Users: {result['active_users']}")
            print(f"   Active Instances: {result['active_instances']}")
            print(f"   Expiring Soon: {result['expiring_soon']}")
            return True
        else:
            print(f"\n❌ TEST FAILED - Expected 200, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        return False


def test_revoke_permission():
    """Test revoking a permission"""
    print("\n🧪 TEST 6: Revoke Permission")
    print("=" * 60)
    
    url = f"{BASE_URL}/api/iam/sites/{TEST_SITE_ID}/permissions/revoke"
    
    data = {
        "email": "testuser@example.com",
        "permission": "premium_tier_1",
        "reason": "Test revocation"
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Admin-Email": TEST_ADMIN_EMAIL
    }
    
    print(f"POST {url}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📋 Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            print("\n✅ TEST PASSED - Permission revoked successfully!")
            return True
        elif response.status_code == 404:
            print("\n⚠️ TEST WARNING - No active permissions to revoke (expected after first run)")
            return True
        else:
            print(f"\n❌ TEST FAILED - Expected 200, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        return False


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "=" * 60)
    print("  LEMMA IAM PERMISSION TYPES - TEST SUITE")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Site ID: {TEST_SITE_ID}")
    print("=" * 60)
    
    results = []
    
    # Test 1: Create permission type
    type_id = test_create_permission_type()
    results.append(("Create Permission Type", type_id is not None))
    
    # Test 2: List permission types
    results.append(("List Permission Types", test_list_permission_types()))
    
    # Test 3: Grant permission
    instance_id = test_grant_permission()
    results.append(("Grant Permission", instance_id is not None))
    
    # Test 4: Search users
    results.append(("Search Users", test_search_users()))
    
    # Test 5: Get stats
    results.append(("Get IAM Stats", test_get_stats()))
    
    # Test 6: Revoke permission
    results.append(("Revoke Permission", test_revoke_permission()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {test_name}")
    
    print("=" * 60)
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! IAM Permission Types API is working!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check errors above.")
    
    return passed == total


if __name__ == "__main__":
    print("""
    ⚠️ SETUP REQUIRED:
    1. Make sure Flask app is running (python app.py)
    2. Update TEST_SITE_ID with a valid site ID
    3. Run migrations/003_add_permission_types.sql if not already run
    
    Press Enter to continue...
    """)
    input()
    
    success = run_all_tests()
    exit(0 if success else 1)

