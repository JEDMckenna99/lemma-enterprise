#!/usr/bin/env python3
"""
Targeted Performance Test for Optimized Endpoints
Tests specific endpoints to validate P95 latency ≤250ms requirement
"""

import requests
import time
import statistics
import json
from typing import List, Dict

def test_endpoint_performance(url: str, num_requests: int = 100) -> Dict:
    """Test endpoint performance and calculate statistics."""
    latencies = []
    errors = 0
    
    print(f"🚀 Testing {url} with {num_requests} requests...")
    
    for i in range(num_requests):
        start_time = time.time()
        try:
            response = requests.get(url, timeout=5)
            latency_ms = (time.time() - start_time) * 1000
            latencies.append(latency_ms)
            
            if response.status_code != 200:
                errors += 1
                
        except Exception as e:
            errors += 1
            latencies.append(5000)  # 5 second timeout as max latency
    
    if latencies:
        return {
            "url": url,
            "total_requests": num_requests,
            "successful_requests": num_requests - errors,
            "error_rate": errors / num_requests,
            "avg_latency_ms": statistics.mean(latencies),
            "median_latency_ms": statistics.median(latencies),
            "p95_latency_ms": statistics.quantiles(latencies, n=20)[18],  # 95th percentile
            "p99_latency_ms": statistics.quantiles(latencies, n=100)[98],  # 99th percentile
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies),
            "meets_p95_sla": statistics.quantiles(latencies, n=20)[18] <= 250.0
        }
    
    return {"error": "No successful requests"}

def main():
    """Run targeted performance tests."""
    print("🎯 TARGETED PERFORMANCE TEST FOR OPTIMIZED ENDPOINTS")
    print("=" * 60)
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    # Test optimized endpoints
    endpoints = [
        "/api/health",
        "/api/ping", 
        "/api/fast-test",
        "/api/generate-challenge"
    ]
    
    results = []
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        result = test_endpoint_performance(url, 50)
        results.append(result)
        
        if 'error' not in result:
            status = "✅ PASS" if result['meets_p95_sla'] else "❌ FAIL"
            print(f"\n{status} {endpoint}")
            print(f"  • P95 latency: {result['p95_latency_ms']:.1f}ms (target: ≤250ms)")
            print(f"  • Average latency: {result['avg_latency_ms']:.1f}ms")
            print(f"  • Success rate: {(1-result['error_rate'])*100:.1f}%")
            print(f"  • Range: {result['min_latency_ms']:.1f}ms - {result['max_latency_ms']:.1f}ms")
        else:
            print(f"❌ ERROR {endpoint}: {result['error']}")
    
    # Overall assessment
    print(f"\n🎯 PERFORMANCE ASSESSMENT")
    print("=" * 40)
    
    successful_tests = [r for r in results if 'error' not in r]
    passing_tests = [r for r in successful_tests if r['meets_p95_sla']]
    
    if successful_tests:
        best_p95 = min(r['p95_latency_ms'] for r in successful_tests)
        worst_p95 = max(r['p95_latency_ms'] for r in successful_tests)
        avg_p95 = statistics.mean(r['p95_latency_ms'] for r in successful_tests)
        
        print(f"📊 P95 Latency Range: {best_p95:.1f}ms - {worst_p95:.1f}ms")
        print(f"📊 Average P95 Latency: {avg_p95:.1f}ms")
        print(f"📊 Endpoints meeting SLA: {len(passing_tests)}/{len(successful_tests)}")
        
        if len(passing_tests) == len(successful_tests):
            print("🎉 ALL ENDPOINTS MEET P95 LATENCY SLA ≤250ms!")
        elif len(passing_tests) > 0:
            print("⚠️  Some endpoints meet SLA, optimization partially successful")
        else:
            print("❌ No endpoints meet P95 latency SLA")
    
    # Save detailed results
    with open('performance_targeted_results.json', 'w') as f:
        json.dump({
            "timestamp": time.time(),
            "test_config": {
                "requests_per_endpoint": 50,
                "target_p95_ms": 250
            },
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to performance_targeted_results.json")

if __name__ == "__main__":
    main() 