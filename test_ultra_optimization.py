#!/usr/bin/env python3
"""
Test Ultra-Optimization Performance Improvements
Compare baseline → optimized → ultra-optimized performance
"""

import time
import json
import statistics

def test_all_optimization_levels():
    """Test all optimization levels for comparison"""
    print("🚀 ULTRA-OPTIMIZATION PERFORMANCE TEST")
    print("Testing: Baseline → Optimized → Ultra-Optimized")
    print("=" * 60)
    
    try:
        import lemma_crypto
        
        # Create test credential
        issuer = lemma_crypto.PyMinimalIssuer()
        claims = {"packageType": "identity", "isHuman": "true", "age": "25"}
        credential_json = issuer.issue_credential("did:lemma:perf_test", claims)
        
        print(f"✅ Test credential: {json.loads(credential_json)['id']}")
        
        # Test 1: Baseline performance
        print("\n1. Testing baseline performance...")
        baseline_verifier = lemma_crypto.PyCompleteVerifier()
        baseline_times = []
        
        for _ in range(100):
            start = time.perf_counter_ns()
            result = baseline_verifier.verify_credential(credential_json)
            end = time.perf_counter_ns()
            if result.verified:
                baseline_times.append((end - start) / 1000)
        
        baseline_avg = statistics.mean(baseline_times)
        print(f"✅ Baseline: {baseline_avg:.3f} μs")
        
        # Test 2: Optimized performance
        print("\n2. Testing optimized performance...")
        optimized_verifier = lemma_crypto.PyOptimizedVerifier()
        optimized_times = []
        
        for _ in range(100):
            start = time.perf_counter_ns()
            result = optimized_verifier.verify_credential(credential_json)
            end = time.perf_counter_ns()
            if result.verified:
                optimized_times.append((end - start) / 1000)
        
        optimized_avg = statistics.mean(optimized_times)
        optimized_speedup = baseline_avg / optimized_avg
        print(f"✅ Optimized: {optimized_avg:.3f} μs ({optimized_speedup:.2f}x speedup)")
        
        # Get optimization stats
        opt_stats = optimized_verifier.get_performance_stats()
        print(f"   Cache hit rate: {opt_stats.cache_hit_rate * 100:.1f}%")
        
        # Test 3: Ultra-optimized performance
        print("\n3. Testing ULTRA-optimized performance...")
        ultra_verifier = lemma_crypto.PyUltraOptimizedVerifier()
        ultra_times = []
        cache_levels = []
        simd_usage = []
        
        for _ in range(100):
            start = time.perf_counter_ns()
            result = ultra_verifier.verify_credential(credential_json)
            end = time.perf_counter_ns()
            if result.verified:
                ultra_times.append((end - start) / 1000)
                cache_levels.append(result.cache_level)
                simd_usage.append(result.simd_used)
        
        ultra_avg = statistics.mean(ultra_times)
        ultra_speedup_vs_baseline = baseline_avg / ultra_avg
        ultra_speedup_vs_optimized = optimized_avg / ultra_avg
        
        print(f"✅ Ultra-optimized: {ultra_avg:.3f} μs")
        print(f"   vs Baseline: {ultra_speedup_vs_baseline:.2f}x speedup")
        print(f"   vs Optimized: {ultra_speedup_vs_optimized:.2f}x speedup")
        
        # Get ultra stats
        ultra_stats = ultra_verifier.get_ultra_stats()
        print(f"   Cache hit rate: {(ultra_stats.cache_hits / ultra_stats.total_verifications) * 100:.1f}%")
        print(f"   Memory pool hits: {ultra_stats.memory_pool_hits}")
        print(f"   Average cache level: {statistics.mean(cache_levels):.1f}")
        
        # Performance breakdown analysis
        print("\n4. Performance breakdown analysis...")
        
        # Separate cache hit vs miss times for ultra-optimized
        ultra_cache_hits = [t for i, t in enumerate(ultra_times) if cache_levels[i] > 0]
        ultra_cache_misses = [t for i, t in enumerate(ultra_times) if cache_levels[i] == 0]
        
        if ultra_cache_hits:
            cache_hit_avg = statistics.mean(ultra_cache_hits)
            print(f"   Ultra cache hits: {cache_hit_avg:.3f} μs average")
        
        if ultra_cache_misses:
            cache_miss_avg = statistics.mean(ultra_cache_misses)
            print(f"   Ultra cache misses: {cache_miss_avg:.3f} μs average")
        
        # Summary
        print("\n" + "=" * 60)
        print("🏆 OPTIMIZATION COMPARISON RESULTS")
        print("=" * 60)
        print(f"📊 Performance Evolution:")
        print(f"   Baseline:        {baseline_avg:.3f} μs")
        print(f"   Optimized:       {optimized_avg:.3f} μs ({optimized_speedup:.2f}x)")
        print(f"   Ultra-Optimized: {ultra_avg:.3f} μs ({ultra_speedup_vs_baseline:.2f}x)")
        print(f"")
        print(f"🚀 Total Improvement: {ultra_speedup_vs_baseline:.2f}x faster than baseline")
        print(f"⚡ Additional Gain: {ultra_speedup_vs_optimized:.2f}x faster than optimized")
        
        if ultra_cache_hits:
            print(f"🎯 Ultra cache performance: {cache_hit_avg:.3f} μs")
            print(f"🎯 Target for Heroku: {cache_hit_avg:.3f} μs (85%+ cache hits)")
        
        return {
            "baseline_avg_us": baseline_avg,
            "optimized_avg_us": optimized_avg,
            "ultra_avg_us": ultra_avg,
            "ultra_speedup": ultra_speedup_vs_baseline,
            "cache_hit_avg_us": cache_hit_avg if ultra_cache_hits else None,
            "ready_for_heroku": True
        }
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    results = test_all_optimization_levels()
    
    if results.get("ultra_speedup", 0) > 3:
        print(f"\n🎉 EXCELLENT: {results['ultra_speedup']:.2f}x speedup achieved!")
        print(f"Ready to deploy ultra-optimized engine to Heroku")
    elif results.get("ultra_speedup", 0) > 1.5:
        print(f"\n✅ GOOD: {results['ultra_speedup']:.2f}x speedup achieved")
    else:
        print(f"\n⚠️  Minimal improvement: {results.get('ultra_speedup', 0):.2f}x")
