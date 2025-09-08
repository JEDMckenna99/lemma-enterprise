#!/usr/bin/env python3
"""
Test Heroku deployment with REAL vs FAKE credentials
Compare what we were measuring before vs actual crypto performance
"""

import time
import requests
import json
import statistics
from typing import Dict, Any, List

HEROKU_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_fake_credentials_heroku(num_tests: int = 50) -> Dict[str, Any]:
    """Test what we were measuring before - fake credentials"""
    print(f"🔍 Testing FAKE credentials (what we measured before) - {num_tests} tests")
    print("=" * 70)
    
    # This is what we were testing before - FAKE DIDs
    fake_credential = {
        "id": "test_credential_001",
        "issuer": "did:lemma:test_issuer",  # ❌ FAKE DID
        "subject": "did:lemma:test_subject",  # ❌ FAKE DID
        "claims": {
            "packageType": "identity",
            "isHuman": True,
            "verificationLevel": "high",
            "timestamp": int(time.time())
        }
    }
    
    verification_times = []
    successful_verifications = 0
    
    for i in range(num_tests):
        try:
            start_time = time.perf_counter_ns()
            
            response = requests.post(
                f"{HEROKU_URL}/api/sdk/verify-offline",
                json={"credential": fake_credential},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer demo-speed-test"
                },
                timeout=10
            )
            
            end_time = time.perf_counter_ns()
            total_time_us = (end_time - start_time) / 1000
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    successful_verifications += 1
                    # Get the claimed verification time
                    claimed_time = result.get('verification_time_us', total_time_us)
                    verification_times.append(claimed_time)
                else:
                    verification_times.append(total_time_us)
            else:
                verification_times.append(total_time_us)
                
            if (i + 1) % 10 == 0:
                print(f"   Completed {i + 1}/{num_tests} tests...")
                
        except Exception as e:
            print(f"   Error on test {i + 1}: {e}")
            verification_times.append(float('inf'))
    
    # Calculate statistics
    valid_times = [t for t in verification_times if t != float('inf')]
    if not valid_times:
        return {
            "success": False,
            "error": "No valid measurements",
            "test_type": "fake_credentials"
        }
    
    avg_time = statistics.mean(valid_times)
    median_time = statistics.median(valid_times)
    min_time = min(valid_times)
    max_time = max(valid_times)
    success_rate = (successful_verifications / num_tests) * 100
    
    return {
        "test_type": "fake_credentials_heroku",
        "success": True,
        "num_tests": num_tests,
        "success_rate_percent": success_rate,
        "credential_type": "FAKE DIDs (what we measured before)",
        "performance": {
            "average_time_us": round(avg_time, 3),
            "median_time_us": round(median_time, 3),
            "min_time_us": round(min_time, 3),
            "max_time_us": round(max_time, 3),
            "throughput_per_second": round(1_000_000 / avg_time) if avg_time > 0 else 0
        }
    }

def test_heroku_with_better_credentials(num_tests: int = 50) -> Dict[str, Any]:
    """Test with better formed credentials (still may not be properly signed)"""
    print(f"🔍 Testing BETTER credentials against Heroku - {num_tests} tests")
    print("=" * 70)
    
    # Try to create a more realistic credential structure
    better_credential = {
        "id": f"cred_{int(time.time())}",
        "issuer": "did:lemma:a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",  # 64-char hex
        "subject": "did:lemma:fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321",  # 64-char hex
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + (365 * 24 * 60 * 60),  # 1 year
        "claims": {
            "packageType": "identity",
            "isHuman": True,
            "verificationLevel": "high",
            "timestamp": int(time.time()),
            "verificationSource": "test"
        },
        "proof": {
            "type": "Ed25519Signature2020",
            "created": int(time.time()),
            "verificationMethod": "did:lemma:a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
            "signatureValue": "abcd1234" * 16  # 128-char fake signature
        }
    }
    
    verification_times = []
    successful_verifications = 0
    
    for i in range(num_tests):
        try:
            start_time = time.perf_counter_ns()
            
            response = requests.post(
                f"{HEROKU_URL}/api/sdk/verify-offline",
                json={"credential": better_credential},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer demo-speed-test"
                },
                timeout=10
            )
            
            end_time = time.perf_counter_ns()
            total_time_us = (end_time - start_time) / 1000
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    successful_verifications += 1
                    claimed_time = result.get('verification_time_us', total_time_us)
                    verification_times.append(claimed_time)
                else:
                    verification_times.append(total_time_us)
            else:
                verification_times.append(total_time_us)
                
            if (i + 1) % 10 == 0:
                print(f"   Completed {i + 1}/{num_tests} tests...")
                
        except Exception as e:
            print(f"   Error on test {i + 1}: {e}")
            verification_times.append(float('inf'))
    
    # Calculate statistics
    valid_times = [t for t in verification_times if t != float('inf')]
    if not valid_times:
        return {
            "success": False,
            "error": "No valid measurements",
            "test_type": "better_credentials"
        }
    
    avg_time = statistics.mean(valid_times)
    median_time = statistics.median(valid_times)
    min_time = min(valid_times)
    max_time = max(valid_times)
    success_rate = (successful_verifications / num_tests) * 100
    
    return {
        "test_type": "better_credentials_heroku",
        "success": True,
        "num_tests": num_tests,
        "success_rate_percent": success_rate,
        "credential_type": "Better formed DIDs (64-char hex)",
        "performance": {
            "average_time_us": round(avg_time, 3),
            "median_time_us": round(median_time, 3),
            "min_time_us": round(min_time, 3),
            "max_time_us": round(max_time, 3),
            "throughput_per_second": round(1_000_000 / avg_time) if avg_time > 0 else 0
        }
    }

def test_heroku_endpoint_response():
    """Test what the Heroku endpoint actually returns"""
    print("🔍 Testing Heroku endpoint response structure")
    print("=" * 50)
    
    test_credential = {
        "id": "test_001",
        "issuer": "did:lemma:test",
        "subject": "did:lemma:subject",
        "claims": {"packageType": "identity"}
    }
    
    try:
        response = requests.post(
            f"{HEROKU_URL}/api/sdk/verify-offline",
            json={"credential": test_credential},
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer demo-speed-test"
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        return response.json()
        
    except Exception as e:
        print(f"❌ Error testing endpoint: {e}")
        return None

def main():
    """Run comprehensive Heroku crypto tests"""
    print("🦀 HEROKU REAL vs FAKE CRYPTO COMPARISON")
    print("Testing what we were measuring vs what we should measure")
    print("=" * 70)
    
    # First, see what the endpoint returns
    print("\n" + "="*70)
    print("STEP 1: Test Heroku endpoint response")
    print("="*70)
    endpoint_response = test_heroku_endpoint_response()
    
    if not endpoint_response:
        print("❌ Cannot reach Heroku endpoint - aborting tests")
        return
    
    # Test what we were measuring before (fake credentials)
    print("\n" + "="*70)
    print("STEP 2: Test FAKE credentials (what we measured before)")
    print("="*70)
    fake_results = test_fake_credentials_heroku(25)
    
    # Test with better credentials
    print("\n" + "="*70)
    print("STEP 3: Test BETTER credentials")
    print("="*70)
    better_results = test_heroku_with_better_credentials(25)
    
    # Summary
    print("\n" + "="*70)
    print("🏆 HEROKU CRYPTO TEST RESULTS SUMMARY")
    print("="*70)
    
    if fake_results.get('success'):
        fake_avg = fake_results['performance']['average_time_us']
        fake_success = fake_results['success_rate_percent']
        print(f"❌ FAKE Credentials (what we measured): {fake_avg:.3f}μs avg, {fake_success:.1f}% success")
    
    if better_results.get('success'):
        better_avg = better_results['performance']['average_time_us']
        better_success = better_results['success_rate_percent']
        print(f"✅ BETTER Credentials: {better_avg:.3f}μs avg, {better_success:.1f}% success")
    
    # Analysis
    print("\n📊 ANALYSIS:")
    if fake_results.get('success') and better_results.get('success'):
        fake_avg = fake_results['performance']['average_time_us']
        better_avg = better_results['performance']['average_time_us']
        
        if abs(fake_avg - better_avg) < 1:
            print("⚠️  WARNING: Similar performance suggests both are measuring error handling, not crypto!")
        elif better_avg > fake_avg * 2:
            print("✅ GOOD: Better credentials take longer - suggests real crypto is happening")
        else:
            print("🤔 UNCLEAR: Performance difference is marginal")
    
    # Save results
    timestamp = int(time.time())
    results = {
        "test_timestamp": timestamp,
        "test_type": "heroku_fake_vs_real_comparison",
        "endpoint_response": endpoint_response,
        "fake_credentials_results": fake_results,
        "better_credentials_results": better_results
    }
    
    filename = f"heroku_crypto_comparison_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")

if __name__ == "__main__":
    main()
