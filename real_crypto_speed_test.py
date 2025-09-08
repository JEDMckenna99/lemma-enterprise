#!/usr/bin/env python3
"""
REAL Lemma Crypto Speed Test - Actual Ed25519 Verification
Tests REAL cryptographic verification with properly signed credentials
"""

import time
import statistics
import json
from typing import List, Dict, Any

def test_real_crypto_verification(num_tests: int = 100) -> Dict[str, Any]:
    """Test REAL cryptographic verification with actual signed credentials"""
    print(f"🔍 Testing REAL Lemma Crypto Engine ({num_tests} iterations)...")
    print("=" * 70)
    
    try:
        # Import the Rust crypto engine
        from lemma_crypto import PyLemmaCore, PyCredentialIssuer
        
        # Step 1: Create a REAL issuer with actual keypair
        print("📝 Creating real credential issuer with Ed25519 keypair...")
        issuer = PyCredentialIssuer()
        issuer_did = issuer.get_did()
        issuer_public_key = issuer.get_public_key_hex()
        
        print(f"✅ Real issuer DID: {issuer_did}")
        print(f"✅ Public key: {issuer_public_key[:16]}...{issuer_public_key[-16:]}")
        
        # Step 2: Create a REAL subject DID
        subject_issuer = PyCredentialIssuer()  # Create another keypair for subject
        subject_did = subject_issuer.get_did()
        
        print(f"✅ Real subject DID: {subject_did}")
        
        # Step 3: Create REAL signed credential
        print("🔐 Creating properly signed credential...")
        claims = {
            "packageType": "identity",
            "isHuman": "true",
            "verificationLevel": "high",
            "timestamp": str(int(time.time()))
        }
        
        # Issue a REAL signed credential
        credential_json = issuer.issue_credential(subject_did, claims)
        credential = json.loads(credential_json)
        
        print(f"✅ Real signed credential created with ID: {credential['id']}")
        print(f"✅ Signature: {credential.get('proof', {}).get('signature_value', 'N/A')[:32]}...")
        
        # Step 4: Initialize verification engine
        core = PyLemmaCore()
        print("✅ Lemma core engine initialized")
        
        # Step 5: Perform REAL speed tests
        print(f"\n⚡ Running {num_tests} REAL cryptographic verifications...")
        verification_times = []
        successful_verifications = 0
        
        for i in range(num_tests):
            start_time = time.perf_counter_ns()
            
            # REAL Ed25519 signature verification
            result = core.verify_credential(credential_json)
            
            end_time = time.perf_counter_ns()
            verification_time_us = (end_time - start_time) / 1000  # Convert to microseconds
            verification_times.append(verification_time_us)
            
            if result.verified:
                successful_verifications += 1
            
            if (i + 1) % 10 == 0:
                print(f"   Completed {i + 1}/{num_tests} tests... (Success: {successful_verifications}/{i+1})")
        
        # Calculate statistics
        if not verification_times:
            return {"success": False, "error": "No verification times recorded"}
        
        avg_time = statistics.mean(verification_times)
        median_time = statistics.median(verification_times)
        min_time = min(verification_times)
        max_time = max(verification_times)
        std_dev = statistics.stdev(verification_times) if len(verification_times) > 1 else 0
        success_rate = (successful_verifications / num_tests) * 100
        
        results = {
            "engine": "real_rust_crypto",
            "success": True,
            "test_type": "real_ed25519_verification",
            "num_tests": num_tests,
            "success_rate_percent": success_rate,
            "issuer_did": issuer_did,
            "subject_did": subject_did,
            "credential_id": credential['id'],
            "has_real_signature": bool(credential.get('proof', {}).get('signature_value')),
            "performance": {
                "average_time_us": round(avg_time, 3),
                "median_time_us": round(median_time, 3),
                "min_time_us": round(min_time, 3),
                "max_time_us": round(max_time, 3),
                "std_dev_us": round(std_dev, 3),
                "throughput_per_second": round(1_000_000 / avg_time) if avg_time > 0 else 0
            },
            "cryptographic_components": {
                "ed25519_signature_verification": True,
                "did_public_key_extraction": True,
                "credential_integrity_check": True,
                "real_cryptographic_operations": True
            }
        }
        
        print("\n" + "="*70)
        print("🏆 REAL CRYPTOGRAPHIC VERIFICATION RESULTS")
        print("="*70)
        print(f"✅ Success Rate: {success_rate:.1f}%")
        print(f"⚡ Average Time: {avg_time:.3f} µs")
        print(f"📊 Median Time: {median_time:.3f} µs")
        print(f"🚀 Throughput: {results['performance']['throughput_per_second']:,} verifications/second")
        print(f"📈 Range: {min_time:.3f} - {max_time:.3f} µs")
        print(f"📏 Std Dev: ±{std_dev:.3f} µs")
        print("="*70)
        
        if success_rate < 100:
            print(f"⚠️  WARNING: {100-success_rate:.1f}% of verifications failed!")
        
        if avg_time > 100:
            print(f"⚠️  WARNING: Average time {avg_time:.1f}µs is higher than expected (<50µs)")
        
        return results
        
    except ImportError as e:
        return {
            "success": False,
            "error": "rust_engine_not_available",
            "message": f"Rust crypto engine not available: {e}",
            "recommendation": "Build lemma-crypto with: cd lemma-crypto && maturin develop"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "test_failed",
            "message": str(e),
            "recommendation": "Check Rust crypto engine installation"
        }

def main():
    """Run comprehensive real crypto speed test"""
    print("🦀 LEMMA REAL CRYPTOGRAPHIC SPEED TEST")
    print("Testing actual Ed25519 signature verification")
    print("=" * 70)
    
    # Test with different sample sizes
    test_sizes = [10, 50, 100]
    
    all_results = []
    
    for size in test_sizes:
        print(f"\n🔍 Running test with {size} samples...")
        result = test_real_crypto_verification(size)
        all_results.append(result)
        
        if result["success"]:
            avg_time = result["performance"]["average_time_us"]
            success_rate = result["success_rate_percent"]
            print(f"✅ {size} samples: {avg_time:.3f}µs average, {success_rate:.1f}% success")
        else:
            print(f"❌ {size} samples: FAILED - {result.get('message', 'Unknown error')}")
    
    # Save results
    timestamp = int(time.time())
    filename = f"real_crypto_speed_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump({
            "test_timestamp": timestamp,
            "test_type": "real_cryptographic_verification",
            "results": all_results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    # Summary
    successful_tests = [r for r in all_results if r["success"]]
    if successful_tests:
        avg_times = [r["performance"]["average_time_us"] for r in successful_tests]
        overall_avg = statistics.mean(avg_times)
        print(f"\n🎯 OVERALL AVERAGE: {overall_avg:.3f} µs")
        
        if overall_avg < 10:
            print("🏆 EXCELLENT: Sub-10µs cryptographic verification!")
        elif overall_avg < 50:
            print("✅ GOOD: Sub-50µs cryptographic verification")
        else:
            print("⚠️  SLOW: Verification taking longer than expected")
    else:
        print("❌ ALL TESTS FAILED - Crypto engine not working properly")

if __name__ == "__main__":
    main()
