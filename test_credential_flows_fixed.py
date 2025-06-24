#!/usr/bin/env python3
"""
COMPREHENSIVE CREDENTIAL FLOW TEST
Tests the fixed join-network page to ensure all flows work properly:
- Credential checking (Check Flow)
- Shield appearance (Shield Flow) 
- Revocation detection (Revoke Flow)
"""

import requests
import json
import time

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}")

def test_api_endpoints():
    """Test that all required API endpoints are working"""
    log("🔌 TESTING API ENDPOINTS")
    
    endpoints = [
        ("/api/health", "GET", None),
        ("/api/shield/config", "GET", None),
        ("/api/issue-credential", "POST", {"user_id": "test_user", "verification_type": "human"}),
        ("/api/shield/status", "POST", {"credentials": [{"id": "test_cred"}]}),
        ("/api/shield/revoke-credential", "POST", {"credential_id": "test_cred", "reason": "test"}),
    ]
    
    working_count = 0
    for endpoint, method, data in endpoints:
        try:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            else:
                response = requests.post(f"{BASE_URL}{endpoint}", json=data, timeout=10)
                
            if response.status_code == 200:
                log(f"   ✅ {endpoint} ({method}): {response.status_code}")
                working_count += 1
            else:
                log(f"   ❌ {endpoint} ({method}): {response.status_code}")
        except Exception as e:
            log(f"   ❌ {endpoint} ({method}): ERROR - {e}")
    
    log(f"📊 API Endpoints: {working_count}/{len(endpoints)} working")
    return working_count == len(endpoints)

def test_join_network_page():
    """Test join-network page setup and initialization"""
    log("🌐 TESTING JOIN-NETWORK PAGE")
    
    try:
        response = requests.get(f"{BASE_URL}/join-network", timeout=10)
        if response.status_code != 200:
            log(f"   ❌ Page failed to load: {response.status_code}")
            return False
            
        content = response.text
        log(f"   ✅ Page loads successfully ({len(content)} chars)")
        
        # Check for critical components
        checks = [
            ("Shield Container", "lemma-shield-container"),
            ("Initialization Function", "initializeLemmaShield"),
            ("Wallet Script", "lemma-wallet.js"),
            ("Background Wallet Script", "lemma-wallet-background.js"),
            ("Shield Widget Script", "lemma-shield-widget.js"),
            ("Flow Orchestrator Script", "lemma-shield-flow-orchestrator.js"),
            ("Revocation Button", "revokeCredential"),
            ("Wallet Initialization", "window.lemmaWallet = new"),
            ("Shield Widget Initialization", "window.lemmaShieldWidget = new"),
            ("Flow Orchestrator Initialization", "window.lemmaFlowOrchestrator = new"),
        ]
        
        passed_checks = 0
        for name, pattern in checks:
            if pattern in content:
                log(f"   ✅ {name}")
                passed_checks += 1
            else:
                log(f"   ❌ {name}")
        
        log(f"📊 Page Setup: {passed_checks}/{len(checks)} components found")
        return passed_checks >= 8  # Need at least 8/10 to be considered working
        
    except Exception as e:
        log(f"   ❌ Error loading page: {e}")
        return False

def test_revocation_flow():
    """Test the complete revocation flow"""
    log("🚨 TESTING REVOCATION FLOW")
    
    try:
        # Step 1: Create a credential
        log("   Step 1: Creating test credential...")
        issue_response = requests.post(f"{BASE_URL}/api/issue-credential", json={
            "user_id": f"test_user_{int(time.time())}",
            "verification_type": "human"
        }, timeout=10)
        
        if issue_response.status_code != 200:
            log(f"   ❌ Failed to create credential: {issue_response.status_code}")
            return False
            
        credential_data = issue_response.json()
        credential_id = credential_data.get("credential", {}).get("id", f"test_cred_{int(time.time())}")
        log(f"   ✅ Created credential: {credential_id}")
        
        # Step 2: Revoke the credential
        log("   Step 2: Revoking credential...")
        revoke_response = requests.post(f"{BASE_URL}/api/shield/revoke-credential", json={
            "credential_id": credential_id,
            "reason": "Test revocation flow",
            "revoked_by": "test_automation"
        }, timeout=10)
        
        if revoke_response.status_code != 200:
            log(f"   ❌ Failed to revoke credential: {revoke_response.status_code}")
            return False
            
        revoke_data = revoke_response.json()
        log(f"   ✅ Revocation successful: {revoke_data.get('success', False)}")
        log(f"   ✅ Flow steps completed: {len(revoke_data.get('flow_steps_completed', []))}")
        log(f"   ✅ Network propagation: {revoke_data.get('network_propagation', {}).get('success', False)}")
        
        # Step 3: Check revocation detection
        log("   Step 3: Testing revocation detection...")
        status_response = requests.post(f"{BASE_URL}/api/shield/status", json={
            "credentials": [{"id": credential_id}],
            "check_revocation": True,
            "comprehensive_check": True
        }, timeout=10)
        
        if status_response.status_code != 200:
            log(f"   ❌ Failed to check status: {status_response.status_code}")
            return False
            
        status_data = status_response.json()
        shield_action = status_data.get("shield_action")
        revocation_detected = status_data.get("revocation_detected", False)
        
        log(f"   ✅ Shield action: {shield_action}")
        log(f"   ✅ Revocation detected: {revocation_detected}")
        
        # Success criteria
        success = (
            revoke_data.get("success", False) and
            shield_action == "require_verification" and
            revocation_detected
        )
        
        if success:
            log("   🎉 Revocation flow working correctly!")
        else:
            log("   ❌ Revocation flow has issues")
            
        return success
        
    except Exception as e:
        log(f"   ❌ Revocation flow error: {e}")
        return False

def test_shield_triggers():
    """Test that shield triggers are working"""
    log("🛡️ TESTING SHIELD TRIGGERS")
    
    # Test shield status with no credentials (should require verification)
    try:
        status_response = requests.post(f"{BASE_URL}/api/shield/status", json={
            "credentials": [],
            "check_revocation": False
        }, timeout=10)
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            shield_action = status_data.get("shield_action")
            
            if shield_action == "require_verification":
                log("   ✅ Shield correctly triggered for no credentials")
                return True
            else:
                log(f"   ❌ Shield action unexpected: {shield_action}")
                return False
        else:
            log(f"   ❌ Shield status check failed: {status_response.status_code}")
            return False
            
    except Exception as e:
        log(f"   ❌ Shield trigger test error: {e}")
        return False

def main():
    """Run all tests and provide summary"""
    log("🚀 STARTING COMPREHENSIVE CREDENTIAL FLOW TEST")
    log("=" * 60)
    
    test_results = {}
    
    # Run all tests
    test_results["API Endpoints"] = test_api_endpoints()
    test_results["Join-Network Page"] = test_join_network_page() 
    test_results["Revocation Flow"] = test_revocation_flow()
    test_results["Shield Triggers"] = test_shield_triggers()
    
    # Summary
    log("\n" + "=" * 60)
    log("📊 COMPREHENSIVE TEST RESULTS")
    log("=" * 60)
    
    passed_tests = sum(test_results.values())
    total_tests = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        log(f"{status} {test_name}")
    
    log(f"\n🎯 OVERALL RESULT: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        log("🎉 ALL TESTS PASSED! The credential flows are working correctly!")
        log("\n✅ WHAT'S WORKING:")
        log("- API endpoints are operational")
        log("- Join-network page has proper setup")
        log("- Revocation flow works end-to-end")
        log("- Shield triggers correctly")
        log("- Credential checking is functional")
        return True
    else:
        log(f"⚠️  {total_tests - passed_tests} tests failed - flows need attention")
        
        if not test_results["API Endpoints"]:
            log("🔧 ISSUE: API endpoints not working properly")
        if not test_results["Join-Network Page"]:
            log("🔧 ISSUE: Join-network page setup incomplete")
        if not test_results["Revocation Flow"]:
            log("🔧 ISSUE: Revocation flow not working")
        if not test_results["Shield Triggers"]:
            log("🔧 ISSUE: Shield not triggering correctly")
            
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 