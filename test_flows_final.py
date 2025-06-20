#!/usr/bin/env python3
"""
Final Three Flows Test - Fix credential verification format for 100% success
"""

import http.client
import json
import time
import sys
import datetime

def get_api_key():
    """Get the correct API key"""
    today = datetime.datetime.now().strftime('%Y%m%d')
    return f'dev_api_key_{today}'

def test_endpoint(path, method="GET", data=None):
    """Test an endpoint"""
    try:
        conn = http.client.HTTPConnection("localhost", 5000, timeout=15)
        
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
        
        print(f"[{time.strftime('%H:%M:%S')}] {method} {path} -> {status}")
        
        if status >= 400:
            print(f"  Error: {response_data[:150]}")
        
        return status, response_data
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] {method} {path} -> ERROR: {e}")
        return None, str(e)

def main():
    """Final comprehensive test"""
    print("🎯 FINAL THREE FLOWS VALIDATION")
    print("=" * 50)
    
    results = {}
    credential_data = None
    credential_id = None
    
    # Step 1: Health Check
    print("\n1️⃣ HEALTH CHECK")
    status, data = test_endpoint("/api/health")
    results['health'] = status == 200
    if not results['health']:
        print("❌ Health check failed - stopping")
        return
    print("✅ Health check passed")
    
    # Step 2: Shield Config  
    print("\n2️⃣ SHIELD CONFIGURATION")
    status, data = test_endpoint("/api/shield/config")
    results['shield_config'] = status == 200
    print("✅ Shield config passed" if results['shield_config'] else "❌ Shield config failed")
    
    # Step 3: Create Credential
    print("\n3️⃣ CREDENTIAL CREATION (SHIELD FLOW)")
    create_data = {
        "user_id": f"final_test_{int(time.time())}",
        "attributes": {"isHuman": True, "final_test": True},
        "include_offline": True
    }
    
    status, data = test_endpoint("/api/issue-credential", "POST", create_data)
    if status in [200, 201]:
        try:
            result = json.loads(data)
            credential_data = result.get("credential")
            credential_id = credential_data.get("id") if credential_data else None
            results['credential_creation'] = bool(credential_id)
            print(f"✅ Credential created: {credential_id}")
        except:
            results['credential_creation'] = False
            print("❌ Credential creation - parse failed")
    else:
        results['credential_creation'] = False
        print("❌ Credential creation failed")
    
    # Step 4: Credential Verification (CHECK FLOW) - FIXED FORMAT
    print("\n4️⃣ CREDENTIAL VERIFICATION (CHECK FLOW)")
    if credential_data:
        # Use the correct format - send the full credential object
        verify_data = {
            "credential": credential_data  # Send full credential, not just ID
        }
        
        status, data = test_endpoint("/api/verify-credential", "POST", verify_data)
        results['credential_verification'] = status in [200, 201]
        if results['credential_verification']:
            print("✅ Credential verification passed")
        else:
            print("❌ Credential verification failed")
    else:
        results['credential_verification'] = False
        print("❌ Credential verification skipped - no credential")
    
    # Step 5: Shield Status Check
    print("\n5️⃣ SHIELD STATUS (CHECK FLOW)")
    if credential_id:
        status_data = {"credentials": [{"id": credential_id}]}
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        results['shield_status'] = status == 200
        if results['shield_status']:
            try:
                result = json.loads(data)
                shield_action = result.get("shield_action", "unknown")
                print(f"✅ Shield status passed - Action: {shield_action}")
            except:
                print("✅ Shield status passed")
        else:
            print("❌ Shield status failed")
    else:
        results['shield_status'] = False
        print("❌ Shield status skipped")
    
    # Step 6: Offline Verification
    print("\n6️⃣ OFFLINE VERIFICATION")
    offline_data = {
        "credential_id": credential_id or "test",
        "credential": {"id": credential_id or "test", "attributes": {"isHuman": True}}
    }
    
    status, data = test_endpoint("/api/verify-offline", "POST", offline_data)
    results['offline_verification'] = status == 200
    if results['offline_verification']:
        try:
            result = json.loads(data)
            unlimited = result.get("unlimited_checks", False)
            print(f"✅ Offline verification passed - Unlimited: {unlimited}")
        except:
            print("✅ Offline verification passed")
    else:
        print("❌ Offline verification failed")
    
    # Step 7: Credential Revocation (REVOKE FLOW)
    print("\n7️⃣ CREDENTIAL REVOCATION (REVOKE FLOW)")
    if credential_id:
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Final test completion",
            "revoked_by": "final_test"
        }
        
        status, data = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
        results['credential_revocation'] = status in [200, 201]
        print("✅ Credential revocation passed" if results['credential_revocation'] else "❌ Credential revocation failed")
    else:
        results['credential_revocation'] = False
        print("❌ Credential revocation skipped")
    
    # Step 8: Revocation Detection
    print("\n8️⃣ REVOCATION DETECTION")
    if credential_id and results['credential_revocation']:
        time.sleep(1)  # Allow propagation
        
        status_data = {"credentials": [{"id": credential_id}]}
        status, data = test_endpoint("/api/shield/status", "POST", status_data)
        
        if status == 200:
            try:
                result = json.loads(data)
                shield_action = result.get("shield_action", "unknown")
                revoked_count = result.get("revoked_count", 0)
                
                results['revocation_detection'] = (shield_action == "require_verification" or revoked_count > 0)
                if results['revocation_detection']:
                    print(f"✅ Revocation detection passed - Action: {shield_action}, Revoked: {revoked_count}")
                else:
                    print(f"⚠️  Revocation detection partial - Action: {shield_action}")
            except:
                results['revocation_detection'] = False
                print("❌ Revocation detection failed - parse error")
        else:
            results['revocation_detection'] = False
            print("❌ Revocation detection failed")
    else:
        results['revocation_detection'] = False
        print("❌ Revocation detection skipped")
    
    # Final Summary
    print("\n" + "=" * 60)
    print("🎯 FINAL VALIDATION SUMMARY")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    success_rate = (passed_tests / total_tests) * 100
    
    print(f"Tests Passed: {passed_tests}/{total_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    print("\nFlow Results:")
    flow_map = {
        'health': '🏥 Health Check',
        'shield_config': '🛡️  Shield Configuration', 
        'credential_creation': '📝 Credential Creation (Shield Flow)',
        'credential_verification': '✅ Credential Verification (Check Flow)',
        'shield_status': '🔍 Shield Status (Check Flow)',
        'offline_verification': '🌐 Offline Verification',
        'credential_revocation': '🚫 Credential Revocation (Revoke Flow)',
        'revocation_detection': '🔎 Revocation Detection'
    }
    
    for key, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        description = flow_map.get(key, key)
        print(f"{status} {description}")
    
    # Flow Assessment
    print("\n" + "-" * 60)
    shield_ready = results.get('credential_creation', False) and results.get('shield_config', False)
    check_ready = results.get('credential_verification', False) and results.get('shield_status', False)
    revoke_ready = results.get('credential_revocation', False) and results.get('revocation_detection', False)
    
    print("THREE ESSENTIAL FLOWS STATUS:")
    print(f"✅ SHIELD FLOW: {'Ready' if shield_ready else 'Needs Attention'}")
    print(f"✅ CHECK FLOW: {'Ready' if check_ready else 'Needs Attention'}")  
    print(f"✅ REVOKE FLOW: {'Ready' if revoke_ready else 'Needs Attention'}")
    
    if success_rate >= 95:
        print("\n🎉 PRODUCTION READY - All flows working seamlessly!")
        return 0
    elif success_rate >= 85:
        print("\n⚠️  MOSTLY READY - Minor issues to address")
        return 1
    else:
        print("\n❌ NEEDS WORK - Major issues found")
        return 2

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 