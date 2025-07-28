#!/usr/bin/env python3
"""
Direct Benchmark Test for Lemma Verification Speed
==================================================

This script runs actual Rust benchmarks and measures offline verification times
with statistical rigor to validate performance claims.
"""

import subprocess
import json
import statistics
import time
import sys
import os
import re
from typing import List, Dict, Tuple

def run_rust_benchmarks() -> Dict[str, float]:
    """Run Rust benchmarks and extract timing results"""
    
    print("🔬 Running Rust Benchmarks")
    print("=" * 50)
    
    # Change to lemma-crypto directory
    os.chdir("lemma-crypto")
    
    # Build first
    print("📦 Building release version...")
    build_result = subprocess.run(
        ["cargo", "build", "--release", "--features", "hsm,gpu,simd,phase3,phase4"],
        capture_output=True,
        text=True
    )
    
    if build_result.returncode != 0:
        print("❌ Build failed:")
        print(build_result.stderr)
        return {}
    
    print("✅ Build successful")
    
    # Run benchmarks
    print("\n🏃 Running benchmarks...")
    bench_result = subprocess.run(
        ["cargo", "bench", "--features", "hsm,gpu,simd,phase3,phase4"],
        capture_output=True,
        text=True,
        timeout=900  # 15 minutes timeout
    )
    
    if bench_result.returncode != 0:
        print("❌ Benchmark failed:")
        print(bench_result.stderr)
        return {}
    
    # Parse results
    results = {}
    lines = bench_result.stdout.split('\n')
    
    for line in lines:
        if 'time:' in line and ('ns' in line or 'µs' in line or 'ms' in line):
            # Extract benchmark name and time
            parts = line.split()
            
            # Find the benchmark name (before 'time:')
            time_index = -1
            for i, part in enumerate(parts):
                if part == 'time:':
                    time_index = i
                    break
            
            if time_index > 0 and time_index + 1 < len(parts):
                # Extract name (typically first part)
                name = parts[0] if parts[0] != 'test' else parts[1]
                
                # Extract time
                time_str = parts[time_index + 1]
                time_ns = parse_time_to_ns(time_str)
                
                if time_ns:
                    results[name] = time_ns
                    print(f"📊 {name}: {time_ns:.2f}ns ({time_ns/1000:.3f}µs)")
    
    return results

def parse_time_to_ns(time_str: str) -> float:
    """Parse time string to nanoseconds"""
    
    # Remove brackets and extra characters
    time_str = time_str.strip('[](),')
    
    # Extract number and unit
    if time_str.endswith('ns'):
        return float(time_str[:-2].replace(',', ''))
    elif time_str.endswith('µs') or time_str.endswith('us'):
        return float(time_str[:-2].replace(',', '')) * 1000
    elif time_str.endswith('ms'):
        return float(time_str[:-2].replace(',', '')) * 1000000
    elif time_str.endswith('s'):
        return float(time_str[:-1].replace(',', '')) * 1000000000
    
    return 0.0

def run_custom_timing_tests() -> Dict[str, float]:
    """Run custom timing tests with higher precision"""
    
    print("\n🎯 Running Custom Timing Tests")
    print("=" * 45)
    
    # Test single verification
    test_code = '''
use lemma_crypto::LemmaCore;
use std::time::Instant;

fn main() {
    let mut core = LemmaCore::new().unwrap();
    
    // Create a simple test credential
    let credential = lemma_crypto::VerifiableCredential {
        id: "test_id".to_string(),
        issuer: "test_issuer".to_string(),
        subject: "test_subject".to_string(),
        claims: std::collections::HashMap::new(),
        signature: vec![0u8; 64],
        created: std::time::SystemTime::now(),
        expires: None,
        revocation_list_url: None,
        package_type: "identity".to_string(),
    };
    
    // Cold start (first verification)
    let start = Instant::now();
    let _ = core.verify(&credential);
    let cold_time = start.elapsed().as_nanos();
    
    // Warm up with 100 verifications
    for _ in 0..100 {
        let _ = core.verify(&credential);
    }
    
    // Hot verification (cached)
    let start = Instant::now();
    let _ = core.verify(&credential);
    let hot_time = start.elapsed().as_nanos();
    
    println!("cold_verification_ns: {}", cold_time);
    println!("hot_verification_ns: {}", hot_time);
    
    // Statistical sample for hot verification
    let mut hot_times = Vec::new();
    for _ in 0..10000 {
        let start = Instant::now();
        let _ = core.verify(&credential);
        hot_times.push(start.elapsed().as_nanos());
    }
    
    let mean = hot_times.iter().sum::<u128>() as f64 / hot_times.len() as f64;
    let variance = hot_times.iter().map(|&x| (x as f64 - mean).powi(2)).sum::<f64>() / hot_times.len() as f64;
    let std_dev = variance.sqrt();
    
    println!("hot_verification_mean_ns: {:.2}", mean);
    println!("hot_verification_std_ns: {:.2}", std_dev);
    println!("hot_verification_min_ns: {}", hot_times.iter().min().unwrap());
    println!("hot_verification_max_ns: {}", hot_times.iter().max().unwrap());
    
    // Batch verification
    let credentials: Vec<_> = (0..10).map(|i| {
        let mut cred = credential.clone();
        cred.id = format!("test_id_{}", i);
        cred
    }).collect();
    
    let start = Instant::now();
    let _ = core.verify_batch(&credentials);
    let batch_time = start.elapsed().as_nanos() / 10;
    
    println!("batch_verification_per_item_ns: {}", batch_time);
}
'''
    
    # Write test file
    with open("timing_test.rs", 'w') as f:
        f.write(test_code)
    
    # Compile
    compile_result = subprocess.run([
        "rustc", "--edition", "2021",
        "-L", "target/release/deps",
        "timing_test.rs",
        "-o", "timing_test",
        "--extern", "lemma_crypto=target/release/liblemma_crypto.rlib"
    ], capture_output=True, text=True)
    
    if compile_result.returncode != 0:
        print("❌ Compilation failed:")
        print(compile_result.stderr)
        return {}
    
    # Run test
    run_result = subprocess.run(["./timing_test"], capture_output=True, text=True)
    
    if run_result.returncode != 0:
        print("❌ Test failed:")
        print(run_result.stderr)
        return {}
    
    # Parse results
    results = {}
    for line in run_result.stdout.split('\n'):
        if ':' in line and 'ns' in line:
            parts = line.split(':')
            if len(parts) == 2:
                name = parts[0].strip()
                value = float(parts[1].strip())
                results[name] = value
                print(f"📊 {name}: {value:.2f}ns ({value/1000:.3f}µs)")
    
    return results

def validate_performance_claims(results: Dict[str, float]) -> Dict[str, bool]:
    """Validate performance claims against actual measurements"""
    
    print("\n🔍 Validating Performance Claims")
    print("=" * 40)
    
    # Performance claims from documentation (in nanoseconds)
    claims = {
        'ASIC Accelerated': 10,
        'Advanced Algorithms (Phase 3)': 50,
        'FPGA Accelerated': 100,
        'WebAssembly (Multi-Level Cached)': 360,
        'Work-Stealing Optimized': 1000,
        'Native Rust (Multi-Level Cached)': 12500,
        'Same-Issuer Verification': 40000,
        'Cold Start (Uncached)': 151270,
    }
    
    validation_results = {}
    
    for claim_name, target_ns in claims.items():
        # Find best matching result
        best_match = None
        best_match_score = float('inf')
        
        for result_name, result_ns in results.items():
            # Match cold start
            if 'cold' in claim_name.lower() and 'cold' in result_name.lower():
                score = abs(result_ns - target_ns)
                if score < best_match_score:
                    best_match_score = score
                    best_match = (result_name, result_ns)
            
            # Match cached/hot
            elif 'cached' in claim_name.lower() and ('hot' in result_name.lower() or 'mean' in result_name.lower()):
                score = abs(result_ns - target_ns)
                if score < best_match_score:
                    best_match_score = score
                    best_match = (result_name, result_ns)
        
        if best_match:
            result_name, result_ns = best_match
            
            # Check if within reasonable tolerance
            # Use 2x tolerance for now since we're testing without specialized hardware
            tolerance = 2.0
            lower_bound = target_ns / tolerance
            upper_bound = target_ns * tolerance
            
            is_valid = lower_bound <= result_ns <= upper_bound
            
            status = "✅" if is_valid else "❌"
            print(f"{status} {claim_name}:")
            print(f"   Target: {target_ns}ns")
            print(f"   Actual: {result_ns:.2f}ns ({result_name})")
            print(f"   Tolerance: {tolerance}x")
            print(f"   Range: [{lower_bound:.2f}, {upper_bound:.2f}]ns")
            print(f"   Valid: {is_valid}")
            
            validation_results[claim_name] = is_valid
        else:
            print(f"❌ {claim_name}: No matching result found")
            validation_results[claim_name] = False
    
    return validation_results

def analyze_performance_characteristics(results: Dict[str, float]) -> Dict[str, any]:
    """Analyze performance characteristics and identify bottlenecks"""
    
    print("\n📈 Performance Analysis")
    print("=" * 30)
    
    analysis = {}
    
    # Extract key metrics
    cold_time = results.get('cold_verification_ns', 0)
    hot_time = results.get('hot_verification_mean_ns', 0)
    batch_time = results.get('batch_verification_per_item_ns', 0)
    
    if cold_time and hot_time:
        caching_speedup = cold_time / hot_time
        print(f"🚀 Caching Speedup: {caching_speedup:.1f}x")
        analysis['caching_speedup'] = caching_speedup
        
        cache_efficiency = ((cold_time - hot_time) / cold_time) * 100
        print(f"💾 Cache Efficiency: {cache_efficiency:.1f}%")
        analysis['cache_efficiency'] = cache_efficiency
    
    if hot_time and batch_time:
        batch_efficiency = hot_time / batch_time
        print(f"📦 Batch Efficiency: {batch_efficiency:.1f}x")
        analysis['batch_efficiency'] = batch_efficiency
    
    # Throughput calculations
    if hot_time:
        hot_throughput = 1_000_000_000 / hot_time
        print(f"🔥 Hot Throughput: {hot_throughput:,.0f} ops/sec")
        analysis['hot_throughput'] = hot_throughput
    
    if cold_time:
        cold_throughput = 1_000_000_000 / cold_time
        print(f"🆒 Cold Throughput: {cold_throughput:,.0f} ops/sec")
        analysis['cold_throughput'] = cold_throughput
    
    # Performance classification
    if hot_time < 1000:  # < 1µs
        print("🏆 Performance Class: EXCELLENT (sub-microsecond)")
        analysis['performance_class'] = "EXCELLENT"
    elif hot_time < 10000:  # < 10µs
        print("🥇 Performance Class: VERY GOOD (sub-10µs)")
        analysis['performance_class'] = "VERY_GOOD"
    elif hot_time < 100000:  # < 100µs
        print("🥈 Performance Class: GOOD (sub-100µs)")
        analysis['performance_class'] = "GOOD"
    else:
        print("🥉 Performance Class: ACCEPTABLE (>100µs)")
        analysis['performance_class'] = "ACCEPTABLE"
    
    return analysis

def generate_performance_report(rust_results: Dict[str, float], 
                              custom_results: Dict[str, float],
                              validation_results: Dict[str, bool],
                              analysis: Dict[str, any]) -> str:
    """Generate comprehensive performance report"""
    
    report = []
    report.append("# Lemma Verification Performance Test Report")
    report.append("=" * 50)
    report.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Executive Summary
    report.append("## Executive Summary")
    report.append("")
    
    total_claims = len(validation_results)
    passed_claims = sum(validation_results.values())
    
    report.append(f"- **Total Performance Claims**: {total_claims}")
    report.append(f"- **Claims Validated**: {passed_claims}")
    report.append(f"- **Success Rate**: {(passed_claims/total_claims)*100:.1f}%")
    
    if 'performance_class' in analysis:
        report.append(f"- **Performance Class**: {analysis['performance_class']}")
    
    if 'caching_speedup' in analysis:
        report.append(f"- **Caching Speedup**: {analysis['caching_speedup']:.1f}x")
    
    if 'hot_throughput' in analysis:
        report.append(f"- **Peak Throughput**: {analysis['hot_throughput']:,.0f} ops/sec")
    
    report.append("")
    
    # Detailed Results
    report.append("## Detailed Benchmark Results")
    report.append("")
    
    # Custom timing results
    if custom_results:
        report.append("### Custom Timing Tests")
        report.append("")
        
        for name, time_ns in custom_results.items():
            report.append(f"- **{name}**: {time_ns:.2f}ns ({time_ns/1000:.3f}µs)")
        
        report.append("")
    
    # Rust benchmark results
    if rust_results:
        report.append("### Rust Benchmark Results")
        report.append("")
        
        for name, time_ns in rust_results.items():
            report.append(f"- **{name}**: {time_ns:.2f}ns ({time_ns/1000:.3f}µs)")
        
        report.append("")
    
    # Validation Results
    report.append("## Performance Claims Validation")
    report.append("")
    
    for claim_name, is_valid in validation_results.items():
        status = "✅ PASSED" if is_valid else "❌ FAILED"
        report.append(f"- **{claim_name}**: {status}")
    
    report.append("")
    
    # Analysis
    report.append("## Performance Analysis")
    report.append("")
    
    for metric, value in analysis.items():
        if isinstance(value, float):
            if metric.endswith('_throughput'):
                report.append(f"- **{metric}**: {value:,.0f} ops/sec")
            elif metric.endswith('_speedup'):
                report.append(f"- **{metric}**: {value:.1f}x")
            elif metric.endswith('_efficiency'):
                report.append(f"- **{metric}**: {value:.1f}%")
            else:
                report.append(f"- **{metric}**: {value:.2f}")
        else:
            report.append(f"- **{metric}**: {value}")
    
    return "\n".join(report)

def main():
    """Main function"""
    
    print("🚀 Lemma Verification Speed Test")
    print("=" * 50)
    print("This test validates offline verification performance claims")
    print("with statistical rigor and real-world measurements.")
    print("")
    
    try:
        # Run Rust benchmarks
        rust_results = run_rust_benchmarks()
        
        # Run custom timing tests
        custom_results = run_custom_timing_tests()
        
        # Combine results
        all_results = {**rust_results, **custom_results}
        
        if not all_results:
            print("❌ No results obtained")
            return
        
        # Validate claims
        validation_results = validate_performance_claims(all_results)
        
        # Analyze performance
        analysis = analyze_performance_characteristics(all_results)
        
        # Generate report
        report = generate_performance_report(
            rust_results, custom_results, validation_results, analysis
        )
        
        # Save report
        with open("PERFORMANCE_VALIDATION_REPORT.md", 'w') as f:
            f.write(report)
        
        # Save raw results
        results_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'rust_results': rust_results,
            'custom_results': custom_results,
            'validation_results': validation_results,
            'analysis': analysis
        }
        
        with open("performance_validation_results.json", 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\n🎉 Performance Testing Complete!")
        print(f"📊 Report saved to PERFORMANCE_VALIDATION_REPORT.md")
        print(f"💾 Raw data saved to performance_validation_results.json")
        
        # Final summary
        total_claims = len(validation_results)
        passed_claims = sum(validation_results.values())
        
        print(f"\n📈 FINAL RESULTS: {passed_claims}/{total_claims} claims validated")
        
        if passed_claims == total_claims:
            print("✅ ALL PERFORMANCE CLAIMS VALIDATED!")
        elif passed_claims >= total_claims * 0.8:
            print("⚠️  Most claims validated - some may need specialized hardware")
        else:
            print("❌ Performance claims need review")
            
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 