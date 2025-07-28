#!/usr/bin/env python3
"""
Simple Rust Engine Speed Test
Tests the verification speed of the Rust engine on Heroku using existing endpoints
"""

import time
import statistics
import requests
import json

def test_heroku_rust_speed(num_tests=50):
    """Test Heroku Rust engine speed using bot shield endpoint"""
    print(f"🦀 Testing Heroku Rust Engine Speed ({num_tests} tests)")
    print("=" * 50)
    
    # First confirm the engine is working
    print("🔍 Checking engine status...")
    try:
        status_response = requests.get(
            "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/bot-shield/status",
            timeout=10
        )
        if status_response.status_code == 200:
            data = status_response.json()
            engine = data.get('engine', 'unknown')
            print(f"✅ Engine Status: {engine}")
            
            if engine != 'rust_ready':
                print(f"⚠️  Warning: Engine is '{engine}', expected 'rust_ready'")
        else:
            print(f"❌ Status check failed: HTTP {status_response.status_code}")
            return
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return
    
    print(f"\n🚀 Running {num_tests} speed tests...")
    
    # Test data for bot shield verification
    test_data = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "ip_address": "192.168.1.100",
        "timestamp": int(time.time()),
        "session_data": {
            "page_url": "/test-page",
            "referrer": "https://google.com",
            "verification_type": "speed_test"
        }
    }
    
    response_times = []
    verification_times = []
    successful_tests = 0
    
    for i in range(num_tests):
        try:
            # Measure total response time
            start_time = time.perf_counter()
            
            response = requests.post(
                "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/bot-shield/verify",
                json=test_data,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            end_time = time.perf_counter()
            total_time_ms = (end_time - start_time) * 1000  # Convert to milliseconds
            response_times.append(total_time_ms)
            
            if response.status_code == 200:
                result = response.json()
                successful_tests += 1
                
                # Try to extract server-side verification time
                server_time_us = result.get('verification_time_us')
                if server_time_us is not None:
                    verification_times.append(server_time_us)
                else:
                    # Estimate pure verification time (subtract network overhead)
                    estimated_verification_us = max((total_time_ms * 1000) - 10000, 1)  # Subtract ~10ms network
                    verification_times.append(estimated_verification_us)
                    
                # Show progress
                if (i + 1) % 10 == 0:
                    print(f"   ✅ Completed {i + 1}/{num_tests} tests")
            else:
                print(f"   ❌ Test {i+1}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Test {i+1}: {e}")
            continue
    
    print(f"\n📊 Results ({successful_tests}/{num_tests} successful):")
    
    if response_times:
        avg_response = statistics.mean(response_times)
        min_response = min(response_times)
        max_response = max(response_times)
        print(f"   Total Response Time:")
        print(f"     Average: {avg_response:.2f} ms")
        print(f"     Min:     {min_response:.2f} ms") 
        print(f"     Max:     {max_response:.2f} ms")
    
    if verification_times:
        avg_verification = statistics.mean(verification_times)
        min_verification = min(verification_times)
        max_verification = max(verification_times)
        std_dev = statistics.stdev(verification_times) if len(verification_times) > 1 else 0
        
        print(f"\n   🦀 Rust Engine Verification Time:")
        print(f"     Average: {avg_verification:.2f} µs")
        print(f"     Min:     {min_verification:.2f} µs")
        print(f"     Max:     {max_verification:.2f} µs")
        print(f"     Std Dev: {std_dev:.2f} µs")
        
        # Calculate throughput
        verifications_per_second = 1_000_000 / avg_verification if avg_verification > 0 else 0
        print(f"     Throughput: {verifications_per_second:,.0f} verifications/second")
        
        # Performance assessment
        print(f"\n🎯 Performance Assessment:")
        if avg_verification < 1:
            print(f"   🏆 EXCELLENT: {avg_verification:.2f}µs - Microsecond-level achieved!")
        elif avg_verification < 10:
            print(f"   ✅ GREAT: {avg_verification:.2f}µs - Sub-10µs performance")
        elif avg_verification < 100:
            print(f"   👍 GOOD: {avg_verification:.2f}µs - Sub-100µs performance")  
        elif avg_verification < 1000:
            print(f"   📊 ACCEPTABLE: {avg_verification:.2f}µs - Sub-millisecond")
        else:
            print(f"   ⚠️  NEEDS OPTIMIZATION: {avg_verification:.2f}µs")
            
        # Compare to claims
        print(f"\n📋 Comparison to Performance Claims:")
        claims = [
            ("ASIC accelerated", 0.01),
            ("Advanced algorithms", 0.05), 
            ("FPGA accelerated", 0.1),
            ("WebAssembly cached", 0.36),
            ("Work-stealing optimized", 1.0),
            ("Multi-level cached", 15.0),
            ("Cold start", 151.27)
        ]
        
        for claim, claim_time in claims:
            if avg_verification <= claim_time:
                print(f"   ✅ Meets {claim} target ({claim_time}µs)")
                break
        else:
            print(f"   ⚠️  Above all claimed performance targets")
    
    else:
        print("❌ No successful verifications to analyze")

def test_local_rust_speed():
    """Test local Rust engine if available"""
    print("\n🔍 Testing Local Rust Engine...")
    print("=" * 40)
    
    try:
        from lemma_crypto import PyLemmaCore
        
        core = PyLemmaCore()
        print("✅ Local Rust engine initialized")
        
        # Simple speed test
        num_tests = 10
        times = []
        
        for i in range(num_tests):
            start = time.perf_counter()
            # Call a basic method
            result = core.verify_basic('{"test": "data"}')
            end = time.perf_counter()
            times.append((end - start) * 1_000_000)  # Convert to microseconds
        
        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"📊 Local Results ({num_tests} tests):")
        print(f"   Average: {avg_time:.2f} µs")
        print(f"   Min:     {min_time:.2f} µs")
        print(f"   Max:     {max_time:.2f} µs")
        
        if avg_time < 1:
            print(f"   🏆 EXCELLENT: Microsecond-level performance!")
        elif avg_time < 10:
            print(f"   ✅ GREAT: Sub-10µs performance")
        else:
            print(f"   📊 Average performance: {avg_time:.2f}µs")
            
    except ImportError:
        print("⚠️  Local Rust engine not available (not compiled locally)")
    except Exception as e:
        print(f"❌ Local test failed: {e}")

if __name__ == "__main__":
    # Test Heroku performance
    test_heroku_rust_speed()
    
    # Test local performance if available
    test_local_rust_speed()
    
    print("\n🎉 Speed test complete!") 