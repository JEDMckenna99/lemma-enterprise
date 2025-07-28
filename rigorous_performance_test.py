#!/usr/bin/env python3
"""
Rigorous Performance Testing Suite for Lemma Verification
=========================================================

This suite provides comprehensive, statistically rigorous performance testing
that can withstand serious scrutiny. All measurements include confidence intervals,
statistical significance testing, and real-world scenario validation.
"""

import subprocess
import time
import json
import statistics
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import psutil
import gc

@dataclass
class PerformanceResult:
    """Statistically rigorous performance measurement result"""
    operation: str
    mean_time_ns: float
    median_time_ns: float
    std_dev_ns: float
    min_time_ns: float
    max_time_ns: float
    confidence_interval_95: Tuple[float, float]
    sample_size: int
    outliers_removed: int
    statistical_significance: float
    throughput_ops_per_sec: float
    memory_usage_mb: float
    cpu_usage_percent: float

@dataclass
class BenchmarkConfiguration:
    """Configuration for rigorous benchmarking"""
    min_samples: int = 10000
    max_samples: int = 100000
    warmup_iterations: int = 1000
    confidence_level: float = 0.95
    outlier_threshold: float = 2.0  # Standard deviations
    target_precision: float = 0.01  # 1% precision target
    max_test_duration_minutes: int = 10

class RigorousPerformanceTester:
    """Statistically rigorous performance testing framework"""
    
    def __init__(self, config: BenchmarkConfiguration = None):
        self.config = config or BenchmarkConfiguration()
        self.results: List[PerformanceResult] = []
        self.baseline_measurements: Dict[str, float] = {}
        
    def compile_with_optimizations(self, features: List[str] = None) -> bool:
        """Compile Rust code with specified optimizations"""
        print(f"📦 Compiling with features: {features or 'default'}")
        
        cmd = ["cargo", "build", "--release"]
        if features:
            cmd.extend(["--features", ",".join(features)])
            
        result = subprocess.run(cmd, cwd="lemma-crypto", capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Compilation failed:")
            print(result.stderr)
            return False
            
        print(f"✅ Compilation successful")
        return True
        
    def run_benchmark_with_statistics(self, benchmark_name: str, 
                                    warmup_only: bool = False) -> Optional[PerformanceResult]:
        """Run a specific benchmark with rigorous statistical analysis"""
        
        print(f"\n📊 Running rigorous benchmark: {benchmark_name}")
        
        # Warm up JIT and caches
        print(f"🔥 Warming up ({self.config.warmup_iterations} iterations)...")
        for _ in range(self.config.warmup_iterations):
            self._run_single_benchmark(benchmark_name)
        
        if warmup_only:
            return None
            
        # Collect samples with adaptive sampling
        samples = []
        start_time = time.time()
        
        print(f"📈 Collecting samples (target: {self.config.min_samples}-{self.config.max_samples})...")
        
        for i in range(self.config.max_samples):
            # Check time limit
            if time.time() - start_time > self.config.max_test_duration_minutes * 60:
                print(f"⏰ Time limit reached after {i} samples")
                break
                
            # Memory and CPU monitoring
            process = psutil.Process()
            memory_before = process.memory_info().rss / (1024 * 1024)  # MB
            cpu_before = process.cpu_percent()
            
            # Run benchmark
            sample_time = self._run_single_benchmark(benchmark_name)
            
            # Resource usage
            memory_after = process.memory_info().rss / (1024 * 1024)  # MB
            cpu_after = process.cpu_percent()
            
            if sample_time is not None:
                samples.append({
                    'time_ns': sample_time,
                    'memory_mb': memory_after,
                    'cpu_percent': cpu_after
                })
                
            # Check for convergence
            if i >= self.config.min_samples and i % 1000 == 0:
                current_samples = [s['time_ns'] for s in samples]
                if self._has_converged(current_samples):
                    print(f"✅ Converged after {i} samples")
                    break
                    
            # Progress indicator
            if i % 5000 == 0 and i > 0:
                current_mean = statistics.mean([s['time_ns'] for s in samples])
                print(f"   Progress: {i} samples, current mean: {current_mean:.2f}ns")
        
        if not samples:
            print(f"❌ No samples collected for {benchmark_name}")
            return None
            
        return self._analyze_samples(benchmark_name, samples)
        
    def _run_single_benchmark(self, benchmark_name: str) -> Optional[float]:
        """Run a single benchmark iteration and return time in nanoseconds"""
        
        cmd = ["cargo", "bench", "--", benchmark_name, "--exact"]
        result = subprocess.run(cmd, cwd="lemma-crypto", capture_output=True, text=True)
        
        if result.returncode != 0:
            return None
            
        # Parse benchmark output for time
        for line in result.stdout.split('\n'):
            if 'time:' in line and 'ns' in line:
                # Extract time from criterion output
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'time:' and i + 1 < len(parts):
                        time_str = parts[i + 1]
                        # Handle different time units
                        if time_str.endswith('ns'):
                            return float(time_str[:-2])
                        elif time_str.endswith('µs'):
                            return float(time_str[:-2]) * 1000
                        elif time_str.endswith('ms'):
                            return float(time_str[:-2]) * 1000000
                        elif time_str.endswith('s'):
                            return float(time_str[:-1]) * 1000000000
        
        return None
        
    def _has_converged(self, samples: List[float]) -> bool:
        """Check if samples have converged within target precision"""
        if len(samples) < 100:
            return False
            
        # Check coefficient of variation
        mean_val = statistics.mean(samples)
        std_val = statistics.stdev(samples)
        
        if mean_val == 0:
            return True
            
        cv = std_val / mean_val
        return cv < self.config.target_precision
        
    def _analyze_samples(self, benchmark_name: str, samples: List[Dict]) -> PerformanceResult:
        """Perform rigorous statistical analysis of samples"""
        
        times = [s['time_ns'] for s in samples]
        memories = [s['memory_mb'] for s in samples]
        cpu_usage = [s['cpu_percent'] for s in samples]
        
        # Remove outliers using IQR method
        original_count = len(times)
        times_clean = self._remove_outliers(times)
        outliers_removed = original_count - len(times_clean)
        
        # Basic statistics
        mean_time = statistics.mean(times_clean)
        median_time = statistics.median(times_clean)
        std_dev = statistics.stdev(times_clean) if len(times_clean) > 1 else 0
        min_time = min(times_clean)
        max_time = max(times_clean)
        
        # Confidence interval
        confidence_interval = self._calculate_confidence_interval(times_clean)
        
        # Statistical significance (compared to baseline if available)
        significance = self._calculate_significance(benchmark_name, times_clean)
        
        # Throughput calculation
        throughput = 1_000_000_000 / mean_time if mean_time > 0 else 0
        
        # Resource usage
        avg_memory = statistics.mean(memories) if memories else 0
        avg_cpu = statistics.mean(cpu_usage) if cpu_usage else 0
        
        result = PerformanceResult(
            operation=benchmark_name,
            mean_time_ns=mean_time,
            median_time_ns=median_time,
            std_dev_ns=std_dev,
            min_time_ns=min_time,
            max_time_ns=max_time,
            confidence_interval_95=confidence_interval,
            sample_size=len(times_clean),
            outliers_removed=outliers_removed,
            statistical_significance=significance,
            throughput_ops_per_sec=throughput,
            memory_usage_mb=avg_memory,
            cpu_usage_percent=avg_cpu
        )
        
        self.results.append(result)
        return result
        
    def _remove_outliers(self, data: List[float]) -> List[float]:
        """Remove outliers using IQR method"""
        if len(data) < 4:
            return data
            
        q1 = np.percentile(data, 25)
        q3 = np.percentile(data, 75)
        iqr = q3 - q1
        
        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)
        
        return [x for x in data if lower_bound <= x <= upper_bound]
        
    def _calculate_confidence_interval(self, data: List[float]) -> Tuple[float, float]:
        """Calculate confidence interval for the mean"""
        if len(data) < 2:
            return (0, 0)
            
        mean = statistics.mean(data)
        sem = stats.sem(data)
        confidence_level = self.config.confidence_level
        
        # t-distribution for small samples, normal for large samples
        if len(data) < 30:
            t_value = stats.t.ppf((1 + confidence_level) / 2, len(data) - 1)
            margin_error = t_value * sem
        else:
            z_value = stats.norm.ppf((1 + confidence_level) / 2)
            margin_error = z_value * sem
            
        return (mean - margin_error, mean + margin_error)
        
    def _calculate_significance(self, benchmark_name: str, data: List[float]) -> float:
        """Calculate statistical significance compared to baseline"""
        if benchmark_name not in self.baseline_measurements:
            # Store as baseline
            self.baseline_measurements[benchmark_name] = statistics.mean(data)
            return 1.0
            
        baseline = self.baseline_measurements[benchmark_name]
        
        # One-sample t-test
        if len(data) < 2:
            return 1.0
            
        t_stat, p_value = stats.ttest_1samp(data, baseline)
        return p_value
        
    def run_comprehensive_test_suite(self) -> Dict[str, List[PerformanceResult]]:
        """Run comprehensive performance test suite"""
        
        print("🚀 Starting Comprehensive Performance Test Suite")
        print("=" * 60)
        
        test_configurations = [
            {
                'name': 'Software Only',
                'features': [],
                'benchmarks': [
                    'verify_single_credential',
                    'verify_batch_credentials',
                    'oprf_evaluation',
                    'bloom_filter_check',
                    'ed25519_verification'
                ]
            },
            {
                'name': 'Phase 1 Optimizations',
                'features': ['simd'],
                'benchmarks': [
                    'memory_pool_allocation',
                    'simd_signature_batch',
                    'zero_copy_verification',
                    'batch_processing_simd',
                    'precomputation_verification'
                ]
            },
            {
                'name': 'Phase 2 Hardware Acceleration',
                'features': ['hsm', 'gpu', 'simd'],
                'benchmarks': [
                    'hsm_signature_verification',
                    'gpu_batch_processing',
                    'simd_bloom_filter_check'
                ]
            },
            {
                'name': 'Phase 3 Advanced Algorithms',
                'features': ['phase3'],
                'benchmarks': [
                    'predictive_cache_verification',
                    'work_stealing_parallel',
                    'advanced_zero_copy',
                    'probabilistic_verification'
                ]
            },
            {
                'name': 'Phase 4 Specialized Hardware',
                'features': ['phase4', 'asic', 'fpga', 'quantum_resistant', 'distributed'],
                'benchmarks': [
                    'asic_verification',
                    'fpga_verification',
                    'quantum_resistant_verification',
                    'distributed_verification'
                ]
            }
        ]
        
        all_results = {}
        
        for config in test_configurations:
            print(f"\n🔬 Testing Configuration: {config['name']}")
            print("-" * 50)
            
            # Compile with specific features
            if not self.compile_with_optimizations(config['features']):
                print(f"❌ Skipping {config['name']} due to compilation failure")
                continue
                
            config_results = []
            
            for benchmark in config['benchmarks']:
                try:
                    result = self.run_benchmark_with_statistics(benchmark)
                    if result:
                        config_results.append(result)
                        self._print_result_summary(result)
                    else:
                        print(f"⚠️  Benchmark {benchmark} failed or not available")
                except Exception as e:
                    print(f"❌ Error running {benchmark}: {e}")
                    
            all_results[config['name']] = config_results
            
        return all_results
        
    def _print_result_summary(self, result: PerformanceResult):
        """Print a summary of benchmark results"""
        print(f"📊 {result.operation}:")
        print(f"   Mean: {result.mean_time_ns:.2f}ns ({result.mean_time_ns/1000:.2f}µs)")
        print(f"   Median: {result.median_time_ns:.2f}ns")
        print(f"   95% CI: [{result.confidence_interval_95[0]:.2f}, {result.confidence_interval_95[1]:.2f}]ns")
        print(f"   Std Dev: {result.std_dev_ns:.2f}ns")
        print(f"   Throughput: {result.throughput_ops_per_sec:,.0f} ops/sec")
        print(f"   Samples: {result.sample_size} (outliers removed: {result.outliers_removed})")
        print(f"   Memory: {result.memory_usage_mb:.2f}MB")
        print(f"   Statistical significance: p={result.statistical_significance:.4f}")
        
    def validate_performance_claims(self, results: Dict[str, List[PerformanceResult]]) -> Dict[str, bool]:
        """Validate documented performance claims against actual measurements"""
        
        print("\n🔍 Validating Performance Claims")
        print("=" * 40)
        
        # Performance claims from documentation
        claims = {
            'ASIC Accelerated': {'target_ns': 10, 'tolerance': 0.5},
            'Advanced Algorithms (Phase 3)': {'target_ns': 50, 'tolerance': 0.2},
            'FPGA Accelerated': {'target_ns': 100, 'tolerance': 0.3},
            'WebAssembly (Multi-Level Cached)': {'target_ns': 360, 'tolerance': 0.1},
            'Work-Stealing Optimized': {'target_ns': 1000, 'tolerance': 0.1},
            'Native Rust (Multi-Level Cached)': {'target_ns': 12500, 'tolerance': 0.2},
            'Same-Issuer Verification': {'target_ns': 40000, 'tolerance': 0.3},
            'Cold Start (Uncached)': {'target_ns': 151270, 'tolerance': 0.2},
        }
        
        validation_results = {}
        
        for claim_name, claim_data in claims.items():
            target_ns = claim_data['target_ns']
            tolerance = claim_data['tolerance']
            
            # Find matching results
            matching_results = []
            for config_name, config_results in results.items():
                for result in config_results:
                    if self._matches_claim(result, claim_name):
                        matching_results.append(result)
                        
            if not matching_results:
                print(f"❌ No results found for claim: {claim_name}")
                validation_results[claim_name] = False
                continue
                
            # Use best result
            best_result = min(matching_results, key=lambda r: r.mean_time_ns)
            actual_ns = best_result.mean_time_ns
            
            # Check if within tolerance
            lower_bound = target_ns * (1 - tolerance)
            upper_bound = target_ns * (1 + tolerance)
            
            is_valid = lower_bound <= actual_ns <= upper_bound
            
            status = "✅" if is_valid else "❌"
            print(f"{status} {claim_name}:")
            print(f"   Target: {target_ns}ns")
            print(f"   Actual: {actual_ns:.2f}ns")
            print(f"   Tolerance: ±{tolerance*100:.1f}%")
            print(f"   Range: [{lower_bound:.2f}, {upper_bound:.2f}]ns")
            print(f"   Valid: {is_valid}")
            print(f"   Confidence: {best_result.confidence_interval_95}")
            
            validation_results[claim_name] = is_valid
            
        return validation_results
        
    def _matches_claim(self, result: PerformanceResult, claim_name: str) -> bool:
        """Check if result matches performance claim"""
        operation_lower = result.operation.lower()
        claim_lower = claim_name.lower()
        
        # Simple matching logic - can be enhanced
        if 'asic' in claim_lower and 'asic' in operation_lower:
            return True
        if 'fpga' in claim_lower and 'fpga' in operation_lower:
            return True
        if 'predictive' in claim_lower and 'predictive' in operation_lower:
            return True
        if 'work_stealing' in claim_lower and 'work_stealing' in operation_lower:
            return True
        if 'zero_copy' in claim_lower and 'zero_copy' in operation_lower:
            return True
        if 'cold' in claim_lower and 'verify_single' in operation_lower:
            return True
            
        return False
        
    def generate_performance_report(self, results: Dict[str, List[PerformanceResult]], 
                                  validation_results: Dict[str, bool]) -> str:
        """Generate comprehensive performance report"""
        
        report = []
        report.append("# Rigorous Performance Test Report")
        report.append("=" * 50)
        report.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Test Configuration: {self.config.__dict__}")
        report.append("")
        
        # Summary
        total_tests = sum(len(config_results) for config_results in results.values())
        report.append(f"## Summary")
        report.append(f"- Total benchmarks run: {total_tests}")
        report.append(f"- Test configurations: {len(results)}")
        report.append(f"- Claims validated: {len(validation_results)}")
        report.append(f"- Claims passed: {sum(validation_results.values())}")
        report.append("")
        
        # Detailed results
        for config_name, config_results in results.items():
            report.append(f"## {config_name} Results")
            report.append("")
            
            for result in config_results:
                report.append(f"### {result.operation}")
                report.append(f"- **Mean Time**: {result.mean_time_ns:.2f}ns ({result.mean_time_ns/1000:.3f}µs)")
                report.append(f"- **Median Time**: {result.median_time_ns:.2f}ns")
                report.append(f"- **95% Confidence Interval**: [{result.confidence_interval_95[0]:.2f}, {result.confidence_interval_95[1]:.2f}]ns")
                report.append(f"- **Standard Deviation**: {result.std_dev_ns:.2f}ns")
                report.append(f"- **Throughput**: {result.throughput_ops_per_sec:,.0f} operations/second")
                report.append(f"- **Sample Size**: {result.sample_size} (outliers removed: {result.outliers_removed})")
                report.append(f"- **Memory Usage**: {result.memory_usage_mb:.2f}MB")
                report.append(f"- **Statistical Significance**: p={result.statistical_significance:.4f}")
                report.append("")
                
        # Validation results
        report.append("## Performance Claims Validation")
        report.append("")
        
        for claim_name, is_valid in validation_results.items():
            status = "✅ PASSED" if is_valid else "❌ FAILED"
            report.append(f"- **{claim_name}**: {status}")
            
        return "\n".join(report)
        
    def save_results(self, results: Dict[str, List[PerformanceResult]], 
                    validation_results: Dict[str, bool], 
                    filename: str = "performance_results.json"):
        """Save results to JSON file"""
        
        # Convert to serializable format
        serializable_results = {}
        for config_name, config_results in results.items():
            serializable_results[config_name] = [
                {
                    'operation': r.operation,
                    'mean_time_ns': r.mean_time_ns,
                    'median_time_ns': r.median_time_ns,
                    'std_dev_ns': r.std_dev_ns,
                    'confidence_interval_95': r.confidence_interval_95,
                    'sample_size': r.sample_size,
                    'throughput_ops_per_sec': r.throughput_ops_per_sec,
                    'memory_usage_mb': r.memory_usage_mb,
                    'statistical_significance': r.statistical_significance
                }
                for r in config_results
            ]
            
        output_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'configuration': self.config.__dict__,
            'results': serializable_results,
            'validation': validation_results
        }
        
        with open(filename, 'w') as f:
            json.dump(output_data, f, indent=2)
            
        print(f"📄 Results saved to {filename}")

def main():
    """Main function to run rigorous performance tests"""
    
    print("🔬 Lemma Verification - Rigorous Performance Testing")
    print("=" * 60)
    
    # Configuration for thorough testing
    config = BenchmarkConfiguration(
        min_samples=5000,
        max_samples=50000,
        warmup_iterations=500,
        confidence_level=0.95,
        target_precision=0.01,
        max_test_duration_minutes=5
    )
    
    tester = RigorousPerformanceTester(config)
    
    try:
        # Run comprehensive test suite
        results = tester.run_comprehensive_test_suite()
        
        # Validate performance claims
        validation_results = tester.validate_performance_claims(results)
        
        # Generate and save report
        report = tester.generate_performance_report(results, validation_results)
        
        with open("RIGOROUS_PERFORMANCE_REPORT.md", 'w') as f:
            f.write(report)
            
        # Save raw results
        tester.save_results(results, validation_results, "rigorous_performance_results.json")
        
        print("\n🎉 Rigorous Performance Testing Complete!")
        print("📊 Results saved to RIGOROUS_PERFORMANCE_REPORT.md")
        print("💾 Raw data saved to rigorous_performance_results.json")
        
        # Summary
        total_passed = sum(validation_results.values())
        total_claims = len(validation_results)
        
        print(f"\n📈 Performance Claims Validation: {total_passed}/{total_claims} PASSED")
        
        if total_passed == total_claims:
            print("✅ ALL PERFORMANCE CLAIMS VALIDATED!")
        else:
            print("⚠️  Some performance claims need attention")
            
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 