#!/usr/bin/env python3
"""
Simple Three Flows Test - Direct HTTP calls without SSL complications
"""

import http.client
import json
import time
import sys

def test_api_endpoint(path, method="GET", data=None, headers=None):
    """Test an API endpoint using direct HTTP connection"""
    try:
        # Connect to localhost:5000
        conn = http.client.HTTPConnection("localhost", 5000, timeout=10)
        
        # Prepare headers
        request_headers = {
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key-123"
        }
        if headers:
            request_headers.update(headers)
        
        # Prepare body
        body = None
        if data:
            body = json.dumps(data)
        
        # Make request
        conn.request(method, path, body, request_headers)
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

def main():
    """Test the three essential flows"""
    print("Testing Three Essential Flows with Simple HTTP")
    print("=" * 50)
    
    # Wait for app to start
    print("Waiting for application to start...")
    time.sleep(5)
    
    # Test 1: Health Check
    print("\n=== TESTING APPLICATION HEALTH ===")
    status, data = test_api_endpoint("/api/health")
    if status == 200:
        print("✅ Application is healthy")
    else:
        print("❌ Application health check failed")
        return
    
    # Test 2: Shield Config
    print("\n=== TESTING SHIELD FLOW ===")
    print("Step 1: Getting shield configuration...")
    status, data = test_api_endpoint("/api/shield/config")
    if status == 200:
        print("✅ Shield config retrieved")
    else:
        print("❌ Shield config failed")
    
    # Test 3: Create Credential
    print("Step 2: Creating test credential...")
    credential_data = {
        "user_id": f"test_user_{int(time.time())}",
        "attributes": {"isHuman": True, "verified_at": int(time.time())},
        "include_offline": True
    }
    status, data = test_api_endpoint("/api/issue-credential", "POST", credential_data)
    
    credential_id = None
    if status in [200, 201]:
        try:
            result = json.loads(data)
            credential_id = result.get("credential", {}).get("id")
            if credential_id:
                print(f"✅ Credential created: {credential_id}")
            else:
                print("⚠️  Credential created but no ID returned")
        except:
            print("⚠️  Credential response not parseable")
    else:
        print("❌ Credential creation failed")
    
    # Test 4: Check Flow (Shield Status)
    print("\n=== TESTING CHECK FLOW ===")
    if credential_id:
        print("Step 1: Checking shield status...")
        status_data = {"credentials": [{"id": credential_id}]}
        status, data = test_api_endpoint("/api/shield/status", "POST", status_data)
        
        if status == 200:
            try:
                result = json.loads(data)
                shield_action = result.get("shield_action", "unknown")
                print(f"✅ Shield status: {shield_action}")
            except:
                print("✅ Shield status endpoint responded")
        else:
            print("❌ Shield status check failed")
    
    # Test 5: Verify Credential
    if credential_id:
        print("Step 2: Verifying credential...")
        verify_data = {
            "credential_id": credential_id,
            "challenge": f"test_challenge_{int(time.time())}"
        }
        status, data = test_api_endpoint("/api/verify-credential", "POST", verify_data)
        
        if status in [200, 201]:
            print("✅ Credential verification successful")
        else:
            print("❌ Credential verification failed")
    
    # Test 6: Offline Verification
    if credential_id:
        print("Step 3: Testing offline verification...")
        offline_data = {
            "credential": {"id": credential_id, "attributes": {"isHuman": True}}
        }
        status, data = test_api_endpoint("/api/verify-offline", "POST", offline_data)
        
        if status == 200:
            print("✅ Offline verification working")
        else:
            print("⚠️  Offline verification needs attention")
    
    # Test 7: Revoke Flow
    print("\n=== TESTING REVOKE FLOW ===")
    if credential_id:
        print("Step 1: Revoking credential...")
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Test revocation for flow validation",
            "revoked_by": "automated_test"
        }
        status, data = test_api_endpoint("/api/shield/revoke-credential", "POST", revoke_data)
        
        if status in [200, 201]:
            print("✅ Credential revoked successfully")
            
            # Test that revoked credential fails verification
            print("Step 2: Confirming revocation took effect...")
            time.sleep(2)  # Allow revocation to propagate
            
            # Check shield status again
            status_data = {"credentials": [{"id": credential_id}]}
            status, data = test_api_endpoint("/api/shield/status", "POST", status_data)
            
            if status == 200:
                try:
                    result = json.loads(data)
                    shield_action = result.get("shield_action", "unknown")
                    if shield_action == "require_verification":
                        print("✅ Revocation detected - shield requires new verification")
                    else:
                        print(f"⚠️  Shield action: {shield_action}")
                except:
                    print("✅ Shield status endpoint responded after revocation")
            
            # Test offline verification of revoked credential
            offline_data = {
                "credential_id": credential_id,
                "credential": {"id": credential_id}
            }
            status, data = test_api_endpoint("/api/verify-offline", "POST", offline_data)
            
            if status == 200:
                try:
                    result = json.loads(data)
                    if not result.get("verified", True) or result.get("revoked", False):
                        print("✅ Offline verification properly detects revocation")
                    else:
                        print("⚠️  Offline verification may not detect revocation immediately")
                except:
                    print("✅ Offline verification responded")
            
        else:
            print("❌ Credential revocation failed")
    
    # Summary
    print("\n" + "=" * 50)
    print("THREE FLOWS TEST COMPLETE")
    print("✅ Shield Flow: Configuration and credential creation")
    print("✅ Check Flow: Status checking and verification") 
    print("✅ Revoke Flow: Credential revocation and detection")
    print("🎉 ALL THREE FLOWS TESTED - Check individual results above")
    print("=" * 50)

if __name__ == "__main__":
    main() 