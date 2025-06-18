#!/usr/bin/env python3
"""
Shopify Integration Test Script
Tests all Lemma API endpoints needed for Shopify app integration
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
API_KEY = os.environ.get('LEMMA_API_KEY', 'test_key_for_development_only')

def test_endpoint(name, url, method='GET', headers=None, expected_status=200):
    """Test an API endpoint and return results"""
    print(f"Testing {name}...")
    try:
        response = None
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, timeout=10)
        
        if response is None:
            raise ValueError(f"Unsupported method: {method}")
            
        status = response.status_code
        
        # Handle multiple expected statuses
        if isinstance(expected_status, list):
            success = status in expected_status
        else:
            success = status == expected_status
        
        print(f"  {'✅' if success else '❌'} {name}: {status}")
        
        if success and response.content:
            try:
                data = response.json()
                print(f"    Response: {json.dumps(data, indent=2)[:200]}...")
            except:
                print(f"    Response: {response.text[:100]}...")
        
        return success, status, response
        
    except Exception as e:
        print(f"  ❌ {name}: ERROR - {str(e)}")
        return False, 0, None

def main():
    print("🛡️ TESTING LEMMA API FOR SHOPIFY INTEGRATION")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    # Headers for authenticated requests
    auth_headers = {'X-API-Key': API_KEY}
    
    # Test results storage
    results = {}
    
    print("📋 CORE SHOPIFY INTEGRATION TESTS")
    print("-" * 40)
    
    # 1. Basic Health Check
    success, status, resp = test_endpoint(
        "Basic Health Check", 
        f"{BASE_URL}/api/health"
    )
    results['health'] = success
    
    # 2. Shield Endpoints (if available)
    success, status, resp = test_endpoint(
        "Shield Health Check", 
        f"{BASE_URL}/api/shield/healthz",
        expected_status=[200, 404]  # 404 is OK if not implemented
    )
    results['shield_health'] = success or status == 404
    
    success, status, resp = test_endpoint(
        "Shield Challenge", 
        f"{BASE_URL}/api/shield/challenge",
        expected_status=[200, 404]
    )
    results['shield_challenge'] = success or status == 404
    
    # 3. Alternative verification endpoints
    success, status, resp = test_endpoint(
        "Generate Challenge", 
        f"{BASE_URL}/api/generate-challenge"
    )
    results['generate_challenge'] = success
    
    # 4. Billing endpoints for usage tracking
    success, status, resp = test_endpoint(
        "Billing Health", 
        f"{BASE_URL}/api/billing/health"
    )
    results['billing_health'] = success
    
    success, status, resp = test_endpoint(
        "Monthly Usage", 
        f"{BASE_URL}/api/billing/usage/monthly?site_id=shopify_test&month=2025-01",
        headers=auth_headers
    )
    results['monthly_usage'] = success
    
    success, status, resp = test_endpoint(
        "Daily Usage", 
        f"{BASE_URL}/api/billing/usage/daily?site_id=shopify_test&date=2025-01-15", 
        headers=auth_headers
    )
    results['daily_usage'] = success
    
    print("\n📊 TEST SUMMARY")
    print("-" * 40)
    
    total_tests = len(results)
    passed_tests = sum(1 for success in results.values() if success)
    
    for test_name, success in results.items():
        status_icon = "✅" if success else "❌"
        print(f"  {status_icon} {test_name.replace('_', ' ').title()}")
    
    print(f"\n🎯 RESULTS: {passed_tests}/{total_tests} tests passed")
    
    # Determine readiness for Shopify integration
    critical_tests = ['health', 'generate_challenge', 'billing_health']
    critical_passed = all(results.get(test, False) for test in critical_tests)
    
    if critical_passed:
        print("🚀 READY FOR SHOPIFY INTEGRATION!")
        print("   Core endpoints are operational")
    else:
        print("⚠️  NOT READY - Some critical endpoints failed")
        failed_critical = [test for test in critical_tests if not results.get(test, False)]
        print(f"   Failed critical tests: {failed_critical}")
    
    print(f"\n💡 NEXT STEPS:")
    if critical_passed:
        print("   1. Create basic Shopify app shell")
        print("   2. Build simple verification widget")
        print("   3. Test end-to-end flow")
    else:
        print("   1. Fix failed endpoint issues")
        print("   2. Re-run this test")
        print("   3. Proceed with Shopify integration")
    
    return critical_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 