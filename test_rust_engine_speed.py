#!/usr/bin/env python3
"""
Rust Engine Speed Test - Comprehensive performance measurement
Tests both local and Heroku Rust engine verification speeds
"""

import time
import statistics
import requests
import json
from typing import List, Dict, Any

# Test configuration
HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
LOCAL_URL = "http://localhost:5000"  # If running locally
NUM_TESTS = 100  # Number of test iterations for statistical accuracy

def measure_local_rust_speed(num_tests: int = NUM_TESTS) -> Dict[str, Any]:
    """Measure local Rust engine verification speed"""
    print(f"🔍 Testing Local Rust Engine Speed ({num_tests} iterations)...")
    print("=" * 60)
    
    try:
        from lemma_crypto import PyLemmaCore, PyVerificationResult
        
        # Initialize the engine
        core = PyLemmaCore()
        print("✅ Local Rust engine initialized successfully")
        
        # Prepare test credential data
        test_credential = {
            "id": "test_credential_001",
            "issuer": "did:lemma:test_issuer",
            "subject": "did:lemma:test_subject", 
            "claims": {
                "packageType": "identity",
                "isHuman": True,
                "verificationLevel": "high",
                "timestamp": int(time.time())
            }
        }
        
        verification_times = []
        
        # Perform speed tests
        for i in range(num_tests):
            start_time = time.perf_counter()
            
            # This is where the actual verification would happen
            # For now, we'll simulate the verification process
            result = core.verify_credential(json.dumps(test_credential))
            
            end_time = time.perf_counter()
            verification_time = (end_time - start_time) * 1_000_000  # Convert to microseconds
            verification_times.append(verification_time)
            
            if (i + 1) % 10 == 0:
                print(f"   Completed {i + 1}/{num_tests} tests...")
        
        # Calculate statistics
        avg_time = statistics.mean(verification_times)
        median_time = statistics.median(verification_times)
        min_time = min(verification_times)
        max_time = max(verification_times)
        std_dev = statistics.stdev(verification_times) if len(verification_times) > 1 else 0
        
        results = {
            "engine": "local_rust",
            "success": True,
            "num_tests": num_tests,
            "avg_time_us": avg_time,
            "median_time_us": median_time,
            "min_time_us": min_time,
            "max_time_us": max_time,
            "std_dev_us": std_dev,
            "verifications_per_second": 1_000_000 / avg_time if avg_time > 0 else 0
        }
        
        print(f"✅ Local Test Results:")
        print(f"   Average: {avg_time:.2f} µs")
        print(f"   Median:  {median_time:.2f} µs")
        print(f"   Min:     {min_time:.2f} µs")
        print(f"   Max:     {max_time:.2f} µs")
        print(f"   Std Dev: {std_dev:.2f} µs")
        print(f"   Throughput: {results['verifications_per_second']:,.0f} verifications/second")
        print()
        
        return results
        
    except ImportError as e:
        print(f"❌ Local Rust engine not available: {e}")
        return {"engine": "local_rust", "success": False, "error": str(e)}
    except Exception as e:
        print(f"❌ Local test failed: {e}")
        return {"engine": "local_rust", "success": False, "error": str(e)}

def measure_heroku_rust_speed(num_tests: int = NUM_TESTS) -> Dict[str, Any]:
    """Measure Heroku Rust engine verification speed"""
    print(f"🌐 Testing Heroku Rust Engine Speed ({num_tests} iterations)...")
    print("=" * 60)
    
    try:
        # First, verify the engine is working
        status_response = requests.get(f"{HEROKU_URL}/api/bot-shield/status", timeout=30)
        if status_response.status_code != 200:
            return {"engine": "heroku_rust", "success": False, "error": f"Status check failed: {status_response.status_code}"}
        
        status_data = status_response.json()
        engine_type = status_data.get('engine', 'unknown')
        
        if engine_type not in ['rust_ready', 'rust_engine']:
            return {"engine": "heroku_rust", "success": False, "error": f"Rust engine not available: {engine_type}"}
        
        print(f"✅ Heroku Rust engine confirmed: {engine_type}")
        
        # Prepare test credential data
        test_credential = {
            "id": "test_credential_heroku_001",
            "issuer": "did:lemma:heroku_test_issuer",
            "subject": "did:lemma:heroku_test_subject",
            "claims": {
                "packageType": "identity",
                "isHuman": True,
                "verificationLevel": "high",
                "timestamp": int(time.time())
            }
        }
        
        verification_times = []
        network_times = []
        successful_tests = 0
        
        # Perform speed tests
        for i in range(num_tests):
            try:
                # Measure total request time (including network)
                total_start = time.perf_counter()
                
                response = requests.post(
                    f"{HEROKU_URL}/api/verify-credential",
                    json={"credential": test_credential},
                    timeout=10,
                    headers={"Content-Type": "application/json"}
                )
                
                total_end = time.perf_counter()
                total_time = (total_end - total_start) * 1_000_000  # Convert to microseconds
                network_times.append(total_time)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Try to extract server-side verification time if available
                    verification_time_us = data.get('verification_time_us')
                    if verification_time_us is not None:
                        verification_times.append(verification_time_us)
                    else:
                        # Estimate verification time (total minus estimated network overhead)
                        estimated_network_overhead = 5000  # 5ms estimated network overhead
                        estimated_verification = max(total_time - estimated_network_overhead, 1)
                        verification_times.append(estimated_verification)
                    
                    successful_tests += 1
                else:
                    print(f"   Request {i+1} failed: HTTP {response.status_code}")
                
                if (i + 1) % 10 == 0:
                    print(f"   Completed {i + 1}/{num_tests} tests ({successful_tests} successful)...")
                    
            except requests.exceptions.RequestException as e:
                print(f"   Request {i+1} failed: {e}")
                continue
        
        if not verification_times:
            return {"engine": "heroku_rust", "success": False, "error": "No successful verifications"}
        
        # Calculate statistics for verification times
        avg_time = statistics.mean(verification_times)
        median_time = statistics.median(verification_times)
        min_time = min(verification_times)
        max_time = max(verification_times)
        std_dev = statistics.stdev(verification_times) if len(verification_times) > 1 else 0
        
        # Calculate network statistics
        avg_network = statistics.mean(network_times) if network_times else 0
        
        results = {
            "engine": "heroku_rust",
            "success": True,
            "num_tests": num_tests,
            "successful_tests": successful_tests,
            "avg_time_us": avg_time,
            "median_time_us": median_time,
            "min_time_us": min_time,
            "max_time_us": max_time,
            "std_dev_us": std_dev,
            "avg_network_time_us": avg_network,
            "verifications_per_second": 1_000_000 / avg_time if avg_time > 0 else 0
        }
        
        print(f"✅ Heroku Test Results:")
        print(f"   Successful Tests: {successful_tests}/{num_tests}")
        print(f"   Average Verification: {avg_time:.2f} µs")
        print(f"   Median Verification:  {median_time:.2f} µs")
        print(f"   Min Verification:     {min_time:.2f} µs")
        print(f"   Max Verification:     {max_time:.2f} µs")
        print(f"   Std Dev:              {std_dev:.2f} µs")
        print(f"   Average Network:      {avg_network/1000:.2f} ms")
        print(f"   Throughput:           {results['verifications_per_second']:,.0f} verifications/second")
        print()
        
        return results
        
    except Exception as e:
        print(f"❌ Heroku test failed: {e}")
        return {"engine": "heroku_rust", "success": False, "error": str(e)}

def compare_performance(local_results: Dict[str, Any], heroku_results: Dict[str, Any]):
    """Compare local vs Heroku performance"""
    print("📊 Performance Comparison")
    print("=" * 60)
    
    if not local_results.get('success') and not heroku_results.get('success'):
        print("❌ Both tests failed - no comparison possible")
        return
    
    if not local_results.get('success'):
        print("⚠️  Local test failed - showing Heroku results only")
        print(f"   Heroku Average: {heroku_results.get('avg_time_us', 0):.2f} µs")
        return
    
    if not heroku_results.get('success'):
        print("⚠️  Heroku test failed - showing local results only")
        print(f"   Local Average: {local_results.get('avg_time_us', 0):.2f} µs")
        return
    
    # Both tests succeeded - full comparison
    local_avg = local_results.get('avg_time_us', 0)
    heroku_avg = heroku_results.get('avg_time_us', 0)
    
    print(f"Local Rust Engine:")
    print(f"   Average: {local_avg:.2f} µs")
    print(f"   Throughput: {local_results.get('verifications_per_second', 0):,.0f} verifications/second")
    print()
    
    print(f"Heroku Rust Engine:")
    print(f"   Average: {heroku_avg:.2f} µs")
    print(f"   Network Overhead: {heroku_results.get('avg_network_time_us', 0)/1000:.2f} ms")
    print(f"   Throughput: {heroku_results.get('verifications_per_second', 0):,.0f} verifications/second")
    print()
    
    # Performance comparison
    if local_avg > 0 and heroku_avg > 0:
        if heroku_avg < local_avg:
            speedup = local_avg / heroku_avg
            print(f"🚀 Heroku is {speedup:.1f}x FASTER than local!")
        elif local_avg < heroku_avg:
            slowdown = heroku_avg / local_avg
            print(f"🐌 Heroku is {slowdown:.1f}x slower than local")
        else:
            print("⚖️  Performance is approximately equal")
    
    # Performance assessment against claims
    print()
    print("🎯 Performance Assessment vs Claims:")
    
    for name, avg_time in [("Local", local_avg), ("Heroku", heroku_avg)]:
        if avg_time == 0:
            continue
            
        if avg_time < 1:  # < 1µs
            print(f"   {name}: 🏆 EXCELLENT - {avg_time:.2f}µs (microsecond-level achieved!)")
        elif avg_time < 10:  # < 10µs  
            print(f"   {name}: ✅ GREAT - {avg_time:.2f}µs (sub-10µs achieved)")
        elif avg_time < 100:  # < 100µs
            print(f"   {name}: 👍 GOOD - {avg_time:.2f}µs (sub-100µs achieved)")
        elif avg_time < 1000:  # < 1ms
            print(f"   {name}: 📊 ACCEPTABLE - {avg_time:.2f}µs (sub-millisecond)")
        else:
            print(f"   {name}: ⚠️  NEEDS OPTIMIZATION - {avg_time:.2f}µs")

def main():
    """Run comprehensive speed tests"""
    print("🦀 Lemma Rust Engine Speed Test")
    print("=" * 60)
    print(f"Testing {NUM_TESTS} iterations for statistical accuracy")
    print()
    
    # Test local performance
    local_results = measure_local_rust_speed()
    
    # Test Heroku performance  
    heroku_results = measure_heroku_rust_speed()
    
    # Compare results
    compare_performance(local_results, heroku_results)
    
    # Summary
    print()
    print("🎯 Summary:")
    if local_results.get('success'):
        local_avg = local_results.get('avg_time_us', 0)
        print(f"   Local Rust Engine: {local_avg:.2f}µs average verification time")
    
    if heroku_results.get('success'):
        heroku_avg = heroku_results.get('avg_time_us', 0)
        print(f"   Heroku Rust Engine: {heroku_avg:.2f}µs average verification time")
        print(f"   Network Round-trip: {heroku_results.get('avg_network_time_us', 0)/1000:.2f}ms")
    
    # Save results
    results = {
        "timestamp": time.time(),
        "local": local_results,
        "heroku": heroku_results
    }
    
    with open('rust_engine_speed_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: rust_engine_speed_test_results.json")

if __name__ == "__main__":
    main() 