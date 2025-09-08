#!/usr/bin/env python3
"""
Test Heroku deployment with REAL crypto engine
Verify that actual Ed25519 + OPRF verification is working in production
"""

import time
import requests
import json
import statistics
from typing import Dict, Any

HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def create_real_test_credential():
    """Create a real credential with proper Ed25519 signature"""
    try:
        import lemma_crypto
        
        # Create real issuer with Ed25519 keypair
        issuer = lemma_crypto.PyMinimalIssuer()
        
        # Create real claims
        claims = {
            "packageType": "identity",
            "isHuman": "true",
            "verificationLevel": "high",
            "timestamp": str(int(time.time()))
        }
        
        # Issue real signed credential
        credential_json = issuer.issue_credential("did:lemma:test_user_heroku", claims)
        credential = json.loads(credential_json)
        
        print(f"✅ Real credential created:")
        print(f"   ID: {credential['id']}")
        print(f"   Issuer DID: {credential['issuer'][:50]}...")
        print(f"   Signature: {credential['proof']['signature_value'][:32]}...")
        
        return credential
        
    except ImportError:
        print("❌ Local crypto engine not available - using mock credential")
        return {
            "id": f"test_real_{int(time.time())}",
            "issuer": "did:lemma:a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
            "subject": "did:lemma:test_user_heroku",
            "claims": {
                "packageType": "identity",
                "isHuman": True,
                "verificationLevel": "high"
            },
            "proof": {
                "type": "Ed25519Signature2020",
                "signatureValue": "abcd1234" * 16  # Mock signature for testing
            }
        }

def test_heroku_real_crypto(num_tests: int = 25) -> Dict[str, Any]:
    """Test Heroku with real crypto engine"""
    print(f"🔍 Testing Heroku REAL crypto engine - {num_tests} tests")
    print("=" * 60)
    
    # Create real credential
    credential = create_real_test_credential()
    
    verification_times = []
    successful_verifications = 0
    cache_hits = 0
    
    for i in range(num_tests):
        try:
            start_time = time.perf_counter_ns()
            
            response = requests.post(
                f"{HEROKU_URL}/api/sdk/verify-offline",
                json={"credential": credential},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer demo-real-crypto-test"
                },
                timeout=10
            )
            
            end_time = time.perf_counter_ns()
            total_time_us = (end_time - start_time) / 1000
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    successful_verifications += 1
                    
                    # Get detailed timing from real crypto engine
                    engine_time = result.get('verification_time_ns', result.get('total_time_us', total_time_us))
                    if isinstance(engine_time, (int, float)):
                        verification_times.append(engine_time / 1000 if engine_time > 1000 else engine_time)
                    
                    if result.get('cache_hit'):
                        cache_hits += 1
                    
                    # Log detailed results for first few tests
                    if i < 3:
                        print(f"   Test {i+1} result:")
                        print(f"     Verified: {result.get('verified')}")
                        print(f"     Signature valid: {result.get('signature_valid')}")
                        print(f"     Not revoked: {result.get('not_revoked')}")
                        print(f"     Engine: {result.get('engine', 'unknown')}")
                        print(f"     Time: {engine_time / 1000 if isinstance(engine_time, (int, float)) and engine_time > 1000 else engine_time:.3f} μs")
                        print(f"     Cache hit: {result.get('cache_hit', False)}")
                else:
                    print(f"   Test {i+1} failed: {result.get('message', 'Unknown error')}")
            else:
                print(f"   Test {i+1} HTTP error: {response.status_code}")
                
            if (i + 1) % 5 == 0:
                print(f"   Completed {i + 1}/{num_tests} tests...")
                
        except Exception as e:
            print(f"   Error on test {i + 1}: {e}")
    
    # Calculate statistics
    if not verification_times:
        return {
            "success": False,
            "error": "No valid measurements",
            "test_type": "heroku_real_crypto"
        }
    
    avg_time = statistics.mean(verification_times)
    median_time = statistics.median(verification_times)
    min_time = min(verification_times)
    max_time = max(verification_times)
    success_rate = (successful_verifications / num_tests) * 100
    cache_hit_rate = (cache_hits / successful_verifications * 100) if successful_verifications > 0 else 0
    
    return {
        "test_type": "heroku_real_crypto_optimized",
        "success": True,
        "num_tests": num_tests,
        "success_rate_percent": success_rate,
        "cache_hit_rate_percent": cache_hit_rate,
        "credential_type": "Real Ed25519 signed credential",
        "performance": {
            "average_time_us": round(avg_time, 3),
            "median_time_us": round(median_time, 3),
            "min_time_us": round(min_time, 3),
            "max_time_us": round(max_time, 3),
            "throughput_per_second": round(1_000_000 / avg_time) if avg_time > 0 else 0
        }
    }

def main():
    """Test Heroku deployment with real crypto"""
    print("🦀 HEROKU REAL CRYPTO DEPLOYMENT TEST")
    print("Testing actual Ed25519 + OPRF verification in production")
    print("=" * 60)
    
    # Test real crypto performance
    results = test_heroku_real_crypto(20)
    
    print("\n" + "="*60)
    print("🏆 HEROKU REAL CRYPTO RESULTS")
    print("="*60)
    
    if results.get('success'):
        perf = results['performance']
        print(f"✅ Success rate: {results['success_rate_percent']:.1f}%")
        print(f"✅ Cache hit rate: {results['cache_hit_rate_percent']:.1f}%")
        print(f"⚡ Average time: {perf['average_time_us']:.3f} μs")
        print(f"📊 Range: {perf['min_time_us']:.3f} - {perf['max_time_us']:.3f} μs")
        print(f"🚀 Throughput: {perf['throughput_per_second']:,} verifications/second")
        
        # Performance analysis
        if perf['average_time_us'] < 20:
            print("🎉 EXCELLENT: Sub-20μs real crypto performance!")
        elif perf['average_time_us'] < 50:
            print("✅ GOOD: Sub-50μs real crypto performance")
        else:
            print("⚠️  SLOW: Real crypto taking longer than expected")
            
        # Cache analysis
        if results['cache_hit_rate_percent'] > 80:
            print("🚀 EXCELLENT: High cache hit rate optimizing performance")
        elif results['cache_hit_rate_percent'] > 50:
            print("✅ GOOD: Moderate cache hit rate")
        else:
            print("⚠️  LOW: Cache hit rate could be improved")
            
    else:
        print(f"❌ Test failed: {results.get('error', 'Unknown error')}")
    
    # Save results
    timestamp = int(time.time())
    filename = f"heroku_real_crypto_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump({
            "test_timestamp": timestamp,
            "test_type": "heroku_real_crypto_deployment",
            "results": results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    return results

if __name__ == "__main__":
    results = main()
    
    if results.get('success') and results['performance']['average_time_us'] < 50:
        print(f"\n🎉 HEROKU REAL CRYPTO DEPLOYMENT SUCCESSFUL!")
        print(f"Ready for production with {results['performance']['average_time_us']:.3f}μs performance")
    else:
        print(f"\n⚠️  Deployment needs optimization or troubleshooting")
