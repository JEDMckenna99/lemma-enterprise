#!/usr/bin/env python3
"""Test OPRF on Heroku deployment"""

import requests
import json
import time

print("=" * 70)
print("HEROKU OPRF REVOCATION TEST")
print("=" * 70)

# Test credential
test_cred = {
    'id': f'cred_oprf_test_{int(time.time())}',
    'issuer': 'did:lemma:test',
    'claims': {'isHuman': 'true', 'packageType': 'identity'}
}

print(f"\nTest Credential: {test_cred['id']}")
print("\nCalling Heroku revocation API...")

start = time.perf_counter()
resp = requests.post(
    'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/revoke-credential',
    json={
        'credentials': [test_cred],
        'revocationType': 'oprf_bloom_filter',
        'reason': 'oprf_math_test'
    },
    headers={'Authorization': 'Bearer demo-integration-key-12345'}
)
api_time_us = (time.perf_counter() - start) * 1_000_000

if resp.ok:
    result = resp.json()
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    oprf_eval = result['results'][0]['oprf_evaluation']
    using_real_oprf = not oprf_eval.startswith('hash_')
    
    print(f"\nCryptography:")
    print(f"  Real OPRF (Ristretto255): {using_real_oprf}")
    print(f"  Privacy-Preserving: {'YES' if using_real_oprf else 'NO (SHA256 fallback)'}")
    
    print(f"\nOPRF Output:")
    print(f"  Evaluation: {oprf_eval[:64]}...")
    print(f"  Length: {len(oprf_eval)} hex characters")
    
    print(f"\nPerformance:")
    print(f"  OPRF Evaluation: {result['oprf_time_us']:.2f} microseconds")
    print(f"  Bloom Filter Update: {result['bloom_update_time_us']:.2f} microseconds")
    print(f"  Server Total: {result['total_time_us']:.2f} microseconds")
    print(f"  API Round-trip: {api_time_us:.2f} microseconds")
    
    print("\n" + "=" * 70)
    
    if using_real_oprf:
        print("SUCCESS: Real Ristretto255 OPRF is working!")
        print("\nMath being used:")
        print("  1. H = HashToCurve(credential_id)")
        print("  2. r = random_scalar()")
        print("  3. M = r * H (blinding)")
        print("  4. Z = k * M (server evaluation)")
        print("  5. N = r^(-1) * Z = k * H (unblinding)")
        print("  6. Output = serialize(N)")
    else:
        print("FALLBACK: Using SHA256 hash (not privacy-preserving)")
        print("  Output = sha256(credential_id)")
    
    print("=" * 70)
else:
    print(f"\nERROR: {resp.status_code}")
    print(resp.text)




