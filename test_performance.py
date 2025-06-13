#!/usr/bin/env python3
"""
Performance Test for Lemma Verify Endpoint
Tests response times to ensure SLA compliance.
"""

import requests
import time
import json
from datetime import datetime

def test_endpoint_performance(base_url="http://localhost:5000", num_requests=5):
    """Test endpoint performance with multiple requests."""
    
    print("🚀 Lemma Endpoint Performance Test")
    print("=" * 50)
    
    response_times = []
    
    # Warm up the endpoint first
    print("🔥 Warming up endpoint...")
    try:
        requests.get(f"{base_url}/api/health", timeout=10)
        print("✅ Warmup complete")
    except Exception as e:
        print(f"❌ Warmup failed: {e}")
        return
    
    print(f"\n📊 Testing {num_requests} requests...")
    
    for i in range(num_requests):
        try:
            # Step 1: Generate a valid challenge
            challenge_response = requests.get(f"{base_url}/api/generate-challenge", timeout=5)
            if challenge_response.status_code != 200:
                print(f"❌ Request {i+1}: Challenge generation failed ({challenge_response.status_code})")
                continue
                
            challenge_data = challenge_response.json()
            challenge = challenge_data.get('challenge')
            
            if not challenge:
                print(f"❌ Request {i+1}: No challenge in response")
                continue
            
            # Step 2: Create test presentation with the valid challenge
            test_presentation = {
                "presentation": {
                    "@context": ["https://www.w3.org/2018/credentials/v1"],
                    "type": ["VerifiablePresentation"],
                    "verifiableCredential": [{
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiableCredential", "LemmaHumanCredential"],
                        "id": f"test-credential-{int(time.time())}-{i}",
                        "issuer": "did:lemma:test",
                        "issuanceDate": datetime.now().isoformat(),
                        "credentialSubject": {
                            "id": "did:user:test-user",
                            "isHuman": True
                        },
                        "proof": {
                            "type": "Ed25519Signature2020",
                            "created": datetime.now().isoformat(),
                            "proofPurpose": "assertionMethod",
                            "verificationMethod": "did:lemma:test#key-1",
                            "proofValue": "test-signature"
                        }
                    }],
                    "proof": {
                        "type": "Ed25519Signature2020",
                        "created": datetime.now().isoformat(),
                        "proofPurpose": "authentication",
                        "challenge": challenge,
                        "verificationMethod": "did:user:test-user#key-1",
                        "proofValue": "test-presentation-signature"
                    }
                },
                "challenge": challenge
            }
            
            # Step 3: Measure verification time
            start_time = time.time()
            response = requests.post(
                f"{base_url}/api/verify-presentation",
                json=test_presentation,
                timeout=10
            )
            response_time = (time.time() - start_time) * 1000
            response_times.append(response_time)
            
            status_icon = "✅" if response_time <= 150 else "❌"
            print(f"{status_icon} Request {i+1}: {response_time:.1f}ms (Status: {response.status_code})")
            
            if response.status_code == 200:
                result = response.json()
                if 'processing_time_ms' in result:
                    print(f"   Server processing time: {result['processing_time_ms']}ms")
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data.get('reason', error_data.get('error', 'Unknown'))}")
                except:
                    print(f"   Error: Status 400")
            
        except Exception as e:
            print(f"❌ Request {i+1} failed: {e}")
    
    if response_times:
        print(f"\n📈 Performance Summary:")
        print(f"   Average: {sum(response_times)/len(response_times):.1f}ms")
        print(f"   Min: {min(response_times):.1f}ms")
        print(f"   Max: {max(response_times):.1f}ms")
        print(f"   P95: {sorted(response_times)[int(len(response_times)*0.95)]:.1f}ms")
        
        sla_compliant = [t for t in response_times if t <= 150]
        compliance_rate = len(sla_compliant) / len(response_times) * 100
        print(f"   SLA Compliance (≤150ms): {compliance_rate:.1f}% ({len(sla_compliant)}/{len(response_times)})")
        
        if compliance_rate >= 95:
            print("🎉 SLA COMPLIANT - Ready for production!")
        else:
            print("⚠️  SLA NOT MET - Optimization needed")

if __name__ == "__main__":
    test_endpoint_performance() 