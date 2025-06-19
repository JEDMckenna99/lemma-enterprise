#!/usr/bin/env python3
"""
Production Shield API Testing Script
Tests the real Shield API endpoints to identify mock vs production cryptographic implementations
"""

import requests
import json
import time
from typing import Dict, Any

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_shield_endpoint(endpoint: str, method: str = "GET", headers: Dict = None, data: Dict = None) -> Dict[str, Any]:
    """Test a Shield API endpoint and return detailed response info"""
    url = f"{BASE_URL}/api/shield{endpoint}"
    headers = headers or {'Content-Type': 'application/json'}
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=15)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=15)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        return {
            "endpoint": endpoint,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response": response.text[:2000] if response.text else "",
            "json": response.json() if response.headers.get('content-type', '').startswith('application/json') else None
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "error": str(e)
        }

def analyze_cryptographic_implementation(response_data: Dict) -> Dict[str, str]:
    """Analyze response data to determine if cryptographic implementations are mock or production"""
    analysis = {
        "oprf_implementation": "unknown",
        "ed25519_implementation": "unknown", 
        "bloom_filter_implementation": "unknown",
        "witness_implementation": "unknown"
    }
    
    if not response_data.get('json'):
        return analysis
    
    json_data = response_data['json']
    
    # Check for mock indicators in the response
    response_str = str(json_data).lower()
    
    # OPRF implementation check
    if 'oprf' in response_str:
        if any(keyword in response_str for keyword in ['mock', 'demo', 'simplified', 'test']):
            analysis["oprf_implementation"] = "MOCK/DEMO"
        elif 'oprf_transcript' in response_str or 'oprf_evaluation' in response_str:
            analysis["oprf_implementation"] = "PRODUCTION-READY"
    
    # Ed25519 signature check
    if 'signature' in response_str or 'ed25519' in response_str:
        if any(keyword in response_str for keyword in ['mock', 'demo', 'simplified']):
            analysis["ed25519_implementation"] = "MOCK/DEMO"
        elif 'signature_valid' in response_str or 'ed25519' in response_str:
            analysis["ed25519_implementation"] = "PRODUCTION-READY"
    
    # Bloom filter check
    if 'bloom' in response_str or 'revocation' in response_str:
        if any(keyword in response_str for keyword in ['mock', 'simple_hash', 'string_match']):
            analysis["bloom_filter_implementation"] = "MOCK/DEMO"
        elif 'bit_array' in response_str or 'filter_data' in response_str:
            analysis["bloom_filter_implementation"] = "PRODUCTION-READY"
    
    # Witness implementation check
    if 'witness' in response_str or 'offline_witness' in response_str:
        if any(keyword in response_str for keyword in ['mock', 'demo', 'simplified']):
            analysis["witness_implementation"] = "MOCK/DEMO"
        elif 'witness_signature' in response_str and 'issuer_pk' in response_str:
            analysis["witness_implementation"] = "PRODUCTION-READY"
    
    return analysis

def main():
    print("=== LEMMA SHIELD API PRODUCTION TESTING ===\n")
    
    # Test 1: Shield Status (GET)
    print("1. SHIELD STATUS (GET) - Session-based check")
    status_get = test_shield_endpoint("/status", "GET")
    print(f"Status Code: {status_get.get('status_code')}")
    if status_get.get('json'):
        shield_action = status_get['json'].get('shield_action', 'N/A')
        print(f"Shield Action: {shield_action}")
        print(f"Success: {status_get['json'].get('success', 'N/A')}")
    print()
    
    # Test 2: Shield Status (POST) - With mock credential
    print("2. SHIELD STATUS (POST) - Credential verification")
    mock_credential = {
        "id": "did:example:test-credential-123",
        "issuer": "did:example:lemma-issuer",
        "offline_capable": True,
        "offline_witness": {
            "issuer_pk": "mock_public_key_12345",
            "bloom_cascade": ["mock_bloom_level_1", "mock_bloom_level_2"],
            "oprf_transcript": {"mock": "oprf_data"},
            "valid_until": int(time.time()) + 86400,  # Valid for 24 hours
            "witness_signature": "mock_signature_data"
        },
        "proof": {
            "jws": "mock_signature_12345"
        }
    }
    
    status_post = test_shield_endpoint("/status", "POST", data={"credential": mock_credential})
    print(f"Status Code: {status_post.get('status_code')}")
    if status_post.get('json'):
        shield_action = status_post['json'].get('shield_action', 'N/A')
        verification_mode = status_post['json'].get('verification_mode', 'N/A')
        offline_verification = status_post['json'].get('offline_verification', 'N/A')
        print(f"Shield Action: {shield_action}")
        print(f"Verification Mode: {verification_mode}")
        print(f"Offline Verification: {offline_verification}")
        
        # Analyze cryptographic implementations
        crypto_analysis = analyze_cryptographic_implementation(status_post)
        print("\n📊 CRYPTOGRAPHIC IMPLEMENTATION ANALYSIS:")
        for component, status in crypto_analysis.items():
            icon = "⚠️" if "MOCK" in status else "✅" if "PRODUCTION" in status else "❓"
            print(f"  {icon} {component.replace('_', ' ').title()}: {status}")
    print()
    
    # Test 3: Offline Verification API
    print("3. OFFLINE VERIFICATION API")
    offline_verify = test_shield_endpoint("", "POST", 
                                        data={"credential": mock_credential},
                                        headers={'Content-Type': 'application/json'})
    
    # Try the actual offline verification endpoint
    try:
        offline_url = f"{BASE_URL}/api/verify-offline"
        offline_response = requests.post(offline_url, 
                                       json={"credential": mock_credential},
                                       headers={'Content-Type': 'application/json'},
                                       timeout=15)
        print(f"Offline Verification Status: {offline_response.status_code}")
        if offline_response.status_code == 200:
            offline_data = offline_response.json()
            print(f"Success: {offline_data.get('success', 'N/A')}")
            print(f"Verification Mode: {offline_data.get('verification_mode', 'N/A')}")
            print(f"API Calls Made: {offline_data.get('api_calls_made', 'N/A')}")
            print(f"Verification Time: {offline_data.get('verification_time_ms', 'N/A')}ms")
            
            # Check for mock implementations in offline verification
            offline_analysis = analyze_cryptographic_implementation({"json": offline_data})
            print("\n📊 OFFLINE VERIFICATION CRYPTO ANALYSIS:")
            for component, status in offline_analysis.items():
                icon = "⚠️" if "MOCK" in status else "✅" if "PRODUCTION" in status else "❓"
                print(f"  {icon} {component.replace('_', ' ').title()}: {status}")
        else:
            print(f"Error: {offline_response.text[:500]}")
    except Exception as e:
        print(f"Offline verification test failed: {e}")
    print()
    
    # Test 4: OPRF Status (with API key)
    print("4. OPRF ENDPOINTS")
    try:
        oprf_url = f"{BASE_URL}/api/oprf/status"
        # Try without API key first
        oprf_response = requests.get(oprf_url, timeout=10)
        print(f"OPRF Status (no key): {oprf_response.status_code}")
        
        # Try with mock API key
        oprf_with_key = requests.get(oprf_url, 
                                   headers={"X-API-Key": "test-key"},
                                   timeout=10)
        print(f"OPRF Status (with key): {oprf_with_key.status_code}")
        if oprf_with_key.status_code == 200:
            oprf_data = oprf_with_key.json()
            print(f"OPRF Service Status: {oprf_data.get('oprf_service', 'N/A')}")
            print(f"Cascade Status: {oprf_data.get('oprf_response', {}).get('cascade_status', 'N/A')}")
    except Exception as e:
        print(f"OPRF test failed: {e}")
    print()
    
    # Test 5: Cascade Data
    print("5. REVOCATION CASCADE")
    try:
        cascade_url = f"{BASE_URL}/api/cascade/latest"
        cascade_response = requests.get(cascade_url, timeout=10)
        print(f"Cascade Status: {cascade_response.status_code}")
        if cascade_response.status_code == 200:
            cascade_data = cascade_response.json()
            if 'bloom_cascade' in cascade_data:
                cascade_levels = len(cascade_data['bloom_cascade']) if isinstance(cascade_data['bloom_cascade'], list) else 0
                print(f"Cascade Levels: {cascade_levels}")
                
                # Check bloom filter implementation
                if cascade_levels > 0:
                    first_level = cascade_data['bloom_cascade'][0]
                    if 'bit_array' in str(first_level) or 'filter_data' in str(first_level):
                        print("✅ BLOOM FILTER: Real bit arrays detected")
                    elif 'mock' in str(first_level).lower() or 'simple' in str(first_level).lower():
                        print("⚠️  BLOOM FILTER: Mock/simplified implementation detected")
                    else:
                        print("❓ BLOOM FILTER: Implementation unclear")
        else:
            print(f"Cascade error: {cascade_response.text[:200]}")
    except Exception as e:
        print(f"Cascade test failed: {e}")
    print()
    
    print("=== PRODUCTION READINESS SUMMARY ===")
    print("✅ = Production-ready implementation")
    print("⚠️  = Mock/demo implementation (needs upgrade)")
    print("❓ = Implementation status unclear")
    print("\nBased on the API responses above, identify which cryptographic")
    print("components are using mock/simplified implementations and need")
    print("to be upgraded to production-grade cryptographic libraries.")

if __name__ == "__main__":
    main() 