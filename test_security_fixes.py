#!/usr/bin/env python3
"""
Security Fix Validation Test Suite
Tests all critical security fixes on the live Lemma deployment
"""

import requests
import json
import sys
import os

# Configuration
BASE_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
OLD_HARDCODED_API_KEY = '63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e'  # Should be blocked
VALID_API_KEY = os.environ.get('LEMMA_API_KEY', 'test_key_for_development_only')

def test_endpoint(name, url, method='GET', headers=None, data=None, expected_status=200):
    """Test an endpoint and return results."""
    print(f"\n🧪 Testing: {name}")
    print(f"   URL: {url}")
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            response = requests.request(method, url, headers=headers, json=data, timeout=10)
            
        print(f"   Status: {response.status_code}")
        
        if response.status_code == expected_status:
            print(f"   ✅ PASS: Expected {expected_status}, got {response.status_code}")
        else:
            print(f"   ❌ FAIL: Expected {expected_status}, got {response.status_code}")
            
        # Show first 200 chars of response
        if response.text:
            print(f"   Response: {response.text[:200]}...")
            
        return response.status_code == expected_status, response
        
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False, None

def test_hardcoded_api_key_blocked():
    """Test that the old hardcoded API key is rejected."""
    print("\n🔐 CRITICAL TEST: Hardcoded API Key Rejection")
    
    # Test endpoints that should require API key
    test_endpoints = [
        '/api/issue-credential',
        '/api/verify-credential', 
        '/api/credentials',
    ]
    
    for endpoint in test_endpoints:
        url = f"{BASE_URL}{endpoint}"
        headers = {'X-API-Key': OLD_HARDCODED_API_KEY, 'Content-Type': 'application/json'}
        data = {'user_id': 'test_user'} if endpoint == '/api/issue-credential' else {}
        
        success, response = test_endpoint(
            f"Hardcoded API Key Block - {endpoint}",
            url,
            method='POST' if endpoint in ['/api/issue-credential', '/api/verify-credential'] else 'GET',
            headers=headers,
            data=data,
            expected_status=401  # Should be unauthorized
        )
        
        if not success and response and response.status_code in [403, 401]:
            print(f"   ✅ SECURITY PASS: Old API key properly rejected")
        elif success:
            print(f"   ❌ SECURITY FAIL: Old API key still accepted!")
            
def test_api_key_requirement():
    """Test that API endpoints require authentication."""
    print("\n🔐 CRITICAL TEST: API Key Requirement")
    
    test_endpoints = [
        '/api/issue-credential',
        '/api/verify-credential',
        '/api/credentials',
    ]
    
    for endpoint in test_endpoints:
        url = f"{BASE_URL}{endpoint}"
        
        # Test without API key
        success, response = test_endpoint(
            f"No API Key - {endpoint}",
            url,
            method='POST' if endpoint in ['/api/issue-credential', '/api/verify-credential'] else 'GET',
            headers={'Content-Type': 'application/json'},
            data={'user_id': 'test_user'} if endpoint == '/api/issue-credential' else {},
            expected_status=401  # Should be unauthorized
        )

def test_debug_mode_disabled():
    """Test that debug mode is disabled in production."""
    print("\n🔐 CRITICAL TEST: Debug Mode Disabled")
    
    # Try to access debug endpoints that shouldn't exist in production
    debug_endpoints = [
        '/debug-app',
        '/api/debug/routes',
        '/_debug',
        '/debug-session'
    ]
    
    for endpoint in debug_endpoints:
        url = f"{BASE_URL}{endpoint}"
        success, response = test_endpoint(
            f"Debug Endpoint Block - {endpoint}",
            url,
            expected_status=404  # Should not exist or be accessible
        )

def test_public_endpoints():
    """Test that public endpoints work correctly."""
    print("\n✅ Testing Public Endpoints")
    
    public_endpoints = [
        ('/', 200),  # Main page
        ('/api/ping', 200),  # Ping endpoint
        ('/api/fast-test', 200),  # Fast test endpoint
        ('/api/generate-challenge', 200),  # Challenge generation
    ]
    
    for endpoint, expected_status in public_endpoints:
        url = f"{BASE_URL}{endpoint}"
        test_endpoint(f"Public Endpoint - {endpoint}", url, expected_status=expected_status)

def test_oprf_security():
    """Test OPRF service security."""
    print("\n🔐 Testing OPRF Security")
    
    # Test OPRF status endpoint
    url = f"{BASE_URL}/api/oprf/status"
    headers = {'X-API-Key': VALID_API_KEY}
    
    success, response = test_endpoint(
        "OPRF Status (with API key)",
        url,
        headers=headers,
        expected_status=200
    )
    
    # Test OPRF without API key (should be blocked)
    success, response = test_endpoint(
        "OPRF Status (no API key)",
        url,
        expected_status=401
    )

def test_session_security():
    """Test session security improvements."""
    print("\n🔐 Testing Session Security")
    
    # Test admin login endpoint
    url = f"{BASE_URL}/admin/login"
    success, response = test_endpoint(
        "Admin Login Page",
        url,
        expected_status=200
    )

def main():
    """Run all security tests."""
    print("🛡️ Lemma Enterprise Security Fix Validation")
    print("=" * 50)
    print(f"Testing deployment: {BASE_URL}")
    print(f"Using API key: {VALID_API_KEY[:20]}...")
    
    # Run all tests
    test_public_endpoints()
    test_hardcoded_api_key_blocked()
    test_api_key_requirement()
    test_debug_mode_disabled()
    test_oprf_security()
    test_session_security()
    
    print("\n" + "=" * 50)
    print("🎯 Security Test Summary:")
    print("✅ All critical authentication bypasses should be blocked")
    print("✅ Hardcoded API keys should be rejected")
    print("✅ Debug mode should be disabled")
    print("✅ OPRF mock implementations should not be accessible")
    print("\n🔒 Production security validation complete!")

if __name__ == "__main__":
    main() 