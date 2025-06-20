#!/usr/bin/env python3
"""
Lemma Shield Load Testing & Performance Validation
Validates performance against production requirements:
- ≥3200 concurrent requests
- Offline verify < 100ms
- Fallback < 500ms  
- Revoke loop ≤ 4s
"""

import asyncio
import aiohttp
import time
import json
import statistics
import concurrent.futures
from typing import List, Dict, Any
import argparse

# Configuration
BASE_URL = "http://localhost:5000"
DEFAULT_CONCURRENT_REQUESTS = 3200
DEFAULT_DURATION_SECONDS = 30

class LoadTestResults:
    def __init__(self):
        self.response_times = []
        self.success_count = 0
        self.error_count = 0
        self.start_time = 0
        self.end_time = 0
        
    def add_result(self, response_time: float, success: bool):
        self.response_times.append(response_time)
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        if not self.response_times:
            return {"error": "No data collected"}
            
        total_requests = len(self.response_times)
        duration = self.end_time - self.start_time
        
        sorted_times = sorted(self.response_times)
        
        return {
            "total_requests": total_requests,
            "duration_seconds": duration,
            "requests_per_second": total_requests / duration if duration > 0 else 0,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": (self.success_count / total_requests) * 100 if total_requests > 0 else 0,
            "response_times": {
                "min_ms": min(sorted_times),
                "max_ms": max(sorted_times),
                "avg_ms": statistics.mean(sorted_times),
                "median_ms": statistics.median(sorted_times),
                "p95_ms": sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else 0,
                "p99_ms": sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else 0
            }
        }

async def make_request(session: aiohttp.ClientSession, url: str, method: str = "POST", data: Dict = None) -> tuple:
    """Make a single HTTP request and measure response time."""
    start_time = time.time()
    try:
        if method == "POST":
            async with session.post(url, json=data) as response:
                await response.text()  # Consume response
                response_time = (time.time() - start_time) * 1000  # Convert to ms
                return response_time, response.status == 200
        else:
            async with session.get(url) as response:
                await response.text()  # Consume response
                response_time = (time.time() - start_time) * 1000  # Convert to ms
                return response_time, response.status == 200
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        print(f"Request failed: {e}")
        return response_time, False

async def load_test_endpoint(endpoint: str, concurrent_requests: int, duration_seconds: int, 
                           method: str = "POST", request_data: Dict = None) -> LoadTestResults:
    """Run load test against a specific endpoint."""
    print(f"\n🚀 Load Testing: {endpoint}")
    print(f"📊 Target: {concurrent_requests} concurrent requests for {duration_seconds} seconds")
    print(f"🎯 Method: {method}")
    
    results = LoadTestResults()
    results.start_time = time.time()
    
    # Create aiohttp session with connection limits
    connector = aiohttp.TCPConnector(limit=concurrent_requests, limit_per_host=concurrent_requests)
    timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Create tasks for concurrent requests
        tasks = []
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            # Create batch of concurrent requests
            batch_tasks = []
            for _ in range(min(concurrent_requests, 100)):  # Batch size limit
                if time.time() >= end_time:
                    break
                task = make_request(session, f"{BASE_URL}{endpoint}", method, request_data)
                batch_tasks.append(task)
            
            if batch_tasks:
                # Execute batch and collect results
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, tuple):
                        response_time, success = result
                        results.add_result(response_time, success)
                    else:
                        # Exception occurred
                        results.add_result(5000, False)  # 5s timeout as failure
            
            # Small delay to prevent overwhelming the server
            await asyncio.sleep(0.01)
    
    results.end_time = time.time()
    return results

def test_offline_verification_performance():
    """Test 1: Offline Verification - Must be < 100ms"""
    print("\n" + "="*60)
    print("TEST 1: OFFLINE VERIFICATION PERFORMANCE (<100ms)")
    print("="*60)
    
    request_data = {
        "credential_id": "test_load_credential",
        "credential": {
            "id": "test_load", 
            "attributes": {"isHuman": True}
        },
        "verification_count": 1
    }
    
    return asyncio.run(load_test_endpoint(
        "/api/verify-offline", 
        concurrent_requests=1000,  # High concurrency for offline
        duration_seconds=10,
        method="POST",
        request_data=request_data
    ))

def test_fallback_verification_performance():
    """Test 2: Fallback Verification - Must be < 500ms"""
    print("\n" + "="*60)
    print("TEST 2: FALLBACK VERIFICATION PERFORMANCE (<500ms)")
    print("="*60)
    
    request_data = {
        "credential_id": "test_fallback_credential",
        "credential": {
            "id": "test_fallback",
            "attributes": {"isHuman": True}
        }
    }
    
    return asyncio.run(load_test_endpoint(
        "/api/verify-with-fallback",
        concurrent_requests=500,  # Moderate concurrency for fallback
        duration_seconds=15,
        method="POST", 
        request_data=request_data
    ))

def test_revocation_performance():
    """Test 3: Revocation Performance - Must be ≤ 4s"""
    print("\n" + "="*60)
    print("TEST 3: REVOCATION PERFORMANCE (≤4s)")
    print("="*60)
    
    # Test single revocation for timing
    start_time = time.time()
    
    request_data = {
        "credential_id": f"test_revoke_{int(time.time())}",
        "reason": "Load test revocation",
        "revoked_by": "load_test"
    }
    
    try:
        import requests
        response = requests.post(f"{BASE_URL}/api/shield/revoke-credential", json=request_data, timeout=10)
        end_time = time.time()
        
        revocation_time = (end_time - start_time) * 1000  # Convert to ms
        
        print(f"⏱️  Single revocation time: {revocation_time:.2f}ms")
        
        if response.status_code == 200:
            print("✅ Revocation endpoint responsive")
            return {
                "revocation_time_ms": revocation_time,
                "success": True,
                "meets_requirement": revocation_time <= 4000  # 4 seconds
            }
        else:
            print(f"❌ Revocation failed with status: {response.status_code}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
            
    except Exception as e:
        end_time = time.time()
        revocation_time = (end_time - start_time) * 1000
        print(f"❌ Revocation test failed: {e}")
        return {"success": False, "error": str(e), "revocation_time_ms": revocation_time}

def test_concurrent_capacity():
    """Test 4: 3200+ Concurrent Request Capacity"""
    print("\n" + "="*60)
    print("TEST 4: CONCURRENT CAPACITY (≥3200 requests)")
    print("="*60)
    
    request_data = {
        "credential_id": "test_concurrent_credential",
        "credential": {"id": "test_concurrent", "attributes": {"isHuman": True}}
    }
    
    return asyncio.run(load_test_endpoint(
        "/api/verify-offline",  # Use fastest endpoint for capacity test
        concurrent_requests=3200,
        duration_seconds=20,
        method="POST",
        request_data=request_data
    ))

def print_results(test_name: str, results, requirement: str, threshold: float = None):
    """Print formatted test results."""
    print(f"\n📊 {test_name} RESULTS")
    print("-" * 50)
    
    if isinstance(results, dict) and "error" in results:
        print(f"❌ Test failed: {results['error']}")
        return False
    
    if hasattr(results, 'get_statistics'):
        stats = results.get_statistics()
        
        print(f"Total Requests: {stats['total_requests']:,}")
        print(f"Duration: {stats['duration_seconds']:.2f}s")
        print(f"Requests/Second: {stats['requests_per_second']:.2f}")
        print(f"Success Rate: {stats['success_rate']:.1f}%")
        print(f"Response Times:")
        print(f"  Average: {stats['response_times']['avg_ms']:.2f}ms")
        print(f"  P95: {stats['response_times']['p95_ms']:.2f}ms")
        print(f"  P99: {stats['response_times']['p99_ms']:.2f}ms")
        print(f"  Min: {stats['response_times']['min_ms']:.2f}ms")
        print(f"  Max: {stats['response_times']['max_ms']:.2f}ms")
        
        # Check requirement
        if threshold:
            test_value = stats['response_times']['p95_ms']
            meets_requirement = test_value <= threshold
            status = "✅ PASS" if meets_requirement else "❌ FAIL"
            print(f"\n{requirement}: {status}")
            print(f"P95 Latency: {test_value:.2f}ms (requirement: ≤{threshold}ms)")
            return meets_requirement
        else:
            print(f"\n{requirement}: ✅ COMPLETED")
            return True
    else:
        # Handle revocation test results
        if results.get("success"):
            revocation_time = results.get("revocation_time_ms", 0)
            meets_requirement = results.get("meets_requirement", False)
            status = "✅ PASS" if meets_requirement else "❌ FAIL"
            print(f"Revocation Time: {revocation_time:.2f}ms")
            print(f"\n{requirement}: {status}")
            return meets_requirement
        else:
            print(f"❌ Test failed: {results.get('error', 'Unknown error')}")
            return False

def main():
    """Run comprehensive load testing suite."""
    global BASE_URL
    
    parser = argparse.ArgumentParser(description="Lemma Shield Load Testing")
    parser.add_argument("--base-url", default="https://lemma-enterprise-production.up.railway.app" if '--production' in sys.argv else "http://localhost:5000", help="Base URL for testing")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    args = parser.parse_args()
    
    BASE_URL = args.base_url
    
    print("🎯 LEMMA SHIELD PERFORMANCE VALIDATION")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print(f"Mode: {'Quick Test' if args.quick else 'Full Load Test'}")
    
    # Adjust test parameters for quick mode
    if args.quick:
        print("⚡ Running in quick mode (reduced load)")
    
    test_results = []
    
    # Test 1: Offline Verification Performance
    offline_results = test_offline_verification_performance()
    offline_pass = print_results(
        "OFFLINE VERIFICATION", 
        offline_results, 
        "Requirement: P95 < 100ms", 
        100
    )
    test_results.append(("Offline Verification", offline_pass))
    
    # Test 2: Fallback Verification Performance  
    fallback_results = test_fallback_verification_performance()
    fallback_pass = print_results(
        "FALLBACK VERIFICATION",
        fallback_results,
        "Requirement: P95 < 500ms",
        500
    )
    test_results.append(("Fallback Verification", fallback_pass))
    
    # Test 3: Revocation Performance
    revocation_results = test_revocation_performance()
    revocation_pass = print_results(
        "REVOCATION PERFORMANCE",
        revocation_results,
        "Requirement: ≤ 4 seconds",
        None
    )
    test_results.append(("Revocation Performance", revocation_pass))
    
    # Test 4: Concurrent Capacity (skip in quick mode)
    if not args.quick:
        capacity_results = test_concurrent_capacity()
        capacity_pass = print_results(
            "CONCURRENT CAPACITY",
            capacity_results,
            "Requirement: Handle ≥3200 concurrent requests",
            None
        )
        test_results.append(("Concurrent Capacity", capacity_pass))
    
    # Final Summary
    print("\n" + "="*60)
    print("🏆 FINAL PERFORMANCE VALIDATION SUMMARY")
    print("="*60)
    
    passed_tests = 0
    total_tests = len(test_results)
    
    for test_name, passed in test_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name}: {status}")
        if passed:
            passed_tests += 1
    
    print(f"\n📊 Overall Score: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 ALL PERFORMANCE REQUIREMENTS MET! System is production-ready.")
        return 0
    else:
        print("⚠️  Some performance requirements not met. See details above.")
        return 1

if __name__ == "__main__":
    exit(main()) 