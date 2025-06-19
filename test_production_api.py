#!/usr/bin/env python3
"""
Production API Testing Script for Lemma Shield
Tests real cryptographic implementations vs mock/demo versions
"""

import requests
import json
import time
from typing import Dict, Any

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_endpoint(endpoint: str, method: str = "GET", headers: Dict = None, data: Dict = None) -> Dict[str, Any]:
    """Test an API endpoint and return detailed response info"""
    url = f"{BASE_URL}{endpoint}"
    headers = headers or {}
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        return {
            "endpoint": endpoint,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response": response.text[:1000] if response.text else "",
            "json": response.json() if response.headers.get('content-type', '').startswith('application/json') else None
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "error": str(e)
        }

def main():
    print("=== LEMMA SHIELD PRODUCTION API TESTING ===\n")
    
    # Test basic health and service info
    print("1. HEALTH & SERVICE STATUS")
    health = test_endpoint("/api/health")
    print(f"Health Status: {health.get('status_code')} - {health.get('json', {}).get('status', 'N/A')}")
    print(f"Service: {health.get('json', {}).get('service', 'N/A')}")
    print(f"Version: {health.get('json', {}).get('version', 'N/A')}\n")
    
    # Test offline credential issuance
    print("2. OFFLINE CREDENTIAL ISSUANCE")
    offline_cred = test_endpoint("/api/issue-offline-credential", "POST", 
                                data={"user_id": "test_user", "credential_type": "human_verification"})
    print(f"Offline Credential Status: {offline_cred.get('status_code')}")
    if offline_cred.get('json'):
        cred_data = offline_cred['json']
        # Check for production vs mock implementations
        if 'offline_witness' in cred_data:
            witness = cred_data['offline_witness']
            print(f"Witness contains issuer_pk: {'issuer_pk' in witness}")
            print(f"Witness contains bloom_cascade: {'bloom_cascade' in witness}")
            print(f"Witness contains oprf_transcript: {'oprf_transcript' in witness}")
            print(f"Witness contains signature: {'witness_signature' in witness}")
            
            # Check if OPRF implementation is real or mock
            if 'oprf_transcript' in witness:
                oprf = witness['oprf_transcript']
                if isinstance(oprf, dict) and 'mock' in str(oprf).lower():
                    print("⚠️  OPRF IMPLEMENTATION: MOCK/DEMO DETECTED")
                else:
                    print("✅ OPRF IMPLEMENTATION: Appears production-ready")
    print()
    
    # Test OPRF endpoints
    print("3. OPRF ENDPOINTS")
    oprf_status = test_endpoint("/api/oprf/status")
    print(f"OPRF Status: {oprf_status.get('status_code')}")
    if oprf_status.get('status_code') == 401:
        print("OPRF endpoint requires authentication - testing with mock API key")
        oprf_with_key = test_endpoint("/api/oprf/status", headers={"X-API-Key": "test-key"})
        print(f"OPRF with key: {oprf_with_key.get('status_code')}")
    print()
    
    # Test revocation endpoints
    print("4. REVOCATION SYSTEM")
    revocation_status = test_endpoint("/api/revocation/status")
    print(f"Revocation Status: {revocation_status.get('status_code')}")
    
    revocation_data = test_endpoint("/api/revocation/data/test-issuer")
    print(f"Revocation Data: {revocation_data.get('status_code')}")
    if revocation_data.get('json'):
        rev_data = revocation_data['json']
        if 'bloom_cascade' in rev_data:
            cascade = rev_data['bloom_cascade']
            print(f"Bloom cascade contains levels: {len(cascade) if isinstance(cascade, list) else 'N/A'}")
            # Check for real Bloom filter vs string matching
            if isinstance(cascade, list) and len(cascade) > 0:
                first_level = cascade[0]
                if 'bit_array' in first_level or 'filter_data' in first_level:
                    print("✅ BLOOM FILTER: Real bit arrays detected")
                elif 'simple_hash' in str(first_level).lower() or 'mock' in str(first_level).lower():
                    print("⚠️  BLOOM FILTER: Simplified/mock implementation detected")
    print()
    
    # Test verification endpoints
    print("5. VERIFICATION SYSTEM")
    verify_formal = test_endpoint("/api/verify-formal", "POST", 
                                 data={"credential": "test", "proof": "test"})
    print(f"Formal Verification: {verify_formal.get('status_code')}")
    print()
    
    # Test SRE metrics
    print("6. SRE METRICS & OBSERVABILITY")
    sre_metrics = test_endpoint("/api/sre/metrics/verification")
    print(f"SRE Metrics: {sre_metrics.get('status_code')}")
    if sre_metrics.get('json'):
        metrics = sre_metrics['json']
        print(f"Verification latency P95: {metrics.get('verification_latency_p95_ms', 'N/A')}ms")
        print(f"Offline verification rate: {metrics.get('offline_verification_success_rate', 'N/A')}")
    print()
    
    # Test compliance endpoints
    print("7. COMPLIANCE & SECURITY")
    compliance = test_endpoint("/api/compliance/audit-log")
    print(f"Compliance Audit Log: {compliance.get('status_code')}")
    print()
    
    print("=== PRODUCTION READINESS ASSESSMENT ===")
    print("Based on API responses, checking for production vs mock implementations...")
    
    # Summary assessment would go here based on the responses
    print("\nTest completed. Review the output above for mock/demo implementations that need upgrading.")

if __name__ == "__main__":
    main() 