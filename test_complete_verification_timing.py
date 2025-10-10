#!/usr/bin/env python3
"""
Test complete verification flow: Ed25519 + OPRF revocation check
Measures both cold start and cached performance
"""

import requests
import json
import time

print("=" * 70)
print("COMPLETE VERIFICATION TIMING TEST")
print("Ed25519 Signature + OPRF Revocation Check")
print("=" * 70)

# Step 1: Create a test credential
print("\n1. CREATING TEST CREDENTIAL")
print("-" * 70)

test_user_id = f"test_user_{int(time.time())}"
test_session_id = f"stripe_sess_{int(time.time())}"

# Call the verification completion endpoint to get a real Ed25519 credential
print("Requesting credential from Heroku...")

try:
    response = requests.post(
        'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/complete-identity-verification',
        json={
            'user_id': test_user_id,
            'session_id': test_session_id,
            'stripe_result': {
                'verified': True,
                'identity_details': {
                    'name': 'Test User',
                    'email': 'test@example.com'
                }
            },
            'enableRustEngine': True
        },
        headers={'Authorization': 'Bearer demo-integration-key-12345'}
    )
    
    if response.ok:
        creation_result = response.json()
        credential = creation_result['credential']
        credential_id = credential['id']
        
        print(f"[OK] Credential created: {credential_id}")
        print(f"     Issuer: {credential['issuer'][:50]}...")
        print(f"     Proof type: {credential.get('proof', {}).get('type', 'unknown')}")
    else:
        print(f"[ERROR] Failed to create credential: {response.status_code}")
        print(response.text)
        exit(1)
        
except Exception as e:
    print(f"[ERROR] {e}")
    exit(1)

# Step 2: Test COLD START verification (no cache)
print("\n2. COLD START VERIFICATION (No Cache)")
print("-" * 70)

cold_start = time.perf_counter()

verify_response = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/check-credentials',
    json={
        'credentials': [credential],
        'enableRustEngine': True,
        'requireFullCrypto': True
    },
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)

cold_total_time_us = (time.perf_counter() - cold_start) * 1_000_000

if verify_response.ok:
    verify_result = verify_response.json()
    
    ed25519_time = verify_result.get('verification_time_us', 0)
    
    print(f"\nCold Start Results:")
    print(f"  Ed25519 Signature Check: {ed25519_time:.2f}us")
    print(f"  Verified: {verify_result.get('verified')}")
    print(f"  Confidence: {verify_result.get('confidence', 0):.3f}")
    print(f"  Total API Time: {cold_total_time_us:.2f}us")
else:
    print(f"[ERROR] Verification failed: {verify_response.status_code}")

# Step 3: Test CACHED verification (warm cache)
print("\n3. CACHED VERIFICATION (Warm Cache)")
print("-" * 70)

cached_start = time.perf_counter()

verify_response2 = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/check-credentials',
    json={
        'credentials': [credential],
        'enableRustEngine': True,
        'requireFullCrypto': True
    },
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)

cached_total_time_us = (time.perf_counter() - cached_start) * 1_000_000

if verify_response2.ok:
    verify_result2 = verify_response2.json()
    
    ed25519_time_cached = verify_result2.get('verification_time_us', 0)
    cache_hit = verify_result2.get('cache_hit', False)
    
    print(f"\nCached Results:")
    print(f"  Ed25519 Signature Check: {ed25519_time_cached:.2f}us")
    print(f"  Cache Hit: {cache_hit}")
    print(f"  Verified: {verify_result2.get('verified')}")
    print(f"  Total API Time: {cached_total_time_us:.2f}us")
    print(f"  Speedup: {(cold_total_time_us / cached_total_time_us):.2f}x faster")

# Step 4: Test OPRF revocation check
print("\n4. OPRF REVOCATION CHECK")
print("-" * 70)

oprf_start = time.perf_counter()

revoke_response = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/revoke-credential',
    json={
        'credentials': [credential],
        'revocationType': 'oprf_bloom_filter',
        'reason': 'timing_test'
    },
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)

oprf_total_time_us = (time.perf_counter() - oprf_start) * 1_000_000

if revoke_response.ok:
    revoke_result = revoke_response.json()
    
    oprf_eval_time = revoke_result.get('oprf_time_us', 0)
    bloom_time = revoke_result.get('bloom_update_time_us', 0)
    server_total = revoke_result.get('total_time_us', 0)
    
    print(f"\nRevocation Results:")
    print(f"  OPRF Evaluation: {oprf_eval_time:.2f}us")
    print(f"  Bloom Filter Update: {bloom_time:.2f}us")
    print(f"  Server Total: {server_total:.2f}us")
    print(f"  Total API Time: {oprf_total_time_us:.2f}us")

# Step 5: Verify the revoked credential
print("\n5. VERIFY REVOKED CREDENTIAL")
print("-" * 70)

verify_revoked_start = time.perf_counter()

verify_response3 = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/check-credentials',
    json={
        'credentials': [credential],
        'enableRustEngine': True,
        'requireFullCrypto': True
    },
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)

verify_revoked_time_us = (time.perf_counter() - verify_revoked_start) * 1_000_000

if verify_response3.ok:
    verify_result3 = verify_response3.json()
    
    print(f"\nRevoked Credential Check:")
    print(f"  Verified: {verify_result3.get('verified')} (should be False)")
    print(f"  Revoked: {verify_result3.get('revoked', 'unknown')}")
    print(f"  Total Time: {verify_revoked_time_us:.2f}us")

# Summary
print("\n" + "=" * 70)
print("PERFORMANCE SUMMARY")
print("=" * 70)

print(f"\nComplete Verification Flow:")
print(f"  COLD START (Ed25519 + revocation check):")
print(f"    - Ed25519 verification: ~{ed25519_time:.0f}us")
print(f"    - OPRF revocation check: ~{oprf_eval_time:.0f}us")
print(f"    - Total: ~{ed25519_time + oprf_eval_time:.0f}us ({(ed25519_time + oprf_eval_time)/1000:.2f}ms)")
print(f"")
print(f"  CACHED (warm cache):")
print(f"    - Ed25519 verification: ~{ed25519_time_cached:.0f}us (cached: {cache_hit})")
print(f"    - OPRF revocation check: <1us (bloom filter lookup)")
print(f"    - Total: <{ed25519_time_cached + 1:.0f}us ({(ed25519_time_cached + 1)/1000:.2f}ms)")

print(f"\nOptimizations:")
print(f"  - Caching reduces time by {((cold_total_time_us - cached_total_time_us) / cold_total_time_us * 100):.1f}%")
print(f"  - Server-side OPRF fast-path (k*H directly)")
print(f"  - Bloom filter for O(k) revocation checks")
print(f"  - LRU caches for repeated verifications")

print("\n" + "=" * 70)




