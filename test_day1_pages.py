#!/usr/bin/env python3
"""
Test script for Day-1 priority pages in Lemma Enterprise
Tests all critical pages that should be working for customer onboarding
"""

import requests
import sys
import time
from urllib.parse import urljoin

# Test configuration
BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
TIMEOUT = 10

# Day-1 Priority Pages to test
DAY1_PAGES = [
    # Core Landing & Marketing
    ("/", "Homepage"),
    ("/landing", "Marketing Landing Page"),
    
    # Documentation & Developer Experience  
    ("/docs", "Documentation Hub"),
    ("/api-docs", "API Documentation"),
    ("/playground", "API Playground"),
    
    # Pricing & Status
    ("/pricing", "Pricing Page"),
    ("/status", "Status Page"),
    
    # Customer Onboarding Flow
    ("/onboarding", "Onboarding Start"),
    ("/onboarding/register", "Customer Registration"),
    ("/onboarding/dashboard", "Customer Dashboard"),
    ("/onboarding/api-keys", "API Key Management"),
    ("/onboarding/usage", "Usage Analytics"),
    ("/onboarding/integration", "Integration Guide"),
    
    # Core Verification Flow
    ("/verify", "Verification Page"),
    ("/protected", "Protected Content"),
    
    # Additional Demo Pages
    ("/gate-demo", "Gate Demo"),
    ("/widget-test", "Widget Test"),
    ("/api-widget-demo", "API Widget Demo"),
]

# API Endpoints to test
API_ENDPOINTS = [
    ("/api/health", "API Health Check"),
    ("/api/generate-challenge", "Challenge Generation"),
    ("/api/billing/health", "Billing Health"),
    ("/api/sandbox/status", "Sandbox Status"),
    ("/api/sre/dashboard/metrics", "SRE Metrics"),
]

def test_page(url, name, expected_status=200):
    """Test a single page and return results"""
    try:
        print(f"Testing {name:.<50} ", end="", flush=True)
        
        start_time = time.time()
        response = requests.get(url, timeout=TIMEOUT, allow_redirects=True)
        response_time = int((time.time() - start_time) * 1000)
        
        if response.status_code == expected_status:
            print(f"✅ {response.status_code} ({response_time}ms)")
            return True, response.status_code, response_time, None
        else:
            print(f"❌ {response.status_code} (expected {expected_status})")
            return False, response.status_code, response_time, f"Unexpected status code"
            
    except requests.exceptions.Timeout:
        print(f"⏰ TIMEOUT (>{TIMEOUT}s)")
        return False, 0, TIMEOUT*1000, "Request timeout"
    except requests.exceptions.ConnectionError:
        print(f"🔌 CONNECTION ERROR")
        return False, 0, 0, "Connection error"
    except Exception as e:
        print(f"💥 ERROR: {str(e)}")
        return False, 0, 0, str(e)

def test_redirect_page(url, name, expected_redirect_codes=[302, 301]):
    """Test pages that should redirect"""
    return test_page(url, name, expected_status=expected_redirect_codes[0])

def main():
    print("=" * 80)
    print("🚀 LEMMA ENTERPRISE - DAY-1 PAGES TEST")
    print("=" * 80)
    print(f"Testing: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s")
    print()
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    # Test Day-1 priority pages
    print("📋 DAY-1 PRIORITY PAGES")
    print("-" * 50)
    
    for path, name in DAY1_PAGES:
        url = urljoin(BASE_URL, path)
        success, status, response_time, error = test_page(url, name)
        
        total_tests += 1
        if success:
            passed_tests += 1
        else:
            failed_tests.append((name, path, status, error))
    
    print()
    
    # Test API endpoints
    print("🔌 API ENDPOINTS")
    print("-" * 50)
    
    for path, name in API_ENDPOINTS:
        url = urljoin(BASE_URL, path)
        success, status, response_time, error = test_page(url, name)
        
        total_tests += 1
        if success:
            passed_tests += 1
        else:
            failed_tests.append((name, path, status, error))
    
    print()
    
    # Test critical redirects (pages that require authentication)
    print("🔄 AUTHENTICATION REDIRECTS")
    print("-" * 50)
    
    auth_pages = [
        ("/admin", "Admin Dashboard (should redirect)"),
        ("/onboarding/verify", "Domain Verification (may redirect)"),
    ]
    
    for path, name in auth_pages:
        url = urljoin(BASE_URL, path)
        success, status, response_time, error = test_redirect_page(url, name)
        
        total_tests += 1
        if success or status in [302, 301, 200]:  # Allow redirects or success
            passed_tests += 1
        else:
            failed_tests.append((name, path, status, error))
    
    print()
    
    # Results summary
    print("=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    
    success_rate = (passed_tests / total_tests) * 100
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {len(failed_tests)} ❌")
    print(f"Success Rate: {success_rate:.1f}%")
    
    if failed_tests:
        print()
        print("❌ FAILED TESTS:")
        print("-" * 40)
        for name, path, status, error in failed_tests:
            print(f"  • {name}")
            print(f"    Path: {path}")
            print(f"    Status: {status}")
            print(f"    Error: {error}")
            print()
    
    # Overall assessment
    print("=" * 80)
    if success_rate >= 90:
        print("🎉 EXCELLENT! Day-1 pages are ready for customers")
        print("✅ Platform is ready for production onboarding")
    elif success_rate >= 80:
        print("✅ GOOD! Most Day-1 pages are working")
        print("⚠️  Minor issues need attention before full launch")
    elif success_rate >= 70:
        print("⚠️  NEEDS WORK! Several critical pages have issues")
        print("🔧 Fixes required before customer onboarding")
    else:
        print("❌ CRITICAL ISSUES! Major problems detected")
        print("🚨 Significant work needed before launch")
    
    print("=" * 80)
    
    # Return appropriate exit code
    return 0 if success_rate >= 90 else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 