#!/usr/bin/env python3
"""
Simple SRE Observability Test
Tests the key SRE endpoints with CloudFlare CDN performance
"""

import requests
import time
import json

# Configuration
BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
API_KEY = "63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e"
HEADERS = {"X-API-Key": API_KEY}

def test_endpoint(endpoint, use_auth=False):
    """Test a single endpoint and measure performance"""
    url = BASE_URL + endpoint
    headers = HEADERS if use_auth else {}
    
    try:
        start = time.time()
        response = requests.get(url, headers=headers, timeout=10)
        end = time.time()
        latency = (end - start) * 1000
        
        print(f"✅ {endpoint}")
        print(f"   Status: {response.status_code}")
        print(f"   Latency: {latency:.1f}ms")
        
        if response.status_code == 200:
            try:
                data = response.json()
                # Show key metrics if available
                if 'p95_latency_ms' in str(data):
                    print(f"   P95 Latency: {data.get('p95_latency_ms', 'N/A')}ms")
                if 'error_rate' in str(data):
                    print(f"   Error Rate: {data.get('error_rate', 'N/A')}%")
                if 'mah_total' in str(data):
                    print(f"   MAH Total: {data.get('mah_total', 'N/A')}")
                return True, latency, data
            except:
                print(f"   Response: {response.text[:100]}...")
                return True, latency, response.text
        else:
            print(f"   Error: {response.text[:100]}")
            return False, latency, response.text
            
    except Exception as e:
        print(f"❌ {endpoint}")
        print(f"   Error: {str(e)}")
        return False, 0, str(e)

def main():
    print("🔍 SRE OBSERVABILITY TEST - CloudFlare CDN Performance")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test basic endpoints (no auth required)
    print("📊 BASIC ENDPOINTS")
    print("-" * 30)
    basic_endpoints = [
        "/api/health",
        "/api/generate-challenge",
    ]
    
    basic_results = []
    for endpoint in basic_endpoints:
        success, latency, data = test_endpoint(endpoint, use_auth=False)
        basic_results.append((endpoint, success, latency))
        print()
    
    # Test SRE endpoints (auth required)
    print("📈 SRE OBSERVABILITY ENDPOINTS")
    print("-" * 30)
    sre_endpoints = [
        "/api/sre/dashboard/metrics",
        "/api/sre/metrics/latency",
        "/api/sre/metrics/errors",
        "/api/sre/metrics/prometheus",
        "/api/billing/health",
    ]
    
    sre_results = []
    for endpoint in sre_endpoints:
        success, latency, data = test_endpoint(endpoint, use_auth=True)
        sre_results.append((endpoint, success, latency))
        print()
    
    # Summary
    print("📋 PERFORMANCE SUMMARY")
    print("-" * 30)
    
    all_latencies = [lat for _, success, lat in basic_results + sre_results if success and lat > 0]
    if all_latencies:
        avg_latency = sum(all_latencies) / len(all_latencies)
        max_latency = max(all_latencies)
        min_latency = min(all_latencies)
        
        print(f"Average Latency: {avg_latency:.1f}ms")
        print(f"Min Latency: {min_latency:.1f}ms")
        print(f"Max Latency: {max_latency:.1f}ms")
        
        # Performance assessment with CloudFlare CDN
        if avg_latency < 250:
            print("🎯 EXCELLENT: Sub-250ms average latency achieved!")
        elif avg_latency < 500:
            print("✅ GOOD: CloudFlare CDN providing solid performance")
        else:
            print("⚠️  NEEDS OPTIMIZATION: Consider additional CDN tuning")
    
    success_count = sum(1 for _, success, _ in basic_results + sre_results if success)
    total_count = len(basic_results + sre_results)
    success_rate = (success_count / total_count) * 100
    
    print(f"Success Rate: {success_rate:.1f}% ({success_count}/{total_count})")
    
    # Overall assessment
    print()
    print("🎯 SRE OBSERVABILITY ASSESSMENT")
    print("-" * 30)
    if success_rate >= 80 and (not all_latencies or avg_latency < 500):
        print("✅ SRE OBSERVABILITY: OPERATIONAL")
        print("   CloudFlare CDN + SRE monitoring working well")
    elif success_rate >= 60:
        print("⚠️  SRE OBSERVABILITY: PARTIAL")
        print("   Some endpoints working, optimization needed")
    else:
        print("❌ SRE OBSERVABILITY: NEEDS ATTENTION")
        print("   Multiple endpoints failing")

if __name__ == "__main__":
    main() 