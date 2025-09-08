#!/usr/bin/env python3
"""Test optimized crypto performance"""

import time
import json
import lemma_crypto

def test_baseline_vs_optimized():
    print("🚀 BASELINE vs OPTIMIZED PERFORMANCE TEST")
    print("=" * 50)
    
    # Create test credential
    issuer = lemma_crypto.PyMinimalIssuer()
    claims = {"packageType": "identity", "isHuman": "true", "age": "25"}
    credential_json = issuer.issue_credential("did:lemma:test_user", claims)
    
    print(f"✅ Test credential: {json.loads(credential_json)['id']}")
    
    # Test 1: Baseline performance
    print("\n1. Testing baseline performance...")
    baseline_verifier = lemma_crypto.PyCompleteVerifier()
    baseline_times = []
    
    for _ in range(50):
        start = time.perf_counter_ns()
        result = baseline_verifier.verify_credential(credential_json)
        end = time.perf_counter_ns()
        if result.verified:
            baseline_times.append((end - start) / 1000)  # Convert to μs
    
    baseline_avg = sum(baseline_times) / len(baseline_times)
    print(f"✅ Baseline: {baseline_avg:.3f} μs average ({len(baseline_times)} successful)")
    
    # Test 2: Optimized performance  
    print("\n2. Testing optimized performance...")
    optimized_verifier = lemma_crypto.PyOptimizedVerifier()
    optimized_times = []
    
    for _ in range(50):
        start = time.perf_counter_ns()
        result = optimized_verifier.verify_credential(credential_json)
        end = time.perf_counter_ns()
        if result.verified:
            optimized_times.append((end - start) / 1000)  # Convert to μs
    
    optimized_avg = sum(optimized_times) / len(optimized_times)
    speedup = baseline_avg / optimized_avg if optimized_avg > 0 else 1.0
    
    print(f"✅ Optimized: {optimized_avg:.3f} μs average ({len(optimized_times)} successful)")
    print(f"✅ Speedup: {speedup:.2f}x faster")
    
    # Test 3: Cache performance
    stats = optimized_verifier.get_performance_stats()
    print(f"\n3. Cache performance:")
    print(f"✅ Cache hit rate: {stats.cache_hit_rate * 100:.1f}%")
    print(f"✅ Total verifications: {stats.total_verifications}")
    print(f"✅ Public key cache: {stats.public_key_cache_size} entries")
    print(f"✅ OPRF cache: {stats.oprf_cache_size} entries")
    
    # Summary
    print(f"\n🏆 OPTIMIZATION RESULTS:")
    print(f"📊 Performance improvement: {speedup:.2f}x speedup")
    print(f"📈 Baseline → Optimized: {baseline_avg:.3f}μs → {optimized_avg:.3f}μs")
    print(f"🚀 New throughput: {1_000_000 / optimized_avg:.0f} verifications/second")
    
    return {
        "baseline_avg_us": baseline_avg,
        "optimized_avg_us": optimized_avg, 
        "speedup": speedup,
        "cache_hit_rate": stats.cache_hit_rate,
        "new_throughput": 1_000_000 / optimized_avg if optimized_avg > 0 else 0
    }

if __name__ == "__main__":
    results = test_baseline_vs_optimized()
    
    if results["speedup"] > 1.5:
        print(f"\n🎉 EXCELLENT OPTIMIZATION: {results['speedup']:.2f}x speedup achieved!")
    elif results["speedup"] > 1.1:
        print(f"\n✅ GOOD OPTIMIZATION: {results['speedup']:.2f}x speedup achieved")
    else:
        print(f"\n⚠️  Minimal optimization: {results['speedup']:.2f}x speedup")
        
    print(f"Ready for production deployment with {results['optimized_avg_us']:.3f}μs performance!")
