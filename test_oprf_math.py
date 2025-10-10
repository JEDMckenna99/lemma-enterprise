#!/usr/bin/env python3
"""Test OPRF-based revocation system"""

import time
import json

print("=" * 70)
print("OPRF REVOCATION MATHEMATICAL TEST")
print("=" * 70)

print("\n1. CHECKING RUST OPRF AVAILABILITY")
print("-" * 70)

try:
    from lemma_crypto import PyOptimizedVerifier
    print("[OK] Rust engine imported")
    
    verifier = PyOptimizedVerifier()
    print("[OK] Optimized verifier created")
    
    # Check available methods
    methods = [m for m in dir(verifier) if not m.startswith('_')]
    print(f"\nAvailable methods ({len(methods)}):")
    for method in methods:
        print(f"   - {method}")
    
    # Check for OPRF
    has_oprf = hasattr(verifier, 'compute_oprf_evaluation')
    print(f"\nHas compute_oprf_evaluation: {has_oprf}")
    
    if has_oprf:
        print("\n2. TESTING OPRF EVALUATION")
        print("-" * 70)
        
        test_credential_id = "cred_17ce30c5-aafb-4436-b0c1-a758bf9ec199"
        print(f"Input: {test_credential_id}")
        
        # Test OPRF evaluation
        oprf_start = time.perf_counter()
        oprf_result = verifier.compute_oprf_evaluation(test_credential_id)
        oprf_time_us = (time.perf_counter() - oprf_start) * 1_000_000
        
        print(f"\n[OK] OPRF Evaluation Result:")
        print(f"   Output: {oprf_result[:64]}...")
        print(f"   Length: {len(oprf_result)} characters")
        print(f"   Time: {oprf_time_us:.2f} microseconds")
        
        # Test determinism
        oprf_result2 = verifier.compute_oprf_evaluation(test_credential_id)
        is_deterministic = oprf_result == oprf_result2
        print(f"\nDeterministic Test:")
        print(f"   Same input -> Same output: {is_deterministic}")
        
        # Test with different ID
        different_id = "cred_different_12345"
        oprf_result3 = verifier.compute_oprf_evaluation(different_id)
        is_different = oprf_result != oprf_result3
        print(f"   Different input -> Different output: {is_different}")
        
    else:
        print("\n[ERROR] OPRF method not found - using fallback hash")
        
except ImportError as e:
    print(f"[ERROR] Cannot import Rust engine: {e}")
except Exception as e:
    print(f"[ERROR] Error during OPRF test: {e}")
    import traceback
    traceback.print_exc()

# Test full revocation flow
print("\n\n3. TESTING FULL REVOCATION FLOW")
print("-" * 70)

try:
    import requests
    
    test_cred = {
        'id': f'cred_math_test_{int(time.time())}',
        'issuer': 'did:lemma:test',
        'claims': {'isHuman': 'true', 'packageType': 'identity'}
    }
    
    print(f"Test Credential ID: {test_cred['id']}")
    
    api_start = time.perf_counter()
    response = requests.post(
        'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/revoke-credential',
        json={'credentials': [test_cred], 'revocationType': 'oprf_bloom_filter', 'reason': 'math_test'},
        headers={'Authorization': 'Bearer demo-integration-key-12345'}
    )
    api_time_us = (time.perf_counter() - api_start) * 1_000_000
    
    if response.ok:
        result = response.json()
        print("\n[OK] Revocation API Response:")
        print(json.dumps(result, indent=2))
        
        if result.get('success'):
            oprf_time = result.get('oprf_time_us', 0)
            bloom_time = result.get('bloom_update_time_us', 0)
            total_time = result.get('total_time_us', 0)
            
            print(f"\nPERFORMANCE BREAKDOWN:")
            print(f"   OPRF Evaluation: {oprf_time:.2f} microseconds")
            print(f"   Bloom Filter Update: {bloom_time:.2f} microseconds")
            print(f"   Server Total: {total_time:.2f} microseconds")
            print(f"   Network Round-trip: {api_time_us:.2f} microseconds")
            
            oprf_eval = result['results'][0].get('oprf_evaluation', '')
            using_real_oprf = not oprf_eval.startswith('hash_')
            
            print(f"\nCRYPTOGRAPHY STATUS:")
            print(f"   Real OPRF (Ristretto255): {'YES' if using_real_oprf else 'NO (SHA256 fallback)'}")
            print(f"   Privacy-Preserving: {'YES' if using_real_oprf else 'LIMITED'}")
            
    else:
        print(f"\n[ERROR] API Error: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"\n[ERROR] Revocation test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)




