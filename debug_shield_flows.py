#!/usr/bin/env python3
"""
Debug Bot Shield Flows - Step by step analysis
"""

import requests
import json
import time

# Production Configuration 
BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
API_KEY = "e663a17fe6a8b1501c768ad88c9ceb072d2ef6eecaa51d84b38a89edfe07d5db"

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def test_endpoint(path, method="GET", data=None):
    """Test endpoint with detailed debugging"""
    url = f"{BASE_URL}{path}"
    print(f"\n🔍 Testing: {method} {path}")
    
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=data, headers=HEADERS, timeout=30)
        else:
            response = requests.get(url, headers=HEADERS, timeout=30)
            
        print(f"   Status: {response.status_code}")
        print(f"   Response size: {len(response.text)} chars")
        
        if response.status_code >= 400:
            print(f"   ❌ Error: {response.text[:300]}")
            return False, None
        
        try:
            result = response.json()
            print(f"   ✅ Success: {list(result.keys()) if isinstance(result, dict) else 'Not dict'}")
            return True, result
        except:
            print(f"   ✅ Success: Non-JSON response")
            return True, response.text
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False, None

def main():
    print("🛡️ DEBUG: Bot Shield Flows Analysis")
    print("=" * 50)
    
    # Step 1: Basic Health Check
    print("\n1️⃣ HEALTH CHECK")
    success, data = test_endpoint("/api/health")
    if not success:
        print("❌ Health check failed - stopping")
        return
        
    # Step 2: Shield Configuration
    print("\n2️⃣ SHIELD CONFIGURATION")
    success, config = test_endpoint("/api/shield/config")
    if success:
        print(f"   Config type: {config.get('type', 'unknown') if isinstance(config, dict) else 'N/A'}")
    
    # Step 3: Create Credential (Shield Flow)
    print("\n3️⃣ CREDENTIAL CREATION (Shield Flow)")
    create_data = {
        "user_id": f"debug_test_{int(time.time())}",
        "attributes": {"isHuman": True, "test_mode": True},
        "include_offline": True
    }
    success, credential_result = test_endpoint("/api/issue-credential", "POST", create_data)
    
    credential_id = None
    if success and isinstance(credential_result, dict):
        credential = credential_result.get("credential", {})
        credential_id = credential.get("id")
        print(f"   Credential ID: {credential_id}")
        print(f"   Credential keys: {list(credential.keys()) if isinstance(credential, dict) else 'N/A'}")
    
    # Step 4: Shield Status Check (Check Flow)
    print("\n4️⃣ SHIELD STATUS CHECK (Check Flow)")
    if credential_id:
        status_data = {"credentials": [{"id": credential_id}]}
        success, status_result = test_endpoint("/api/shield/status", "POST", status_data)
        if success and isinstance(status_result, dict):
            print(f"   Shield action: {status_result.get('shield_action', 'unknown')}")
            print(f"   Revoked count: {status_result.get('revoked_count', 0)}")
    else:
        print("   ⚠️  Skipping - no credential ID")
    
    # Step 5: Credential Verification
    print("\n5️⃣ CREDENTIAL VERIFICATION")
    if credential_id:
        # Use the full credential structure from the creation response
        full_credential = credential_result.get("credential", {})
        verify_data = {
            "credential": full_credential,
            "challenge": f"debug_challenge_{int(time.time())}"
        }
        success, verify_result = test_endpoint("/api/verify-credential", "POST", verify_data)
        if success and isinstance(verify_result, dict):
            print(f"   Verified: {verify_result.get('verified', False)}")
        else:
            print("   ⚠️  Using simplified verification format...")
            # Try alternative format
            verify_data_alt = {
                "credential_id": credential_id,
                "challenge": f"debug_challenge_alt_{int(time.time())}"
            }
            success, verify_result = test_endpoint("/api/verify-credential", "POST", verify_data_alt)
            if success and isinstance(verify_result, dict):
                print(f"   Verified (alt): {verify_result.get('verified', False)}")
    else:
        print("   ⚠️  Skipping - no credential ID")
    
    # Step 6: Offline Verification
    print("\n6️⃣ OFFLINE VERIFICATION")
    if credential_id:
        offline_data = {
            "credential_id": credential_id,
            "credential": {"id": credential_id, "attributes": {"isHuman": True}}
        }
        success, offline_result = test_endpoint("/api/verify-offline", "POST", offline_data)
        if success and isinstance(offline_result, dict):
            print(f"   Offline verified: {offline_result.get('verified', False)}")
            print(f"   Network calls: {offline_result.get('network_calls', 'N/A')}")
    else:
        print("   ⚠️  Skipping - no credential ID")
    
    # Step 7: Revocation (Revoke Flow)
    print("\n7️⃣ CREDENTIAL REVOCATION (Revoke Flow)")
    if credential_id:
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Debug test revocation",
            "revoked_by": "debug_test"
        }
        success, revoke_result = test_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
        if success:
            print("   ✅ Revocation successful")
            
            # Test revocation detection
            print("\n8️⃣ REVOCATION DETECTION")
            time.sleep(2)  # Allow propagation
            
            status_data = {"credentials": [{"id": credential_id}]}
            success, status_result = test_endpoint("/api/shield/status", "POST", status_data)
            if success and isinstance(status_result, dict):
                shield_action = status_result.get('shield_action', 'unknown')
                print(f"   Post-revocation action: {shield_action}")
                if shield_action == "require_verification":
                    print("   ✅ Revocation properly detected")
                else:
                    print("   ⚠️  Revocation may not be detected yet")
    else:
        print("   ⚠️  Skipping - no credential ID")
    
    print("\n" + "=" * 50)
    print("🎯 DEBUG ANALYSIS COMPLETE")
    print("Check the detailed output above for issues")

if __name__ == "__main__":
    main() 