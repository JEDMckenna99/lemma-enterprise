#!/usr/bin/env python3
"""
CloudFlare Caching Test Script for Lemma Shield
Tests caching rules and performance after CloudFlare Pro setup
"""

import requests
import time
from datetime import datetime

def test_cloudflare_caching():
    """Test CloudFlare caching rules for Lemma Shield"""
    
    base_url = "https://www.lemma.id"
    
    test_urls = [
        {
            "url": f"{base_url}/api/health",
            "expected_cache": "HIT or MISS",
            "description": "API Health Check (should cache for 5 minutes)"
        },
        {
            "url": f"{base_url}/static/css/lemma-shield-widget.css",
            "expected_cache": "HIT or MISS", 
            "description": "Static CSS (should cache for 1 month)"
        },
        {
            "url": f"{base_url}/static/js/lemma-shield-widget.js",
            "expected_cache": "HIT or MISS",
            "description": "Static JS (should cache for 1 month)"
        },
        {
            "url": f"{base_url}/api/shield/status",
            "expected_cache": "DYNAMIC or BYPASS",
            "description": "Dynamic API (should bypass cache)"
        }
    ]
    
    print("🚀 CloudFlare Caching Test for Lemma Shield")
    print("=" * 60)
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    for test in test_urls:
        print(f"Testing: {test['description']}")
        print(f"URL: {test['url']}")
        
        try:
            # Make request and measure time
            start_time = time.time()
            response = requests.get(test['url'], timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            # Check CloudFlare headers
            cf_cache_status = response.headers.get('CF-Cache-Status', 'UNKNOWN')
            cf_ray = response.headers.get('CF-RAY', 'N/A')
            server = response.headers.get('Server', 'N/A')
            
            print(f"✅ Status: {response.status_code}")
            print(f"⚡ Response Time: {response_time:.0f}ms")
            print(f"🌐 CF-Cache-Status: {cf_cache_status}")
            print(f"📡 CF-RAY: {cf_ray}")
            print(f"🖥️  Server: {server}")
            
            # Performance analysis
            if response_time < 100:
                print("🎯 EXCELLENT: Sub-100ms response time")
            elif response_time < 200:
                print("✅ GOOD: Sub-200ms response time")
            elif response_time < 500:
                print("⚠️  OK: Sub-500ms response time")
            else:
                print("❌ SLOW: >500ms response time")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ ERROR: {e}")
            
        print("-" * 40)
        print()

def test_performance_improvement():
    """Test performance before/after CloudFlare optimization"""
    
    print("📈 Performance Comparison Test")
    print("=" * 40)
    
    # Test multiple requests to see caching effect
    url = "https://www.lemma.id/api/health"
    times = []
    
    for i in range(5):
        start_time = time.time()
        try:
            response = requests.get(url, timeout=10)
            response_time = (time.time() - start_time) * 1000
            times.append(response_time)
            
            cf_cache_status = response.headers.get('CF-Cache-Status', 'UNKNOWN')
            print(f"Request {i+1}: {response_time:.0f}ms (Cache: {cf_cache_status})")
            
        except requests.exceptions.RequestException as e:
            print(f"Request {i+1}: ERROR - {e}")
            
        time.sleep(1)  # Wait 1 second between requests
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print()
        print(f"📊 Performance Summary:")
        print(f"   Average: {avg_time:.0f}ms")
        print(f"   Best: {min_time:.0f}ms") 
        print(f"   Worst: {max_time:.0f}ms")
        
        if avg_time < 150:
            print("🎉 EXCELLENT: CloudFlare optimization working!")
        elif avg_time < 300:
            print("✅ GOOD: Decent performance improvement")
        else:
            print("⚠️  Check CloudFlare configuration")

if __name__ == "__main__":
    print("🛡️  Lemma Shield - CloudFlare Caching Test")
    print()
    
    test_cloudflare_caching()
    print()
    test_performance_improvement()
    
    print()
    print("🔧 Next Steps:")
    print("1. If CF-Cache-Status shows 'MISS', wait a few minutes and test again")
    print("2. If response times are >200ms, check CloudFlare Speed settings")
    print("3. If caching isn't working, verify Cache Rules are configured")
    print("4. Enable Argo Smart Routing for additional 30% performance boost") 