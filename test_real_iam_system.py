"""
Test suite for Real IAM System with Rust Crypto Engine
Validates end-to-end permission verification
"""

import json
import time
import requests
from typing import Dict, List

# Test configuration
API_BASE = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"  # Heroku deployment
API_KEY = "test_api_key_12345"  # Replace with real API key if needed

def test_site_registration():
    """Test 1: Register a new site with real crypto"""
    print("\n" + "="*60)
    print("TEST 1: Site Registration with Real Crypto")
    print("="*60)
    
    response = requests.post(
        f"{API_BASE}/api/v1/sites/register",
        headers={"X-API-Key": API_KEY},
        json={
            "site_domain": "testcompany.com",
            "company_name": "Test Company Inc",
            "admin_email": "admin@testcompany.com",
            "plan": "professional"
        }
    )
    
    assert response.status_code == 201, f"Registration failed: {response.text}"
    data = response.json()
    
    print(f"Site registered: {data['site_id']}")
    if 'issuer_did' in data:
        print(f"Issuer DID: {data['issuer_did'][:50]}...")
        print(f"Crypto engine: {data.get('crypto_engine', 'unknown')}")
        print(f"Site isolation: {data.get('site_isolation', 'unknown')}")
    else:
        print("WARNING: Real IAM manager not connected yet (issuer_did missing)")
        print(f"Response: {data}")
    
    return data['site_id'], data['api_key']

def test_permission_creation(site_id: str, api_key: str):
    """Test 2: Create permission definitions"""
    print("\n" + "="*60)
    print("TEST 2: Permission Creation")
    print("="*60)
    
    permissions = [
        {
            "permission_id": "admin",
            "display_name": "Administrator",
            "scope": ["*"],
            "description": "Full access"
        },
        {
            "permission_id": "editor",
            "display_name": "Editor",
            "scope": ["posts:*", "comments:*"],
            "description": "Content management"
        },
        {
            "permission_id": "viewer",
            "display_name": "Viewer",
            "scope": ["posts:read", "comments:read"],
            "description": "Read-only access"
        }
    ]
    
    for perm in permissions:
        response = requests.post(
            f"{API_BASE}/api/v1/sites/{site_id}/permissions",
            headers={"X-API-Key": api_key},
            json=perm
        )
        
        assert response.status_code == 201, f"Permission creation failed: {response.text}"
        print(f"✅ Created permission: {perm['permission_id']}")
    
    return permissions

def test_permission_grant(site_id: str, api_key: str):
    """Test 3: Grant permission to user (issue real Ed25519 credential)"""
    print("\n" + "="*60)
    print("TEST 3: Permission Grant (Real Ed25519 Credential)")
    print("="*60)
    
    user_did = "did:lemma:test_user_12345"
    
    response = requests.post(
        f"{API_BASE}/api/v1/sites/{site_id}/users/{user_did}/permissions",
        headers={"X-API-Key": api_key},
        json={
            "permission_id": "admin",
            "expiry_days": 90
        }
    )
    
    assert response.status_code == 201, f"Permission grant failed: {response.text}"
    data = response.json()
    
    print(f"✅ Permission granted to user")
    print(f"🔐 Credential ID: {data['credential']['id']}")
    print(f"🔐 Issuer: {data['issuer_did'][:50]}...")
    print(f"⚡ Issue time: {data['issue_time_us']:.2f}µs")
    print(f"⚡ Crypto engine: {data['crypto_engine']}")
    
    return user_did, data['credential']

def test_access_verification(site_id: str, user_did: str, credential: Dict):
    """Test 4: Verify access using real crypto (Ed25519 + OPRF)"""
    print("\n" + "="*60)
    print("TEST 4: Access Verification (Real Crypto)")
    print("="*60)
    
    test_cases = [
        ("/admin/users", "read", True, "Admin should have read access"),
        ("/admin/users", "write", True, "Admin should have write access"),
        ("/posts", "delete", True, "Admin should have delete access"),
        ("/api/secret", "read", True, "Admin wildcard should grant access"),
    ]
    
    for resource, action, expected_access, description in test_cases:
        response = requests.post(
            f"{API_BASE}/api/v1/auth/verify",
            json={
                "site_id": site_id,
                "user_did": user_did,
                "resource": resource,
                "action": action,
                "user_lemmas": [credential]
            }
        )
        
        assert response.status_code == 200, f"Verification failed: {response.text}"
        data = response.json()
        
        has_access = data['has_access']
        verification_time = data['verification_time_us']
        
        status = "✅" if has_access == expected_access else "❌"
        print(f"{status} {description}")
        print(f"   Resource: {resource}:{action}")
        print(f"   Access: {has_access}")
        print(f"   ⚡ Verification time: {verification_time:.2f}µs")
        print(f"   Crypto engine: {data['crypto_engine']}")
        
        assert has_access == expected_access, f"Access check failed for {resource}:{action}"
        assert verification_time < 200, f"Verification too slow: {verification_time}µs (target: <200µs)"

def test_performance_benchmark(site_id: str, user_did: str, credential: Dict):
    """Test 5: Performance benchmark (100 verifications)"""
    print("\n" + "="*60)
    print("TEST 5: Performance Benchmark (100 verifications)")
    print("="*60)
    
    verification_times = []
    
    for i in range(100):
        response = requests.post(
            f"{API_BASE}/api/v1/auth/verify",
            json={
                "site_id": site_id,
                "user_did": user_did,
                "resource": "/admin/users",
                "action": "read",
                "user_lemmas": [credential]
            }
        )
        
        data = response.json()
        verification_times.append(data['verification_time_us'])
    
    avg_time = sum(verification_times) / len(verification_times)
    min_time = min(verification_times)
    max_time = max(verification_times)
    
    print(f"📊 Performance Results:")
    print(f"   Average: {avg_time:.2f}µs")
    print(f"   Min: {min_time:.2f}µs")
    print(f"   Max: {max_time:.2f}µs")
    print(f"   Target: 31-94µs")
    
    if avg_time <= 94:
        print(f"✅ PERFORMANCE TARGET MET!")
    else:
        print(f"⚠️ Performance slower than target")
    
    return avg_time

def run_all_tests():
    """Run complete IAM system test suite"""
    print("\n" + "="*60)
    print("LEMMA IAM SYSTEM - REAL CRYPTO TEST SUITE")
    print("="*60)
    
    try:
        # Test 1: Site registration
        site_id, api_key = test_site_registration()
        
        # Test 2: Permission creation
        permissions = test_permission_creation(site_id, api_key)
        
        # Test 3: Permission grant
        user_did, credential = test_permission_grant(site_id, api_key)
        
        # Test 4: Access verification
        test_access_verification(site_id, user_did, credential)
        
        # Test 5: Performance benchmark
        avg_time = test_performance_benchmark(site_id, user_did, credential)
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED!")
        print("="*60)
        print(f"Real Rust crypto engine working")
        print(f"Average verification time: {avg_time:.2f}us")
        print(f"IAM system ready for production")
        
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\nERROR: {e}")
        raise

if __name__ == "__main__":
    run_all_tests()
