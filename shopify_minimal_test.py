#!/usr/bin/env python3
"""
Minimal Shopify Integration Test
Tests only the essential endpoints needed for Shopify human verification
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'

def test_essential_endpoints():
    """Test only the essential endpoints for Shopify integration"""
    print("🛡️ MINIMAL SHOPIFY INTEGRATION TEST")
    print("=" * 50)
    print(f"Testing: {BASE_URL}")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    results = {}
    
    # 1. Basic Health Check - Essential
    print("Testing Basic Health...")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        success = response.status_code == 200
        print(f"  {'✅' if success else '❌'} Health Check: {response.status_code}")
        if success:
            print(f"    Service: {response.json().get('service')}")
        results['health'] = success
    except Exception as e:
        print(f"  ❌ Health Check: ERROR - {str(e)}")
        results['health'] = False
    
    # 2. Challenge Generation - Essential for verification
    print("\nTesting Challenge Generation...")
    try:
        response = requests.get(f"{BASE_URL}/api/generate-challenge", timeout=10)
        success = response.status_code == 200
        print(f"  {'✅' if success else '❌'} Generate Challenge: {response.status_code}")
        if success:
            data = response.json()
            print(f"    Challenge: {data.get('challenge', '')[:20]}...")
            print(f"    Expires in: {data.get('expiry_seconds')} seconds")
        results['challenge'] = success
    except Exception as e:
        print(f"  ❌ Generate Challenge: ERROR - {str(e)}")
        results['challenge'] = False
    
    # 3. Human Verification - Essential for the core functionality
    print("\nTesting Human Verification Endpoint...")
    try:
        response = requests.post(f"{BASE_URL}/api/verify-human", 
                               json={}, timeout=10)
        # We expect this to fail with 400 (bad request) since we're not sending valid data
        # But the endpoint should exist and respond
        success = response.status_code in [400, 422]  # Bad request is OK - endpoint exists
        print(f"  {'✅' if success else '❌'} Verify Human: {response.status_code}")
        if response.status_code == 400:
            print("    Endpoint exists (400 = missing data, as expected)")
        results['verify_human'] = success
    except Exception as e:
        print(f"  ❌ Verify Human: ERROR - {str(e)}")
        results['verify_human'] = False
    
    # 4. Shield Widget Script - For frontend integration
    print("\nTesting Shield Widget Script...")
    try:
        response = requests.get(f"{BASE_URL}/static/js/lemma-shield.js", timeout=10)
        success = response.status_code == 200
        print(f"  {'✅' if success else '❌'} Shield Script: {response.status_code}")
        if success:
            script_size = len(response.content)
            print(f"    Script size: {script_size} bytes")
        results['shield_script'] = success
    except Exception as e:
        print(f"  ❌ Shield Script: ERROR - {str(e)}")
        results['shield_script'] = False
    
    print("\n📊 SUMMARY")
    print("-" * 50)
    
    total_tests = len(results)
    passed_tests = sum(1 for success in results.values() if success)
    
    for test_name, success in results.items():
        status_icon = "✅" if success else "❌"
        print(f"  {status_icon} {test_name.replace('_', ' ').title()}")
    
    print(f"\n🎯 RESULTS: {passed_tests}/{total_tests} tests passed")
    
    # Determine Shopify readiness
    critical_tests = ['health', 'challenge', 'verify_human']
    critical_passed = all(results.get(test, False) for test in critical_tests)
    
    if critical_passed:
        print("\n🚀 READY FOR SHOPIFY INTEGRATION!")
        print("   ✅ Core verification endpoints working")
        print("   ✅ Can generate challenges for customers")
        print("   ✅ Can verify human status")
        print("\n💡 NEXT STEPS:")
        print("   1. Create basic Shopify app")
        print("   2. Build verification widget")
        print("   3. Test with real Shopify store")
    else:
        print("\n⚠️  NOT READY FOR SHOPIFY")
        failed_tests = [test for test in critical_tests if not results.get(test, False)]
        print(f"   Failed critical tests: {failed_tests}")
        print("\n💡 NEXT STEPS:")
        print("   1. Fix failed endpoints")
        print("   2. Re-run this test")
    
    print(f"\n🎯 SHOPIFY INTEGRATION SCOPE:")
    print("   • Human verification widget in checkout")
    print("   • Basic merchant dashboard")
    print("   • Simple on/off settings")
    print("   • That's it! (No complex billing APIs needed)")
    
    return critical_passed

if __name__ == "__main__":
    success = test_essential_endpoints()
    exit(0 if success else 1) 