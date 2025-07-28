#!/usr/bin/env python3
"""
Accurate Rust Engine Speed Test
Tests the actual verification speed using the real endpoints and timing data
"""

import time
import statistics
import requests
import json

def test_heroku_rust_engine(num_tests=100):
    """Test Heroku Rust engine speed using actual endpoints"""
    print(f"🦀 Heroku Rust Engine Speed Test ({num_tests} iterations)")
    print("=" * 60)
    
    # Confirm Rust engine status
    print("🔍 Checking Rust engine status...")
    try:
        response = requests.get(
            "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/shield-status",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            shield_status = data.get('shield_status', {})
            
            print(f"✅ Engine initialized: {shield_status.get('engine_initialized', False)}")
            print(f"✅ Rust engine available: {shield_status.get('rust_engine_available', False)}")
            print(f"✅ Shield enabled: {shield_status.get('shield_enabled', False)}")
            print(f"✅ Version: {shield_status.get('version', 'unknown')}")
            
            # Check if we got timing data
            user_check = data.get('user_credential_check', {})
            if 'verification_time_ns' in user_check:
                initial_time_ns = user_check['verification_time_ns']
                print(f"🎯 Initial timing sample: {initial_time_ns/1000:.2f} µs")
            
            if not shield_status.get('rust_engine_available'):
                print("❌ Rust engine is not available!")
                return
        else:
            print(f"❌ Status check failed: HTTP {response.status_code}")
            return
            
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return
    
    print(f"\n🚀 Running {num_tests} verification speed tests...")
    
    # Collect timing data
    verification_times_ns = []
    response_times_ms = []
    successful_tests = 0
    
    for i in range(num_tests):
        try:
            # Measure total response time
            start_time = time.perf_counter()
            
            response = requests.get(
                "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/shield-status",
                timeout=10
            )
            
            end_time = time.perf_counter()
            total_time_ms = (end_time - start_time) * 1000
            response_times_ms.append(total_time_ms)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract the actual Rust engine verification time
                user_check = data.get('user_credential_check', {})
                verification_time_ns = user_check.get('verification_time_ns')
                
                if verification_time_ns is not None:
                    verification_times_ns.append(verification_time_ns)
                    successful_tests += 1
                else:
                    print(f"   ⚠️  Test {i+1}: No timing data in response")
            else:
                print(f"   ❌ Test {i+1}: HTTP {response.status_code}")
                
            # Progress indicator
            if (i + 1) % 20 == 0:
                print(f"   ✅ Completed {i + 1}/{num_tests} tests")
                
        except Exception as e:
            print(f"   ❌ Test {i+1}: {e}")
            continue
    
    print(f"\n📊 Results Analysis ({successful_tests}/{num_tests} successful):")
    
    if not verification_times_ns:
        print("❌ No timing data collected!")
        return
    
    # Convert to microseconds for analysis
    verification_times_us = [ns / 1000.0 for ns in verification_times_ns]
    
    # Calculate statistics
    avg_time_us = statistics.mean(verification_times_us)
    median_time_us = statistics.median(verification_times_us)
    min_time_us = min(verification_times_us)
    max_time_us = max(verification_times_us)
    std_dev_us = statistics.stdev(verification_times_us) if len(verification_times_us) > 1 else 0
    
    # Network statistics
    avg_response_ms = statistics.mean(response_times_ms) if response_times_ms else 0
    
    print(f"\n🦀 Rust Engine Verification Performance:")
    print(f"   Average:    {avg_time_us:.3f} µs")
    print(f"   Median:     {median_time_us:.3f} µs")
    print(f"   Min:        {min_time_us:.3f} µs")
    print(f"   Max:        {max_time_us:.3f} µs")
    print(f"   Std Dev:    {std_dev_us:.3f} µs")
    
    # Calculate throughput
    verifications_per_second = 1_000_000 / avg_time_us if avg_time_us > 0 else 0
    print(f"   Throughput: {verifications_per_second:,.0f} verifications/second")
    
    print(f"\n🌐 Network Performance:")
    print(f"   Avg Response: {avg_response_ms:.2f} ms")
    print(f"   Network Overhead: {avg_response_ms:.2f} ms vs {avg_time_us/1000:.3f} ms verification")
    
    # Performance assessment
    print(f"\n🎯 Performance Assessment:")
    if avg_time_us < 1:
        print(f"   🏆 OUTSTANDING: {avg_time_us:.3f}µs - Sub-microsecond achieved!")
        performance_level = "OUTSTANDING"
    elif avg_time_us < 10:
        print(f"   🚀 EXCELLENT: {avg_time_us:.3f}µs - Single-digit microseconds!")
        performance_level = "EXCELLENT"
    elif avg_time_us < 100:
        print(f"   ✅ GREAT: {avg_time_us:.3f}µs - Sub-100µs performance")
        performance_level = "GREAT"
    elif avg_time_us < 1000:
        print(f"   👍 GOOD: {avg_time_us:.3f}µs - Sub-millisecond")
        performance_level = "GOOD"
    else:
        print(f"   ⚠️  NEEDS OPTIMIZATION: {avg_time_us:.3f}µs")
        performance_level = "NEEDS_OPTIMIZATION"
    
    # Compare to performance claims from README
    print(f"\n📋 Comparison to Performance Claims:")
    performance_targets = [
        ("ASIC accelerated", 0.01, "🔥 Ultimate hardware"),
        ("Advanced algorithms", 0.05, "🚀 Predictive caching"),
        ("FPGA accelerated", 0.1, "⚡ Configurable hardware"),
        ("WebAssembly cached", 0.36, "🌐 Browser optimized"),
        ("Work-stealing optimized", 1.0, "🔧 Multi-threading"),
        ("Multi-level cached", 15.0, "📦 Standard caching"),
        ("Same-issuer verification", 45.0, "📝 Batch processing"),
        ("Cold start", 151.27, "❄️  Initial verification")
    ]
    
    achieved_targets = []
    for target_name, target_us, description in performance_targets:
        if avg_time_us <= target_us:
            print(f"   ✅ MEETS {target_name} target ({target_us}µs) - {description}")
            achieved_targets.append(target_name)
        else:
            print(f"   ❌ Above {target_name} target ({target_us}µs)")
            break
    
    # Performance summary
    print(f"\n🎉 Performance Summary:")
    print(f"   🦀 Heroku Rust Engine: {avg_time_us:.3f}µs average verification")
    print(f"   📊 Performance Level: {performance_level}")
    print(f"   🎯 Targets Achieved: {len(achieved_targets)}/{len(performance_targets)}")
    
    if achieved_targets:
        best_target = achieved_targets[0]
        print(f"   🏆 Best Performance Category: {best_target}")
    
    # Consistency analysis
    if std_dev_us / avg_time_us < 0.1:
        print(f"   ✅ CONSISTENT: Low variability ({std_dev_us/avg_time_us*100:.1f}% coefficient of variation)")
    elif std_dev_us / avg_time_us < 0.3:
        print(f"   📊 ACCEPTABLE: Moderate variability ({std_dev_us/avg_time_us*100:.1f}% coefficient of variation)")
    else:
        print(f"   ⚠️  VARIABLE: High variability ({std_dev_us/avg_time_us*100:.1f}% coefficient of variation)")
    
    # Save detailed results
    results = {
        "timestamp": time.time(),
        "test_config": {
            "num_tests": num_tests,
            "successful_tests": successful_tests,
            "endpoint": "/shield-status"
        },
        "performance": {
            "avg_time_us": avg_time_us,
            "median_time_us": median_time_us,
            "min_time_us": min_time_us,
            "max_time_us": max_time_us,
            "std_dev_us": std_dev_us,
            "verifications_per_second": verifications_per_second
        },
        "network": {
            "avg_response_ms": avg_response_ms
        },
        "assessment": {
            "performance_level": performance_level,
            "targets_achieved": achieved_targets
        },
        "raw_data": {
            "verification_times_ns": verification_times_ns,
            "response_times_ms": response_times_ms
        }
    }
    
    with open('heroku_rust_speed_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: heroku_rust_speed_test_results.json")

def test_local_rust_engine():
    """Test local Rust engine if available"""
    print(f"\n🔍 Local Rust Engine Test")
    print("=" * 40)
    
    try:
        from lemma_crypto import PyLemmaCore
        
        core = PyLemmaCore()
        print("✅ Local Rust engine initialized successfully")
        
        # Run basic speed test
        num_tests = 50
        times_us = []
        
        test_data = '{"test": "verification", "timestamp": ' + str(int(time.time())) + '}'
        
        print(f"🚀 Running {num_tests} local tests...")
        
        for i in range(num_tests):
            start = time.perf_counter()
            result = core.verify_basic(test_data)
            end = time.perf_counter()
            times_us.append((end - start) * 1_000_000)  # Convert to microseconds
        
        avg_time = statistics.mean(times_us)
        median_time = statistics.median(times_us)
        min_time = min(times_us)
        max_time = max(times_us)
        std_dev = statistics.stdev(times_us) if len(times_us) > 1 else 0
        
        print(f"\n🦀 Local Rust Engine Results:")
        print(f"   Average: {avg_time:.3f} µs")
        print(f"   Median:  {median_time:.3f} µs")
        print(f"   Min:     {min_time:.3f} µs")
        print(f"   Max:     {max_time:.3f} µs")
        print(f"   Std Dev: {std_dev:.3f} µs")
        
        throughput = 1_000_000 / avg_time if avg_time > 0 else 0
        print(f"   Throughput: {throughput:,.0f} verifications/second")
        
        if avg_time < 1:
            print(f"   🏆 OUTSTANDING: Sub-microsecond local performance!")
        elif avg_time < 10:
            print(f"   🚀 EXCELLENT: Single-digit microsecond performance!")
        else:
            print(f"   ✅ GOOD: {avg_time:.3f}µs local performance")
            
    except ImportError:
        print("⚠️  Local Rust engine not available (library not compiled locally)")
    except Exception as e:
        print(f"❌ Local test failed: {e}")

if __name__ == "__main__":
    # Test Heroku Rust engine performance
    test_heroku_rust_engine()
    
    # Test local engine if available
    test_local_rust_engine()
    
    print(f"\n🎯 Speed Test Complete!")
    print("=" * 60)
    print("💡 The verification times shown are from the actual Rust engine")
    print("💡 Network times are separate and much higher (~100-500ms)")
    print("💡 In production, the engine would run client-side for 0µs network time") 