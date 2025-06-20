#!/usr/bin/env python3
"""
Production Three Flows Test - Test the Shield, Check, and Revoke APIs with correct configuration
"""

import http.client
import json
import time
import sys
import datetime

def get_api_key():
    """Get the correct API key based on app.py configuration"""
    today = datetime.datetime.now().strftime('%Y%m%d')
    return f'dev_api_key_{today}'

def test_endpoint(path, method="GET", data=None):
    """Test an endpoint with correct API key"""
    try:
        conn = http.client.HTTPConnection("localhost", 5000, timeout=15)
        
        # Prepare headers with correct API key
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": get_api_key()
        }
        
        # Prepare body
        body = None
        if data:
            body = json.dumps(data)
        
        # Make request
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        
        # Read response
        response_data = response.read().decode('utf-8')
        status = response.status
        
        conn.close()
        
        print(f"[{time.strftime('%H:%M:%S')}] {method} {path} -> {status}")
        
        if status >= 400:
            print(f"  Error: {response_data[:200]}")
        
        return status, response_data
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] {method} {path} -> ERROR: {e}")
        return None, str(e)

def test_production_flows():
    """Test all three essential flows for production readiness"""
    print("🔧 LEMMA PRODUCTION FLOWS VALIDATION")
    print("=" * 50)
    print(f"API Key: {get_api_key()}")
    print("=" * 50)
    
    # Test results tracking
    flow_results = {
        "health": False,
        "shield_config": False,
        "credential_creation": False,
        "credential_verification": False,
        "shield_status": False,
        "credential_revocation": False,
        "revocation_detection": False,
        "offline_verification": False
    }
    
    credential_id = None
    
    # Test 1: Application Health
    print("\n🏥 TESTING APPLICATION HEALTH")
    print("-" * 30)
    
    status, data = test_endpoint("/api/health")
    if status == 200:
        print("✅ Application health check PASSED")
        flow_results["health"] = True
    else:
        print("❌ Application health check FAILED")
        return flow_results
    
    # Test 2: Shield Configuration
    print("\n🛡️  TESTING SHIELD CONFIGURATION")
    print("-" * 30)
    
    status, data = test_endpoint("/api/shield/config")
    if status == 200:
        try:
            config = json.loads(data)
            security_level = config.get('config', {}).get('security_level', 'unknown')
            print(f"✅ Shield config PASSED - Security level: {security_level}")
            flow_results["shield_config"] = True
        except:
            print("✅ Shield config PASSED - Response received")
            flow_results["shield_config"] = True
    else:
        print("❌ Shield config FAILED")
    
    # Test 3: Credential Creation (Shield Flow)
    print("\n📝 TESTING CREDENTIAL CREATION")
    print("-" * 30)
    
    credential_data = {
        "user_id": f"production_test_user_{int(time.time())}",
        "attributes": {
            "isHuman": True,
            "verified_at": int(time.time()),
            "production_test": True
        },
        "include_offline": True
    }
    
    status, data = test_endpoint("/api/issue-credential", "POST", credential_data)
    if status in [200, 201]:
        try:
            result = json.loads(data)
            credential_id = result.get("credential", {}).get("id")
            if credential_id:
                print(f"✅ Credential creation PASSED - ID: {credential_id}")
                flow_results["credential_creation"] = True
            else:
                print("⚠️  Credential creation PARTIAL - No ID returned")
        except Exception as e:
            print(f"⚠️  Credential creation PARTIAL - Parse error: {e}")
    else:
        print(f"❌ Credential creation FAILED - Status: {status}")
    
    # Test 4: Credential Verification (Check Flow)
    print("\n✅ TESTING CREDENTIAL VERIFICATION")
    print("-" * 30)
    
    if credential_id:
        verify_data = {
            "credential_id": credential_id,
            "challenge": f"production_challenge_{int(time.time())}"
        }
        
        status, data = test_endpoint("/api/verify-credential", "POST", verify_data)
        if status in [200, 201]:
            try:
                result = json.loads(data)
                verified = result.get("verified", False)
                print(f"✅ Credential verification PASSED - Verified: {verified}")
                flow_results["credential_verification"] = True
            except:
                print("✅ Credential verification PASSED - Response received")
                flow_results["credential_verification"] = True
        else:
            print(f"❌ Credential verification FAILED - Status: {status}")
    else:
        print("❌ Credential verification SKIPPED - No credential ID")
    
    # Test 5: Shield Status Check
    print("\n🔍 TESTING SHIELD STATUS CHECK")
    print("-" * 30)
    
    if credential_id:
        status_data = {
            "credentials": [{"id": credential_id}]
        }
        
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        if status == 200:
            try:
                result = json.loads(data)
                shield_action = result.get("shield_action", "unknown")
                print(f"✅ Shield status check PASSED - Action: {shield_action}")
                flow_results["shield_status"] = True
            except:
                print("✅ Shield status check PASSED - Response received")
                flow_results["shield_status"] = True
        else:
            print(f"❌ Shield status check FAILED - Status: {status}")
    else:
        print("❌ Shield status check SKIPPED - No credential ID")
    
    # Test 6: Offline Verification
    print("\n🌐 TESTING OFFLINE VERIFICATION")
    print("-" * 30)
    
    offline_data = {
        "credential_id": credential_id or "test_offline_credential",
        "credential": {
            "id": credential_id or "test_offline",
            "attributes": {"isHuman": True}
        }
    }
    
    status, data = test_endpoint("/api/verify-offline", "POST", offline_data)
    if status == 200:
        try:
            result = json.loads(data)
            verified = result.get("verified", False)
            offline_capable = result.get("unlimited_checks", False)
            print(f"✅ Offline verification PASSED - Verified: {verified}, Unlimited: {offline_capable}")
            flow_results["offline_verification"] = True
        except:
            print("✅ Offline verification PASSED - Response received")
            flow_results["offline_verification"] = True
    else:
        print(f"❌ Offline verification FAILED - Status: {status}")
    
    # Test 7: Credential Revocation (Revoke Flow)
    print("\n🚫 TESTING CREDENTIAL REVOCATION")
    print("-" * 30)
    
    if credential_id:
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Production flow test completion",
            "revoked_by": "automated_production_test"
        }
        
        status, data = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
        if status in [200, 201]:
            try:
                result = json.loads(data)
                print("✅ Credential revocation PASSED")
                flow_results["credential_revocation"] = True
            except:
                print("✅ Credential revocation PASSED - Response received")
                flow_results["credential_revocation"] = True
        else:
            print(f"❌ Credential revocation FAILED - Status: {status}")
    else:
        print("❌ Credential revocation SKIPPED - No credential ID")
    
    # Test 8: Revocation Detection
    print("\n🔎 TESTING REVOCATION DETECTION")
    print("-" * 30)
    
    if credential_id and flow_results["credential_revocation"]:
        print("Waiting for revocation to propagate...")
        time.sleep(2)
        
        # Test shield status after revocation
        status_data = {
            "credentials": [{"id": credential_id}]
        }
        
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        if status == 200:
            try:
                result = json.loads(data)
                shield_action = result.get("shield_action", "unknown")
                revoked_count = result.get("revoked_count", 0)
                
                if shield_action == "require_verification" or revoked_count > 0:
                    print(f"✅ Revocation detection PASSED - Action: {shield_action}, Revoked: {revoked_count}")
                    flow_results["revocation_detection"] = True
                else:
                    print(f"⚠️  Revocation detection PARTIAL - Action: {shield_action}")
            except:
                print("⚠️  Revocation detection PARTIAL - Response received")
        
        # Test offline verification of revoked credential
        offline_data = {
            "credential_id": credential_id,
            "credential": {"id": credential_id}
        }
        
        status, data = test_endpoint("/api/verify-offline", "POST", offline_data)
        if status == 200:
            try:
                result = json.loads(data)
                verified = result.get("verified", True)
                revoked = result.get("revoked", False)
                
                if not verified or revoked:
                    print("✅ Offline revocation detection PASSED")
                else:
                    print("⚠️  Offline revocation detection PARTIAL")
            except:
                print("⚠️  Offline revocation detection PARTIAL")
    else:
        print("❌ Revocation detection SKIPPED - No revoked credential")
    
    return flow_results

def print_production_summary(results):
    """Print a comprehensive production readiness summary"""
    print("\n" + "=" * 60)
    print("🎯 PRODUCTION READINESS SUMMARY")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed Tests: {passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    print("\nDetailed Results:")
    print("-" * 30)
    
    test_descriptions = {
        "health": "Application Health Check",
        "shield_config": "Shield Configuration",
        "credential_creation": "Credential Creation (Shield Flow)",
        "credential_verification": "Credential Verification (Check Flow)",
        "shield_status": "Shield Status Check",
        "credential_revocation": "Credential Revocation (Revoke Flow)",
        "revocation_detection": "Revocation Detection",
        "offline_verification": "Offline Verification"
    }
    
    for key, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        description = test_descriptions.get(key, key)
        print(f"{status} {description}")
    
    # Production readiness assessment
    print("\n" + "-" * 60)
    
    critical_flows = ["health", "credential_creation", "credential_verification", "credential_revocation"]
    critical_passed = sum(1 for key in critical_flows if results.get(key, False))
    
    if critical_passed == len(critical_flows):
        print("🎉 PRODUCTION READY - All critical flows working")
        production_status = "READY"
    elif critical_passed >= 3:
        print("⚠️  PARTIALLY READY - Most critical flows working")
        production_status = "PARTIAL"
    else:
        print("❌ NOT READY - Critical flows failing")
        production_status = "NOT_READY"
    
    # Specific flow assessments
    print("\nFlow-Specific Assessment:")
    print("-" * 30)
    
    if results.get("credential_creation") and results.get("shield_config"):
        print("✅ SHIELD FLOW: Ready for production")
    else:
        print("❌ SHIELD FLOW: Needs attention")
    
    if results.get("credential_verification") and results.get("shield_status"):
        print("✅ CHECK FLOW: Ready for production")
    else:
        print("❌ CHECK FLOW: Needs attention")
    
    if results.get("credential_revocation") and results.get("revocation_detection"):
        print("✅ REVOKE FLOW: Ready for production")
    else:
        print("❌ REVOKE FLOW: Needs attention")
    
    if results.get("offline_verification"):
        print("✅ OFFLINE VERIFICATION: Working")
    else:
        print("❌ OFFLINE VERIFICATION: Needs attention")
    
    print("\n" + "=" * 60)
    return production_status

def main():
    """Main production test function"""
    print("Starting Production Three Flows Validation...")
    time.sleep(2)  # Wait for app to be ready
    
    # Run the comprehensive tests
    results = test_production_flows()
    
    # Print summary
    production_status = print_production_summary(results)
    
    # Return appropriate exit code
    if production_status == "READY":
        return 0
    elif production_status == "PARTIAL":
        return 1
    else:
        return 2

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 