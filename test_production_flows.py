#!/usr/bin/env python3
"""
Comprehensive Production Flow Validation
Validates Shield, Check, and Revoke flows for production readiness with edge cases
"""

import http.client
import json
import time
import sys
import datetime
import threading
import random
import concurrent.futures

def get_api_key():
    """Get the correct API key"""
    today = datetime.datetime.now().strftime('%Y%m%d')
    return f'dev_api_key_{today}'

def test_endpoint(path, method="GET", data=None, timeout=30):
    """Test an endpoint with improved error handling"""
    try:
        conn = http.client.HTTPConnection("localhost", 5000, timeout=timeout)
        
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": get_api_key()
        }
        
        body = None
        if data:
            body = json.dumps(data)
        
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        response_data = response.read().decode('utf-8')
        status = response.status
        conn.close()
        
        return status, response_data
        
    except Exception as e:
        return None, str(e)

def validate_response_format(response_data, expected_fields):
    """Validate response has expected fields"""
    try:
        data = json.loads(response_data)
        return all(field in data for field in expected_fields)
    except:
        return False

def test_concurrent_operations(num_threads=5):
    """Test concurrent credential operations"""
    print(f"\n🧪 CONCURRENT OPERATIONS TEST ({num_threads} threads)")
    
    def create_and_verify_credential(thread_id):
        """Create and verify a credential in one thread"""
        user_id = f"concurrent_test_{thread_id}_{int(time.time())}"
        
        # Create credential
        create_data = {
            "user_id": user_id,
            "attributes": {"isHuman": True, "thread_id": thread_id}
        }
        
        status, data = test_endpoint("/api/issue-credential", "POST", create_data)
        if status not in [200, 201]:
            return False, f"Thread {thread_id}: Create failed"
        
        # Parse credential
        try:
            result = json.loads(data)
            credential = result.get("credential")
            if not credential:
                return False, f"Thread {thread_id}: No credential returned"
        except:
            return False, f"Thread {thread_id}: Parse error"
        
        # Verify credential
        verify_data = {"credential": credential}
        status, data = test_endpoint("/api/verify-credential", "POST", verify_data)
        
        return status in [200, 201], f"Thread {thread_id}: {'Success' if status in [200, 201] else 'Verify failed'}"
    
    # Run concurrent tests
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(create_and_verify_credential, i) for i in range(num_threads)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    success_count = sum(1 for success, _ in results if success)
    success_rate = (success_count / num_threads) * 100
    
    print(f"✅ Concurrent test: {success_count}/{num_threads} ({success_rate:.1f}%) successful")
    return success_rate >= 80  # 80% success rate acceptable for concurrent ops

def test_revocation_propagation():
    """Test revocation propagation across multiple checks"""
    print("\n🔄 REVOCATION PROPAGATION TEST")
    
    # Create credential
    user_id = f"propagation_test_{int(time.time())}"
    create_data = {
        "user_id": user_id,
        "attributes": {"isHuman": True, "propagation_test": True}
    }
    
    status, data = test_endpoint("/api/issue-credential", "POST", create_data)
    if status not in [200, 201]:
        print("❌ Failed to create credential for propagation test")
        return False
    
    # Parse credential
    try:
        result = json.loads(data)
        credential = result.get("credential")
        credential_id = credential.get("id")
    except:
        print("❌ Failed to parse credential")
        return False
    
    # Verify initial status (should be valid)
    status_data = {"credentials": [{"id": credential_id}]}
    status, data = test_endpoint("/api/shield/status", "POST", status_data)
    
    if status != 200:
        print("❌ Initial status check failed")
        return False
    
    try:
        result = json.loads(data)
        initial_action = result.get("shield_action")
        if initial_action == "require_verification":
            print("❌ Credential already marked as revoked before revocation")
            return False
    except:
        print("❌ Failed to parse initial status")
        return False
    
    # Revoke credential
    revoke_data = {
        "credential_id": credential_id,
        "reason": "Propagation test",
        "revoked_by": "test_system"
    }
    
    status, data = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
    if status not in [200, 201]:
        print("❌ Revocation failed")
        return False
    
    # Wait for propagation
    time.sleep(2)
    
    # Test multiple status checks to ensure consistent revocation detection
    propagation_results = []
    for i in range(3):
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        if status == 200:
            try:
                result = json.loads(data)
                action = result.get("shield_action")
                revoked_count = result.get("revoked_count", 0)
                propagation_results.append(action == "require_verification" or revoked_count > 0)
            except:
                propagation_results.append(False)
        else:
            propagation_results.append(False)
        
        time.sleep(0.5)  # Small delay between checks
    
    consistent_revocation = all(propagation_results)
    print(f"✅ Propagation consistency: {sum(propagation_results)}/3 checks detected revocation")
    
    return consistent_revocation

def test_security_edge_cases():
    """Test security edge cases and malformed requests"""
    print("\n🔒 SECURITY EDGE CASES")
    
    edge_cases = []
    
    # Test 1: Invalid API key
    print("  Testing invalid API key...")
    conn = http.client.HTTPConnection("localhost", 5000, timeout=10)
    headers = {"Content-Type": "application/json", "X-API-Key": "invalid_key"}
    try:
        conn.request("GET", "/api/shield/config", None, headers)
        response = conn.getresponse()
        edge_cases.append(response.status in [401, 403])  # Should reject
        conn.close()
    except:
        edge_cases.append(False)
    
    # Test 2: Missing required fields
    print("  Testing missing required fields...")
    status, data = test_endpoint("/api/issue-credential", "POST", {})
    edge_cases.append(status == 400)  # Should return bad request
    
    # Test 3: Malformed JSON in revocation
    print("  Testing malformed requests...")
    status, data = test_endpoint("/api/shield/revoke-credential", "POST", {"invalid": "data"})
    edge_cases.append(status == 400)  # Should return bad request
    
    # Test 4: Non-existent credential revocation
    print("  Testing non-existent credential revocation...")
    revoke_data = {
        "credential_id": "non_existent_credential_12345",
        "reason": "Test",
        "revoked_by": "test"
    }
    status, data = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
    # Should handle gracefully (either 200 with warning or 404)
    edge_cases.append(status in [200, 404])
    
    passed_edge_cases = sum(edge_cases)
    total_edge_cases = len(edge_cases)
    
    print(f"✅ Security edge cases: {passed_edge_cases}/{total_edge_cases} handled correctly")
    return passed_edge_cases >= (total_edge_cases * 0.75)  # 75% pass rate

def main():
    """Comprehensive production readiness validation"""
    print("🚀 PRODUCTION FLOW VALIDATION")
    print("=" * 60)
    
    all_results = {}
    
    # Step 1: Basic Flow Validation (from final test)
    print("\n1️⃣ BASIC FLOW VALIDATION")
    basic_results = run_basic_flows()
    all_results.update(basic_results)
    
    # Step 2: Concurrent Operations
    concurrent_success = test_concurrent_operations()
    all_results['concurrent_operations'] = concurrent_success
    
    # Step 3: Revocation Propagation
    propagation_success = test_revocation_propagation()
    all_results['revocation_propagation'] = propagation_success
    
    # Step 4: Security Edge Cases
    security_success = test_security_edge_cases()
    all_results['security_edge_cases'] = security_success
    
    # Step 5: Performance Validation
    print("\n⚡ PERFORMANCE VALIDATION")
    performance_success = test_performance_requirements()
    all_results['performance'] = performance_success
    
    # Final Assessment
    print("\n" + "=" * 70)
    print("🎯 PRODUCTION READINESS ASSESSMENT")
    print("=" * 70)
    
    total_tests = len(all_results)
    passed_tests = sum(all_results.values())
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"Overall Success Rate: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
    
    # Critical assessments
    critical_flows = ['credential_creation', 'credential_verification', 'credential_revocation', 'revocation_detection']
    critical_passed = sum(1 for flow in critical_flows if all_results.get(flow, False))
    
    print(f"Critical Flows: {critical_passed}/{len(critical_flows)} ({'✅ PASS' if critical_passed == len(critical_flows) else '❌ FAIL'})")
    
    # Production readiness determination
    if success_rate >= 95 and critical_passed == len(critical_flows):
        print("\n🎉 PRODUCTION READY")
        print("✅ All three flows (Shield, Check, Revoke) working seamlessly")
        print("✅ Concurrent operations stable")
        print("✅ Revocation propagation consistent")
        print("✅ Security edge cases handled")
        print("✅ Performance requirements met")
        return 0
    elif success_rate >= 85:
        print("\n⚠️  MOSTLY READY - Minor Issues")
        print("Some non-critical tests failed but core flows are working")
        return 1
    else:
        print("\n❌ NOT READY - Major Issues Found")
        print("Critical flows or multiple systems failing")
        return 2

def run_basic_flows():
    """Run the basic three flows validation"""
    results = {}
    credential_data = None
    credential_id = None
    
    # Health Check
    status, data = test_endpoint("/api/health")
    results['health'] = status == 200
    
    # Shield Config
    status, data = test_endpoint("/api/shield/config")
    results['shield_config'] = status == 200
    
    # Create Credential
    create_data = {
        "user_id": f"prod_test_{int(time.time())}",
        "attributes": {"isHuman": True, "production_test": True}
    }
    
    status, data = test_endpoint("/api/issue-credential", "POST", create_data)
    if status in [200, 201]:
        try:
            result = json.loads(data)
            credential_data = result.get("credential")
            credential_id = credential_data.get("id") if credential_data else None
            results['credential_creation'] = bool(credential_id)
        except:
            results['credential_creation'] = False
    else:
        results['credential_creation'] = False
    
    # Verify Credential
    if credential_data:
        verify_data = {"credential": credential_data}
        status, data = test_endpoint("/api/verify-credential", "POST", verify_data)
        results['credential_verification'] = status in [200, 201]
    else:
        results['credential_verification'] = False
    
    # Shield Status
    if credential_id:
        status_data = {"credentials": [{"id": credential_id}]}
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        results['shield_status'] = status == 200
    else:
        results['shield_status'] = False
    
    # Revoke Credential
    if credential_id:
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Production test completion",
            "revoked_by": "prod_test"
        }
        status, data = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
        results['credential_revocation'] = status in [200, 201]
    else:
        results['credential_revocation'] = False
    
    # Revocation Detection
    if credential_id and results['credential_revocation']:
        time.sleep(1)
        status_data = {"credentials": [{"id": credential_id}]}
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        
        if status == 200:
            try:
                result = json.loads(data)
                shield_action = result.get("shield_action")
                revoked_count = result.get("revoked_count", 0)
                results['revocation_detection'] = (shield_action == "require_verification" or revoked_count > 0)
            except:
                results['revocation_detection'] = False
        else:
            results['revocation_detection'] = False
    else:
        results['revocation_detection'] = False
    
    return results

def test_performance_requirements():
    """Test performance requirements"""
    print("  Testing endpoint response times...")
    
    performance_results = []
    
    # Test health check performance (should be < 250ms)
    start_time = time.time()
    status, data = test_endpoint("/api/health")
    health_time = (time.time() - start_time) * 1000
    performance_results.append(health_time < 250 and status == 200)
    print(f"    Health check: {health_time:.1f}ms ({'✅' if health_time < 250 else '❌ >250ms'})")
    
    # Test shield config performance
    start_time = time.time()
    status, data = test_endpoint("/api/shield/config")
    config_time = (time.time() - start_time) * 1000
    performance_results.append(config_time < 1000 and status == 200)
    print(f"    Shield config: {config_time:.1f}ms ({'✅' if config_time < 1000 else '❌ >1000ms'})")
    
    passed = sum(performance_results)
    total = len(performance_results)
    print(f"✅ Performance: {passed}/{total} endpoints meet requirements")
    
    return passed == total

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 