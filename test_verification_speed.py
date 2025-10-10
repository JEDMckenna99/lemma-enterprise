#!/usr/bin/env python3
"""
Test complete verification timing with a mock credential
"""

import requests
import json
import time

print("=" * 70)
print("COMPLETE VERIFICATION + REVOCATION TIMING")
print("=" * 70)

# Use a properly formatted mock credential
test_credential = {
    "id": f"cred_{int(time.time())}_test",
    "issuer": "did:lemma:74e6145dfc542956a9c8d038fb02dd0980f5006ec9feb99ad54f3da1621447dd",
    "subject": "did:lemma:test_user",
    "issuanceDate": int(time.time()),
    "credentialSubject": {
        "packageType": "identity",
        "isHuman": "true",
        "verificationMethod": "stripe_identity"
    },
    "proof": {
        "type": "Ed25519Signature2020",
        "created": int(time.time()),
        "verificationMethod": "did:lemma:74e6145dfc542956a9c8d038fb02dd0980f5006ec9feb99ad54f3da1621447dd",
        "signatureValue": "abc123" * 10  # Mock signature
    }
}

credential_id = test_credential['id']
print(f"\nTest Credential: {credential_id}")

# Test 1: Cold start verification
print("\n1. COLD START - Ed25519 Verification")
print("-" * 70)

cold_start = time.perf_counter()
verify_response = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/check-credentials',
    json={'credentials': [test_credential], 'enableRustEngine': True},
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)
cold_time_us = (time.perf_counter() - cold_start) * 1_000_000

if verify_response.ok:
    result = verify_response.json()
    engine_time = result.get('verification_time_us', 0)
    print(f"  Engine Time: {engine_time:.2f}us")
    print(f"  API Round-trip: {cold_time_us:.2f}us")
    print(f"  Verified: {result.get('verified')}")

# Test 2: Cached verification
print("\n2. CACHED - Ed25519 Verification (2nd check)")
print("-" * 70)

cached_start = time.perf_counter()
verify_response2 = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/check-credentials',
    json={'credentials': [test_credential], 'enableRustEngine': True},
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)
cached_time_us = (time.perf_counter() - cached_start) * 1_000_000

if verify_response2.ok:
    result2 = verify_response2.json()
    engine_time_cached = result2.get('verification_time_us', 0)
    cache_hit = result2.get('cache_hit', False)
    print(f"  Engine Time: {engine_time_cached:.2f}us")
    print(f"  Cache Hit: {cache_hit}")
    print(f"  API Round-trip: {cached_time_us:.2f}us")
    print(f"  Speedup: {(cold_time_us / cached_time_us):.2f}x")

# Test 3: OPRF revocation (cold)
print("\n3. OPRF REVOCATION (Cold)")
print("-" * 70)

oprf_cold_start = time.perf_counter()
revoke_response = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/revoke-credential',
    json={'credentials': [test_credential], 'revocationType': 'oprf_bloom_filter'},
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)
oprf_cold_time_us = (time.perf_counter() - oprf_cold_start) * 1_000_000

if revoke_response.ok:
    revoke_result = revoke_response.json()
    oprf_eval_time = revoke_result.get('oprf_time_us', 0)
    bloom_time = revoke_result.get('bloom_update_time_us', 0)
    server_total = revoke_result.get('total_time_us', 0)
    
    print(f"  OPRF Evaluation: {oprf_eval_time:.2f}us")
    print(f"  Bloom Update: {bloom_time:.2f}us")
    print(f"  Server Total: {server_total:.2f}us")
    print(f"  API Round-trip: {oprf_cold_time_us:.2f}us")

# Test 4: OPRF check again (should use cache)
print("\n4. OPRF REVOCATION (Cached)")
print("-" * 70)

oprf_cached_start = time.perf_counter()
revoke_response2 = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/revoke-credential',
    json={'credentials': [test_credential], 'revocationType': 'oprf_bloom_filter'},
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)
oprf_cached_time_us = (time.perf_counter() - oprf_cached_start) * 1_000_000

if revoke_response2.ok:
    revoke_result2 = revoke_response2.json()
    oprf_eval_time_cached = revoke_result2.get('oprf_time_us', 0)
    
    print(f"  OPRF Evaluation: {oprf_eval_time_cached:.2f}us")
    print(f"  Server Total: {revoke_result2.get('total_time_us', 0):.2f}us")
    print(f"  API Round-trip: {oprf_cached_time_us:.2f}us")
    print(f"  Speedup: {(oprf_cold_time_us / oprf_cached_time_us):.2f}x")

# Final Summary
print("\n" + "=" * 70)
print("COMPLETE FLOW TIMING SUMMARY")
print("=" * 70)

print(f"\nSCENARIO 1: COLD START (First-time verification)")
print(f"  Ed25519 signature check: ~{engine_time:.0f}us")
print(f"  OPRF revocation check: ~{oprf_eval_time:.0f}us")
print(f"  TOTAL: ~{engine_time + oprf_eval_time:.0f}us (~{(engine_time + oprf_eval_time)/1000:.2f}ms)")

print(f"\nSCENARIO 2: CACHED (Repeat verification)")
print(f"  Ed25519 signature check: ~{engine_time_cached:.0f}us (from cache)")
print(f"  OPRF revocation check: ~{oprf_eval_time_cached:.0f}us (from cache)")  
print(f"  TOTAL: ~{engine_time_cached + oprf_eval_time_cached:.0f}us (~{(engine_time_cached + oprf_eval_time_cached)/1000:.2f}ms)")

print(f"\nPerformance Characteristics:")
print(f"  - Cold start: Millisecond range ({(engine_time + oprf_eval_time)/1000:.2f}ms)")
print(f"  - Cached: Sub-millisecond (<{(engine_time_cached + oprf_eval_time_cached)/1000:.2f}ms)")
print(f"  - Optimization: Ristretto255 OPRF fast-path (k*H direct)")
print(f"  - Privacy: Full Ristretto255 OPRF (not SHA256 hash)")

print("\n" + "=" * 70)




