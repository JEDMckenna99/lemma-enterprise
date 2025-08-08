#!/usr/bin/env python3
"""
Test Federated Revocation System

This tests that when a lemma is revoked on one deployment (lemma-enterprise),
it gets properly distributed to all other deployments in the federated network.
"""
import json
import requests
import time
from typing import Dict, Any

# Test configuration
FEDERATED_NETWORK_ENDPOINTS = [
    "https://lemma-enterprise-0f6ba17076c1.herokuapp.com",      # Production lemma.id
    "https://lemma-identity-network-2d96786d6ffb.herokuapp.com", # Identity network
]

NETWORK_AUTH_KEY = "lemma_network_master_key_2024"

def test_federated_revocation():
    """Test that revocation works across the federated network"""
    
    print("🧪 Testing Federated Revocation System")
    print("=" * 50)
    
    # Test credential to revoke
    test_credential_id = f"test_federated_revocation_{int(time.time())}"
    test_oprf = f"test_oprf_evaluation_{int(time.time())}"
    test_bloom_hash = f"test_bloom_{int(time.time())}"
    
    print(f"📋 Test Credential ID: {test_credential_id}")
    print(f"🔐 Test OPRF Evaluation: {test_oprf[:32]}...")
    print()
    
    # Step 1: Test revocation distribution from first endpoint
    print("🌐 Step 1: Testing federated revocation distribution")
    
    source_endpoint = FEDERATED_NETWORK_ENDPOINTS[0]
    print(f"📡 Source: {source_endpoint}")
    
    try:
        response = requests.post(
            f"{source_endpoint}/api/sdk/revoke-credential",
            headers={
                'Content-Type': 'application/json',
            },
            json={
                'credentials': [test_credential_id],
                'reason': 'federated_test'
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Revocation request successful")
            
            if 'revocation_results' in result:
                for revocation in result['revocation_results']:
                    fed_results = revocation.get('federated_network_results', {})
                    successful = fed_results.get('successful_distributions', 0)
                    total = fed_results.get('total_endpoints', 0)
                    print(f"📊 Federated Distribution: {successful}/{total} successful")
                    
                    for endpoint_result in fed_results.get('results', []):
                        endpoint = endpoint_result['endpoint']
                        success = endpoint_result['success']
                        error = endpoint_result.get('error')
                        response_time = endpoint_result.get('response_time_ms', 0)
                        
                        status = "✅" if success else "❌"
                        print(f"  {status} {endpoint}: {response_time:.1f}ms {f'({error})' if error else ''}")
            
        else:
            print(f"❌ Revocation request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Revocation request error: {e}")
        return False
    
    print()
    
    # Step 2: Verify revocation on all endpoints
    print("🔍 Step 2: Verifying revocation across all endpoints")
    
    verification_results = []
    
    for endpoint in FEDERATED_NETWORK_ENDPOINTS:
        print(f"🔎 Checking: {endpoint}")
        
        try:
            response = requests.get(
                f"{endpoint}/api/network/check-revocation/{test_credential_id}",
                headers={
                    'Authorization': f'Network {NETWORK_AUTH_KEY}',
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                is_revoked = result.get('revoked', False)
                
                if is_revoked:
                    revoked_at = result.get('revoked_at', 'unknown')
                    reason = result.get('reason', 'unknown')
                    source = result.get('source_deployment', 'unknown')
                    federated = result.get('federated_revocation', False)
                    
                    print(f"  ✅ REVOKED - Reason: {reason}, Source: {source}, Federated: {federated}")
                    verification_results.append(True)
                else:
                    print(f"  ❌ NOT REVOKED")
                    verification_results.append(False)
            else:
                print(f"  ⚠️ Check failed: {response.status_code}")
                verification_results.append(False)
                
        except Exception as e:
            print(f"  ❌ Check error: {e}")
            verification_results.append(False)
    
    print()
    
    # Step 3: Results summary
    print("📊 Test Results Summary")
    print("=" * 30)
    
    successful_verifications = sum(verification_results)
    total_endpoints = len(FEDERATED_NETWORK_ENDPOINTS)
    success_rate = (successful_verifications / total_endpoints * 100) if total_endpoints > 0 else 0
    
    print(f"✅ Successful verifications: {successful_verifications}/{total_endpoints}")
    print(f"📈 Success rate: {success_rate:.1f}%")
    
    if success_rate >= 100:
        print("🎉 FEDERATED REVOCATION TEST PASSED!")
        print("✅ Lemma revoked on one deployment is properly invalidated across the entire network")
        return True
    elif success_rate >= 50:
        print("⚠️ PARTIAL SUCCESS - Some endpoints working")
        return False
    else:
        print("❌ FEDERATED REVOCATION TEST FAILED")
        print("❌ Revocation not properly distributed across network")
        return False

if __name__ == "__main__":
    success = test_federated_revocation()
    exit(0 if success else 1)
