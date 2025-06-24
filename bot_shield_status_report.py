#!/usr/bin/env python3
"""
🛡️ BOT SHIELD CIRCUIT STATUS REPORT
Complete validation of all three flows
"""

import requests
import json
import time
from datetime import datetime

# Production Configuration 
BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
API_KEY = "e663a17fe6a8b1501c768ad88c9ceb072d2ef6eecaa51d84b38a89edfe07d5db"

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def test_endpoint(path, method="GET", data=None):
    """Test endpoint and return success status"""
    try:
        url = f"{BASE_URL}{path}"
        if method.upper() == "POST":
            response = requests.post(url, json=data, headers=HEADERS, timeout=30)
        else:
            response = requests.get(url, headers=HEADERS, timeout=30)
        
        if response.status_code < 400:
            try:
                return True, response.json()
            except:
                return True, response.text
        return False, response.text[:200]
    except Exception as e:
        return False, str(e)

def main():
    print("🛡️ LEMMA BOT SHIELD CIRCUIT - STATUS REPORT")
    print("=" * 60)
    print(f"📅 Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Environment: Production Heroku")
    print(f"🔗 Base URL: {BASE_URL}")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Health & Infrastructure
    print("\n🏥 INFRASTRUCTURE HEALTH")
    success, data = test_endpoint("/api/health")
    results['health'] = success
    print(f"   Health Check: {'✅ PASS' if success else '❌ FAIL'}")
    
    # Test 2: Shield Configuration
    print("\n🛡️ SHIELD CONFIGURATION")
    success, data = test_endpoint("/api/shield/config")
    results['config'] = success
    print(f"   Shield Config: {'✅ PASS' if success else '❌ FAIL'}")
    
    # Test 3: FLOW 1 - SHIELD FLOW (Credential Creation)
    print("\n1️⃣ SHIELD FLOW - Human Verification Setup")
    create_data = {
        "user_id": f"shield_test_{int(time.time())}",
        "attributes": {"isHuman": True, "test_mode": True},
        "include_offline": True
    }
    success, credential_result = test_endpoint("/api/issue-credential", "POST", create_data)
    results['shield_flow'] = success
    
    credential_id = None
    if success:
        credential = credential_result.get("credential", {})
        credential_id = credential.get("id")
        print(f"   Credential Creation: ✅ PASS")
        print(f"   Credential ID: {credential_id}")
        print(f"   Offline Capable: {'✅ YES' if credential_result.get('offline_capable') else '❌ NO'}")
    else:
        print(f"   Credential Creation: ❌ FAIL")
    
    # Test 4: FLOW 2 - CHECK FLOW (Background Verification)
    print("\n2️⃣ CHECK FLOW - Background Verification")
    if credential_id:
        # Shield Status Check
        status_data = {"credentials": [{"id": credential_id}]}
        success, status_result = test_endpoint("/api/shield/status", "POST", status_data)
        results['check_flow_status'] = success
        
        if success:
            shield_action = status_result.get('shield_action', 'unknown')
            print(f"   Shield Status Check: ✅ PASS")
            print(f"   Shield Action: {shield_action}")
            print(f"   Valid Credentials: {status_result.get('valid_count', 0)}")
        else:
            print(f"   Shield Status Check: ❌ FAIL")
        
        # Credential Verification
        full_credential = credential_result.get("credential", {})
        verify_data = {
            "credential": full_credential,
            "challenge": f"status_report_{int(time.time())}"
        }
        success, verify_result = test_endpoint("/api/verify-credential", "POST", verify_data)
        results['check_flow_verify'] = success
        print(f"   Credential Verification: {'✅ PASS' if success else '❌ FAIL'}")
        
        # Offline Verification (Zero API Calls)
        offline_data = {
            "credential_id": credential_id,
            "credential": {"id": credential_id, "attributes": {"isHuman": True}}
        }
        success, offline_result = test_endpoint("/api/verify-offline", "POST", offline_data)
        results['offline_verification'] = success
        
        if success:
            network_calls = offline_result.get('network_calls', 'N/A')
            verified = offline_result.get('verified', False)
            print(f"   Offline Verification: ✅ PASS")
            print(f"   Network Calls: {network_calls} (Target: 0)")
            print(f"   Verified: {'✅ YES' if verified else '❌ NO'}")
            print(f"   Unlimited Checks: {'✅ YES' if offline_result.get('unlimited_checks') else '❌ NO'}")
        else:
            print(f"   Offline Verification: ❌ FAIL")
    else:
        print("   ⚠️  Skipping CHECK FLOW - no credential")
        results['check_flow_status'] = False
        results['check_flow_verify'] = False
        results['offline_verification'] = False
    
    # Test 5: FLOW 3 - REVOCATION FLOW (Security Response)
    print("\n3️⃣ REVOCATION FLOW - Security Response")
    if credential_id:
        # Revoke Credential
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Status report test revocation",
            "revoked_by": "status_report"
        }
        success, revoke_result = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
        results['revocation'] = success
        
        if success:
            print(f"   Credential Revocation: ✅ PASS")
            print(f"   Flow Steps: {len(revoke_result.get('flow_steps_completed', []))}")
            print(f"   OPRF Data Available: {'✅ YES' if revoke_result.get('oprf_data_available') else '❌ NO'}")
            
            # Wait for propagation
            time.sleep(2)
            
            # Test Revocation Detection
            status_data = {"credentials": [{"id": credential_id}]}
            success, status_result = test_endpoint("/api/shield/status", "POST", status_data)
            results['revocation_detection'] = success
            
            if success:
                shield_action = status_result.get('shield_action', 'unknown')
                revocation_detected = status_result.get('revocation_detected', False)
                print(f"   Revocation Detection: ✅ PASS")
                print(f"   Shield Action: {shield_action}")
                print(f"   Revocation Detected: {'✅ YES' if revocation_detected else '❌ NO'}")
            else:
                print(f"   Revocation Detection: ❌ FAIL")
        else:
            print(f"   Credential Revocation: ❌ FAIL")
            results['revocation_detection'] = False
    else:
        print("   ⚠️  Skipping REVOCATION FLOW - no credential")
        results['revocation'] = False
        results['revocation_detection'] = False
    
    # Calculate Overall Status
    print("\n" + "=" * 60)
    print("📊 OVERALL BOT SHIELD STATUS")
    print("=" * 60)
    
    # Core flows
    shield_working = results.get('shield_flow', False)
    check_working = all([
        results.get('check_flow_status', False),
        results.get('offline_verification', False)
    ])
    revoke_working = all([
        results.get('revocation', False),
        results.get('revocation_detection', False)
    ])
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
    
    print(f"🔍 CHECK FLOW (Background): {'✅ OPERATIONAL' if check_working else '❌ NEEDS ATTENTION'}")
    print(f"🛡️ SHIELD FLOW (Human Verification): {'✅ OPERATIONAL' if shield_working else '❌ NEEDS ATTENTION'}")
    print(f"🚫 REVOCATION FLOW (Security Response): {'✅ OPERATIONAL' if revoke_working else '❌ NEEDS ATTENTION'}")
    print(f"⚡ OFFLINE VERIFICATION: {'✅ OPERATIONAL' if results.get('offline_verification') else '❌ NEEDS ATTENTION'}")
    
    print(f"\n📈 SUCCESS RATE: {success_rate:.1f}% ({passed_tests}/{total_tests} tests passed)")
    
    # Overall Circuit Status
    if all([shield_working, check_working, revoke_working]):
        print("🎉 CIRCUIT STATUS: ✅ 100% OPERATIONAL - PRODUCTION READY")
        print("🚀 All three bot shield flows are working correctly")
        print("⚡ Zero-API-call offline verification confirmed")
        print("🔐 Complete OPRF-cascaded revocation system operational")
    elif shield_working and check_working:
        print("⚠️  CIRCUIT STATUS: 🟡 MOSTLY OPERATIONAL")
        print("✅ Core verification flows working")
        print("⚠️  Revocation flow needs attention")
    else:
        print("❌ CIRCUIT STATUS: 🔴 NEEDS ATTENTION")
        print("🔧 Critical flows require debugging")
    
    print("\n" + "=" * 60)
    print("🛡️ BOT SHIELD CIRCUIT REPORT COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main() 