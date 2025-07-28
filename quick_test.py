#!/usr/bin/env python3
"""
Quick Test Script for Phase 3 & 4 Optimizations
Basic validation of all optimization features
"""

import subprocess
import os
import sys

def run_command(cmd, cwd=".", timeout=60):
    """Run a command and return success/failure"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                              cwd=cwd, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def main():
    print("🚀 Quick Test: Phase 3 & 4 Optimizations")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists('lemma-crypto'):
        print("❌ Error: Please run this script from the lemma-rebuild directory")
        print("   Expected to find lemma-crypto/ subdirectory")
        return 1
    
    # Test 1: Basic compilation
    print("🔧 Test 1: Basic Compilation")
    success, stdout, stderr = run_command("cargo build", cwd="lemma-crypto")
    if success:
        print("✅ Basic compilation successful")
    else:
        print("❌ Basic compilation failed:")
        print(stderr)
        return 1
    
    # Test 2: Phase 3 features compilation
    print("\n📊 Test 2: Phase 3 Features Compilation")
    success, stdout, stderr = run_command("cargo build --features=\"phase3\"", cwd="lemma-crypto")
    if success:
        print("✅ Phase 3 features compilation successful")
    else:
        print("❌ Phase 3 features compilation failed:")
        print(stderr)
        return 1
    
    # Test 3: Phase 4 features compilation
    print("\n🔬 Test 3: Phase 4 Features Compilation")
    success, stdout, stderr = run_command("cargo build --features=\"phase4\"", cwd="lemma-crypto")
    if success:
        print("✅ Phase 4 features compilation successful")
    else:
        print("❌ Phase 4 features compilation failed:")
        print(stderr)
        return 1
    
    # Test 4: All features compilation
    print("\n🎯 Test 4: All Features Compilation")
    success, stdout, stderr = run_command("cargo build --features=\"phase3,phase4,asic,fpga,quantum_resistant,distributed\"", cwd="lemma-crypto")
    if success:
        print("✅ All features compilation successful")
    else:
        print("❌ All features compilation failed:")
        print(stderr)
        return 1
    
    # Test 5: Basic tests
    print("\n🧪 Test 5: Basic Tests")
    success, stdout, stderr = run_command("cargo test", cwd="lemma-crypto")
    if success:
        print("✅ Basic tests passed")
    else:
        print("❌ Basic tests failed:")
        print(stderr)
        return 1
    
    # Test 6: Phase 3 tests
    print("\n📈 Test 6: Phase 3 Tests")
    success, stdout, stderr = run_command("cargo test --features=\"phase3\"", cwd="lemma-crypto")
    if success:
        print("✅ Phase 3 tests passed")
    else:
        print("❌ Phase 3 tests failed:")
        print(stderr)
        return 1
    
    # Test 7: Phase 4 tests
    print("\n🔥 Test 7: Phase 4 Tests")
    success, stdout, stderr = run_command("cargo test --features=\"phase4\"", cwd="lemma-crypto")
    if success:
        print("✅ Phase 4 tests passed")
    else:
        print("❌ Phase 4 tests failed:")
        print(stderr)
        return 1
    
    # Test 8: Quick benchmark (if available)
    print("\n⚡ Test 8: Quick Benchmark")
    success, stdout, stderr = run_command("cargo bench --bench benchmarks -- --sample-size 10", cwd="lemma-crypto", timeout=120)
    if success:
        print("✅ Quick benchmark completed")
        # Try to extract some timing information
        lines = stdout.split('\n')
        for line in lines:
            if 'time:' in line:
                print(f"📊 {line.strip()}")
    else:
        print("⚠️  Quick benchmark failed (this is okay for now):")
        print(stderr[:500])  # First 500 chars only
    
    print("\n🎉 All quick tests completed successfully!")
    print("🔗 For comprehensive testing, run: python test_phase3_4_optimizations.py")
    return 0

if __name__ == "__main__":
    exit(main()) 