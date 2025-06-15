#!/usr/bin/env python3
"""
Developer Docs Journey Test Suite
Tests the implementation of the three Developer Docs Journey requirements:
1. Landing View Docs scrolls to /docs#quick-start
2. Code blocks include "Copy cURL" and auto-inject user's demo key if present
3. OpenAPI download + version/status badges on every endpoint page
"""

import requests
import json
import time
from datetime import datetime

# Configuration
base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_docs_quick_start_anchor():
    """Test 1: Landing View Docs scrolls to /docs#quick-start"""
    try:
        # Test home page has link to docs#quick-start
        response = requests.get(f"{base_url}/", timeout=10)
        if response.status_code == 200:
            content = response.text
            if '/docs#quick-start' in content:
                # Test docs page has quick-start anchor
                docs_response = requests.get(f"{base_url}/docs", timeout=10)
                if docs_response.status_code == 200:
                    docs_content = docs_response.text
                    if 'id="quick-start"' in docs_content or 'name="quick-start"' in docs_content:
                        return True, "✅ Landing View Docs correctly links to /docs#quick-start anchor"
                    else:
                        return False, "❌ Docs page missing quick-start anchor"
                else:
                    return False, f"❌ Docs page not accessible (status: {docs_response.status_code})"
            else:
                return False, "❌ Home page missing link to /docs#quick-start"
        else:
            return False, f"❌ Home page not accessible (status: {response.status_code})"
    except Exception as e:
        return False, f"❌ Error testing docs quick-start: {str(e)}"

def test_copy_curl_buttons():
    """Test 2: Code blocks include "Copy cURL" and auto-inject user's demo key if present"""
    try:
        response = requests.get(f"{base_url}/api-docs", timeout=10)
        if response.status_code == 200:
            content = response.text
            
            # Check for Copy cURL buttons
            copy_curl_count = content.count('Copy cURL')
            if copy_curl_count >= 3:  # Should have multiple Copy cURL buttons
                # Check for API key injection placeholder
                if 'customer_api_key' in content or 'your_api_key_here' in content:
                    # Check for JavaScript copy functions
                    if 'copyToClipboard' in content:
                        return True, f"✅ Copy cURL buttons implemented ({copy_curl_count} found) with API key injection"
                    else:
                        return False, "❌ Copy cURL buttons present but missing JavaScript copy functionality"
                else:
                    return False, "❌ Copy cURL buttons present but missing API key injection"
            else:
                return False, f"❌ Insufficient Copy cURL buttons found (expected ≥3, found {copy_curl_count})"
        else:
            return False, f"❌ API docs page not accessible (status: {response.status_code})"
    except Exception as e:
        return False, f"❌ Error testing copy cURL buttons: {str(e)}"

def test_openapi_download_and_badges():
    """Test 3: OpenAPI download + version/status badges on every endpoint page"""
    try:
        # Test API docs page for badges and download link
        response = requests.get(f"{base_url}/api-docs", timeout=10)
        if response.status_code == 200:
            content = response.text
            
            # Check for version badges
            version_badge = 'v2.7.0' in content or 'Version: 2.7.0' in content
            
            # Check for status badges  
            status_badge = ('Operational' in content and 'API Status' in content) or 'Status:' in content
            
            # Check for OpenAPI download link
            openapi_download = 'Download OpenAPI Spec' in content or '/api/openapi.yaml' in content
            
            if version_badge and status_badge and openapi_download:
                # Test actual OpenAPI download
                openapi_response = requests.get(f"{base_url}/api/openapi.yaml", timeout=10)
                if openapi_response.status_code == 200:
                    openapi_content = openapi_response.text
                    if 'openapi:' in openapi_content and 'paths:' in openapi_content:
                        return True, "✅ OpenAPI download working with version/status badges on endpoint pages"
                    else:
                        return False, "❌ OpenAPI download returns invalid spec format"
                else:
                    return False, f"❌ OpenAPI download not working (status: {openapi_response.status_code})"
            else:
                missing = []
                if not version_badge: missing.append("version badge")
                if not status_badge: missing.append("status badge") 
                if not openapi_download: missing.append("OpenAPI download link")
                return False, f"❌ Missing: {', '.join(missing)}"
        else:
            return False, f"❌ API docs page not accessible (status: {response.status_code})"
    except Exception as e:
        return False, f"❌ Error testing OpenAPI download and badges: {str(e)}"

def run_developer_docs_journey_tests():
    """Run all Developer Docs Journey tests and generate report"""
    print("🚀 Developer Docs Journey Test Suite")
    print("=" * 50)
    print(f"Testing: {base_url}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Landing View Docs → /docs#quick-start", test_docs_quick_start_anchor),
        ("Copy cURL + API Key Injection", test_copy_curl_buttons), 
        ("OpenAPI Download + Version/Status Badges", test_openapi_download_and_badges)
    ]
    
    results = []
    passed = 0
    
    for test_name, test_func in tests:
        print(f"Testing: {test_name}")
        try:
            success, message = test_func()
            results.append({
                'test': test_name,
                'passed': success,
                'message': message
            })
            if success:
                passed += 1
            print(f"  {message}")
        except Exception as e:
            results.append({
                'test': test_name,
                'passed': False,
                'message': f"❌ Test error: {str(e)}"
            })
            print(f"  ❌ Test error: {str(e)}")
        print()
    
    # Summary
    total = len(tests)
    percentage = (passed / total) * 100
    
    print("=" * 50)
    print(f"📊 DEVELOPER DOCS JOURNEY RESULTS")
    print(f"Passed: {passed}/{total} ({percentage:.0f}%)")
    
    if percentage == 100:
        print("🎉 ALL DEVELOPER DOCS JOURNEY REQUIREMENTS COMPLETE!")
        status = "COMPLETE"
    elif percentage >= 67:
        print("⚠️  Most requirements implemented, minor fixes needed")
        status = "MOSTLY_COMPLETE"
    else:
        print("❌ Significant implementation work required")
        status = "INCOMPLETE"
    
    print()
    print("📋 Detailed Results:")
    for result in results:
        status_icon = "✅" if result['passed'] else "❌"
        print(f"  {status_icon} {result['test']}")
        if not result['passed']:
            print(f"     {result['message']}")
    
    # Save results
    test_results = {
        'timestamp': datetime.now().isoformat(),
        'base_url': base_url,
        'total_tests': total,
        'passed_tests': passed,
        'percentage': percentage,
        'status': status,
        'results': results
    }
    
    with open('developer_docs_journey_results.json', 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\n💾 Results saved to: developer_docs_journey_results.json")
    return percentage == 100

if __name__ == "__main__":
    success = run_developer_docs_journey_tests()
    exit(0 if success else 1) 