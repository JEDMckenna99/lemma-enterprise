#!/usr/bin/env python3
"""
Test real Ed25519 + OPRF timing by creating valid credentials
"""

import time

print("=" * 70)
print("REAL VERIFICATION TIMING TEST")
print("=" * 70)

# Import Rust engine locally
try:
    from lemma_crypto import PyOptimizedVerifier, PyMinimalIssuer
    print("\n[OK] Rust engine imported locally")
    
    # Create issuer and credential
    print("\n1. CREATING REAL Ed25519 CREDENTIAL")
    print("-" * 70)
    
    issuer = PyMinimalIssuer()
    issuer_did = issuer.get_did()
    print(f"Issuer DID: {issuer_did[:50]}...")
    
    # Issue a credential
    credential_json = issuer.issue_credential(
        "did:lemma:test_user",
        {
            "packageType": "identity",
            "isHuman": "true",
            "verificationMethod": "test"
        }
    )
    
    import json
    credential = json.loads(credential_json)
    credential_id = credential['id']
    
    print(f"Credential ID: {credential_id}")
    print(f"Proof Type: {credential['proof']['type']}")
    
    # Test Ed25519 verification timing
    print("\n2. Ed25519 VERIFICATION TIMING")
    print("-" * 70)
    
    verifier = PyOptimizedVerifier()
    
    # Cold start (first verification)
    print("\nCold Start:")
    cold_times = []
    for i in range(10):
        start = time.perf_counter()
        result = verifier.verify_credential(credential_json)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        cold_times.append(elapsed_us)
        if i == 0:
            print(f"  First run: {elapsed_us:.2f}us (verified: {result.verified})")
    
    avg_cold = sum(cold_times) / len(cold_times)
    print(f"  Average (10 runs): {avg_cold:.2f}us")
    print(f"  Min: {min(cold_times):.2f}us")
    print(f"  Max: {max(cold_times):.2f}us")
    
    # Warm cache (cached verification)
    print("\nWarm Cache:")
    warm_times = []
    for i in range(100):
        start = time.perf_counter()
        result = verifier.verify_credential(credential_json)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        warm_times.append(elapsed_us)
    
    avg_warm = sum(warm_times) / len(warm_times)
    print(f"  Average (100 runs): {avg_warm:.2f}us")
    print(f"  Min: {min(warm_times):.2f}us")
    print(f"  Cache hit: {result.cache_hit}")
    
    # Test OPRF evaluation timing
    print("\n3. OPRF REVOCATION CHECK TIMING")
    print("-" * 70)
    
    # Cold start
    print("\nCold Start:")
    oprf_cold_times = []
    for i in range(10):
        start = time.perf_counter()
        oprf_result = verifier.compute_oprf_evaluation(credential_id)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        oprf_cold_times.append(elapsed_us)
        if i == 0:
            print(f"  First run: {elapsed_us:.2f}us")
            print(f"  Output: {oprf_result[:64]}...")
    
    avg_oprf_cold = sum(oprf_cold_times) / len(oprf_cold_times)
    print(f"  Average (10 runs): {avg_oprf_cold:.2f}us")
    print(f"  Min: {min(oprf_cold_times):.2f}us")
    
    # Warm cache
    print("\nWarm Cache:")
    oprf_warm_times = []
    for i in range(100):
        start = time.perf_counter()
        oprf_result = verifier.compute_oprf_evaluation(credential_id)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        oprf_warm_times.append(elapsed_us)
    
    avg_oprf_warm = sum(oprf_warm_times) / len(oprf_warm_times)
    print(f"  Average (100 runs): {avg_oprf_warm:.2f}us")
    print(f"  Min: {min(oprf_warm_times):.2f}us")
    
    # Summary
    print("\n" + "=" * 70)
    print("TIMING SUMMARY")
    print("=" * 70)
    
    print(f"\nCOLD START (First verification):")
    print(f"  Ed25519 verification: {avg_cold:.2f}us")
    print(f"  OPRF revocation check: {avg_oprf_cold:.2f}us")
    print(f"  TOTAL: {avg_cold + avg_oprf_cold:.2f}us ({(avg_cold + avg_oprf_cold)/1000:.3f}ms)")
    
    print(f"\nWARM CACHE (Cached verification):")
    print(f"  Ed25519 verification: {avg_warm:.2f}us")
    print(f"  OPRF revocation check: {avg_oprf_warm:.2f}us")
    print(f"  TOTAL: {avg_warm + avg_oprf_warm:.2f}us ({(avg_warm + avg_oprf_warm)/1000:.3f}ms)")
    
    print(f"\nSpeedup from caching:")
    print(f"  Ed25519: {avg_cold / avg_warm:.2f}x faster")
    print(f"  OPRF: {avg_oprf_cold / avg_oprf_warm:.2f}x faster")
    print(f"  Overall: {(avg_cold + avg_oprf_cold) / (avg_warm + avg_oprf_warm):.2f}x faster")
    
    print("\n" + "=" * 70)
    
except ImportError as e:
    print(f"\n[ERROR] Cannot import Rust engine: {e}")
    print("This test requires lemma_crypto to be installed")
except Exception as e:
    print(f"\n[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()




