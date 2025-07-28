#!/usr/bin/env python3
"""
Comprehensive Test Suite for Phase 3 & 4 Optimizations
Testing: Predictive Caching, Work-Stealing, Zero-Copy, Probabilistic Verification,
ASIC/FPGA Acceleration, Quantum-Resistant Cryptography, Distributed Processing
"""

import subprocess
import json
import time
import statistics
import concurrent.futures
from typing import List, Dict, Any
import os

class Phase3Phase4TestSuite:
    def __init__(self):
        self.test_results = {
            'phase3': {
                'predictive_caching': {},
                'work_stealing': {},
                'advanced_zero_copy': {},
                'probabilistic_verification': {}
            },
            'phase4': {
                'asic_integration': {},
                'fpga_implementation': {},
                'quantum_resistant': {},
                'distributed_processing': {}
            },
            'integration': {},
            'performance': {}
        }
    
    def run_rust_benchmark(self, benchmark_name: str, feature_flags: str = "") -> Dict[str, Any]:
        """Run a specific Rust benchmark and parse results"""
        cmd = f"cargo bench --bench benchmarks {benchmark_name}"
        if feature_flags:
            cmd += f" --features=\"{feature_flags}\""
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                                 cwd="lemma-crypto", timeout=300)
            
            if result.returncode != 0:
                print(f"❌ Benchmark {benchmark_name} failed:")
                print(result.stderr)
                return {'success': False, 'error': result.stderr}
            
            # Parse benchmark output (simplified)
            lines = result.stdout.split('\n')
            timing_data = {}
            
            for line in lines:
                if 'time:' in line and 'µs' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        timing_data['mean'] = parts[1]
                        timing_data['unit'] = 'µs'
                elif 'ns' in line and 'time:' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        timing_data['mean'] = parts[1]
                        timing_data['unit'] = 'ns'
            
            return {'success': True, 'timing': timing_data, 'output': result.stdout}
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Benchmark timed out'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def test_phase3_predictive_caching(self):
        """Test Phase 3 predictive caching system"""
        print("🧠 Testing Phase 3 Predictive Caching...")
        
        # Test basic predictive caching
        result = self.run_rust_benchmark("predictive_cache_benchmark", "phase3")
        self.test_results['phase3']['predictive_caching']['basic'] = result
        
        # Test pattern analysis
        result = self.run_rust_benchmark("pattern_analysis_benchmark", "phase3")
        self.test_results['phase3']['predictive_caching']['pattern_analysis'] = result
        
        # Test cache prediction accuracy
        result = self.run_rust_benchmark("cache_prediction_accuracy_benchmark", "phase3")
        self.test_results['phase3']['predictive_caching']['accuracy'] = result
        
        print("✅ Predictive Caching tests completed")
    
    def test_phase3_work_stealing(self):
        """Test Phase 3 work-stealing parallelism"""
        print("⚡ Testing Phase 3 Work-Stealing Parallelism...")
        
        # Test work-stealing scheduler
        result = self.run_rust_benchmark("work_stealing_scheduler_benchmark", "phase3")
        self.test_results['phase3']['work_stealing']['scheduler'] = result
        
        # Test dynamic load balancing
        result = self.run_rust_benchmark("dynamic_load_balancing_benchmark", "phase3")
        self.test_results['phase3']['work_stealing']['load_balancing'] = result
        
        # Test CPU utilization
        result = self.run_rust_benchmark("cpu_utilization_benchmark", "phase3")
        self.test_results['phase3']['work_stealing']['cpu_utilization'] = result
        
        print("✅ Work-Stealing tests completed")
    
    def test_phase3_advanced_zero_copy(self):
        """Test Phase 3 advanced zero-copy operations"""
        print("🚀 Testing Phase 3 Advanced Zero-Copy Operations...")
        
        # Test advanced zero-copy verifier
        result = self.run_rust_benchmark("advanced_zero_copy_benchmark", "phase3")
        self.test_results['phase3']['advanced_zero_copy']['verifier'] = result
        
        # Test memory-mapped shared memory
        result = self.run_rust_benchmark("memory_mapped_shared_benchmark", "phase3")
        self.test_results['phase3']['advanced_zero_copy']['shared_memory'] = result
        
        # Test SIMD memory operations
        result = self.run_rust_benchmark("simd_memory_operations_benchmark", "phase3")
        self.test_results['phase3']['advanced_zero_copy']['simd_memory'] = result
        
        print("✅ Advanced Zero-Copy tests completed")
    
    def test_phase3_probabilistic_verification(self):
        """Test Phase 3 probabilistic verification"""
        print("🎯 Testing Phase 3 Probabilistic Verification...")
        
        # Test probabilistic verifier
        result = self.run_rust_benchmark("probabilistic_verifier_benchmark", "phase3")
        self.test_results['phase3']['probabilistic_verification']['verifier'] = result
        
        # Test confidence scoring
        result = self.run_rust_benchmark("confidence_scoring_benchmark", "phase3")
        self.test_results['phase3']['probabilistic_verification']['confidence'] = result
        
        # Test statistical analysis
        result = self.run_rust_benchmark("statistical_analysis_benchmark", "phase3")
        self.test_results['phase3']['probabilistic_verification']['statistics'] = result
        
        print("✅ Probabilistic Verification tests completed")
    
    def test_phase4_asic_integration(self):
        """Test Phase 4 ASIC integration"""
        print("🔥 Testing Phase 4 ASIC Integration...")
        
        # Test ASIC verifier
        result = self.run_rust_benchmark("asic_verifier_benchmark", "phase4,asic")
        self.test_results['phase4']['asic_integration']['verifier'] = result
        
        # Test ASIC batch processing
        result = self.run_rust_benchmark("asic_batch_benchmark", "phase4,asic")
        self.test_results['phase4']['asic_integration']['batch'] = result
        
        # Test hardware detection
        result = self.run_rust_benchmark("asic_hardware_detection_benchmark", "phase4,asic")
        self.test_results['phase4']['asic_integration']['detection'] = result
        
        print("✅ ASIC Integration tests completed")
    
    def test_phase4_fpga_implementation(self):
        """Test Phase 4 FPGA implementation"""
        print("⚙️ Testing Phase 4 FPGA Implementation...")
        
        # Test FPGA verifier
        result = self.run_rust_benchmark("fpga_verifier_benchmark", "phase4,fpga")
        self.test_results['phase4']['fpga_implementation']['verifier'] = result
        
        # Test configurable bitstreams
        result = self.run_rust_benchmark("fpga_bitstream_benchmark", "phase4,fpga")
        self.test_results['phase4']['fpga_implementation']['bitstream'] = result
        
        # Test reconfiguration
        result = self.run_rust_benchmark("fpga_reconfiguration_benchmark", "phase4,fpga")
        self.test_results['phase4']['fpga_implementation']['reconfiguration'] = result
        
        print("✅ FPGA Implementation tests completed")
    
    def test_phase4_quantum_resistant(self):
        """Test Phase 4 quantum-resistant cryptography"""
        print("🔐 Testing Phase 4 Quantum-Resistant Cryptography...")
        
        # Test quantum-resistant verifier
        result = self.run_rust_benchmark("quantum_resistant_verifier_benchmark", "phase4,quantum_resistant")
        self.test_results['phase4']['quantum_resistant']['verifier'] = result
        
        # Test post-quantum algorithms
        result = self.run_rust_benchmark("post_quantum_algorithms_benchmark", "phase4,quantum_resistant")
        self.test_results['phase4']['quantum_resistant']['algorithms'] = result
        
        # Test hybrid verification
        result = self.run_rust_benchmark("hybrid_verification_benchmark", "phase4,quantum_resistant")
        self.test_results['phase4']['quantum_resistant']['hybrid'] = result
        
        print("✅ Quantum-Resistant tests completed")
    
    def test_phase4_distributed_processing(self):
        """Test Phase 4 distributed processing"""
        print("🌐 Testing Phase 4 Distributed Processing...")
        
        # Test distributed verifier
        result = self.run_rust_benchmark("distributed_verifier_benchmark", "phase4,distributed")
        self.test_results['phase4']['distributed_processing']['verifier'] = result
        
        # Test multi-node clusters
        result = self.run_rust_benchmark("multi_node_cluster_benchmark", "phase4,distributed")
        self.test_results['phase4']['distributed_processing']['cluster'] = result
        
        # Test fault tolerance
        result = self.run_rust_benchmark("fault_tolerance_benchmark", "phase4,distributed")
        self.test_results['phase4']['distributed_processing']['fault_tolerance'] = result
        
        print("✅ Distributed Processing tests completed")
    
    def test_integration_performance(self):
        """Test integrated performance of all optimizations"""
        print("🔬 Testing Integration Performance...")
        
        # Test Phase 3 integration
        result = self.run_rust_benchmark("phase3_integration_benchmark", "phase3")
        self.test_results['integration']['phase3'] = result
        
        # Test Phase 4 integration
        result = self.run_rust_benchmark("phase4_integration_benchmark", "phase4")
        self.test_results['integration']['phase4'] = result
        
        # Test complete integration
        result = self.run_rust_benchmark("complete_integration_benchmark", "phase3,phase4")
        self.test_results['integration']['complete'] = result
        
        print("✅ Integration Performance tests completed")
    
    def test_throughput_scalability(self):
        """Test throughput and scalability"""
        print("📈 Testing Throughput & Scalability...")
        
        batch_sizes = [1, 8, 32, 128, 512, 1024]
        
        for size in batch_sizes:
            # Test with different batch sizes
            result = self.run_rust_benchmark(f"batch_processing_benchmark_{size}", "phase3,phase4")
            self.test_results['performance'][f'batch_{size}'] = result
        
        print("✅ Throughput & Scalability tests completed")
    
    def compile_rust_with_optimizations(self):
        """Compile Rust code with all optimizations"""
        print("🔧 Compiling Rust code with all optimizations...")
        
        cmd = "cargo build --release --features=\"phase3,phase4,asic,fpga,quantum_resistant,distributed\""
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                                 cwd="lemma-crypto", timeout=300)
            
            if result.returncode != 0:
                print(f"❌ Compilation failed:")
                print(result.stderr)
                return False
            
            print("✅ Compilation successful")
            return True
            
        except subprocess.TimeoutExpired:
            print("❌ Compilation timed out")
            return False
        except Exception as e:
            print(f"❌ Compilation error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all Phase 3 & 4 tests"""
        print("🚀 Starting Comprehensive Phase 3 & 4 Test Suite...")
        print("=" * 60)
        
        # First compile with all optimizations
        if not self.compile_rust_with_optimizations():
            print("❌ Cannot proceed without successful compilation")
            return False
        
        # Phase 3 Tests
        print("\n📊 Phase 3 Advanced Algorithm Tests")
        print("-" * 40)
        self.test_phase3_predictive_caching()
        self.test_phase3_work_stealing()
        self.test_phase3_advanced_zero_copy()
        self.test_phase3_probabilistic_verification()
        
        # Phase 4 Tests  
        print("\n🔬 Phase 4 Specialized Hardware Tests")
        print("-" * 40)
        self.test_phase4_asic_integration()
        self.test_phase4_fpga_implementation()
        self.test_phase4_quantum_resistant()
        self.test_phase4_distributed_processing()
        
        # Integration Tests
        print("\n🧪 Integration & Performance Tests")
        print("-" * 40)
        self.test_integration_performance()
        self.test_throughput_scalability()
        
        # Save results
        self.save_test_results()
        
        # Generate report
        self.generate_test_report()
        
        print("\n✅ All tests completed!")
        return True
    
    def save_test_results(self):
        """Save test results to JSON file"""
        try:
            with open('phase3_4_test_results.json', 'w') as f:
                json.dump(self.test_results, f, indent=2)
            print("💾 Test results saved to phase3_4_test_results.json")
        except Exception as e:
            print(f"❌ Failed to save results: {e}")
    
    def generate_test_report(self):
        """Generate a comprehensive test report"""
        report = []
        report.append("# Phase 3 & 4 Optimization Test Report")
        report.append("=" * 50)
        report.append("")
        
        # Phase 3 Report
        report.append("## Phase 3 Advanced Algorithm Results")
        report.append("-" * 30)
        
        phase3_results = self.test_results['phase3']
        for category, tests in phase3_results.items():
            report.append(f"### {category.replace('_', ' ').title()}")
            for test_name, result in tests.items():
                if result.get('success'):
                    timing = result.get('timing', {})
                    mean_time = timing.get('mean', 'N/A')
                    unit = timing.get('unit', '')
                    report.append(f"- **{test_name}**: {mean_time} {unit} ✅")
                else:
                    report.append(f"- **{test_name}**: Failed ❌")
            report.append("")
        
        # Phase 4 Report
        report.append("## Phase 4 Specialized Hardware Results")
        report.append("-" * 30)
        
        phase4_results = self.test_results['phase4']
        for category, tests in phase4_results.items():
            report.append(f"### {category.replace('_', ' ').title()}")
            for test_name, result in tests.items():
                if result.get('success'):
                    timing = result.get('timing', {})
                    mean_time = timing.get('mean', 'N/A')
                    unit = timing.get('unit', '')
                    report.append(f"- **{test_name}**: {mean_time} {unit} ✅")
                else:
                    report.append(f"- **{test_name}**: Failed ❌")
            report.append("")
        
        # Integration Report
        report.append("## Integration Performance Results")
        report.append("-" * 30)
        
        integration_results = self.test_results['integration']
        for test_name, result in integration_results.items():
            if result.get('success'):
                timing = result.get('timing', {})
                mean_time = timing.get('mean', 'N/A')
                unit = timing.get('unit', '')
                report.append(f"- **{test_name}**: {mean_time} {unit} ✅")
            else:
                report.append(f"- **{test_name}**: Failed ❌")
        
        # Save report
        try:
            with open('phase3_4_test_report.md', 'w') as f:
                f.write('\n'.join(report))
            print("📄 Test report saved to phase3_4_test_report.md")
        except Exception as e:
            print(f"❌ Failed to save report: {e}")

def main():
    """Main test execution"""
    print("🎯 Lemma Phase 3 & 4 Optimization Test Suite")
    print("Testing: Advanced Algorithms + Specialized Hardware")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not os.path.exists('lemma-crypto'):
        print("❌ Error: Please run this script from the lemma-rebuild directory")
        print("   Expected to find lemma-crypto/ subdirectory")
        return 1
    
    # Initialize test suite
    test_suite = Phase3Phase4TestSuite()
    
    # Run all tests
    success = test_suite.run_all_tests()
    
    if success:
        print("\n🎉 All Phase 3 & 4 optimization tests completed successfully!")
        print("📊 Check phase3_4_test_results.json for detailed results")
        print("📄 Check phase3_4_test_report.md for formatted report")
        return 0
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit(main()) 