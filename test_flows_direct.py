#!/usr/bin/env python3
"""
Direct API Flow Test - Handle redirects and test available endpoints
"""

import http.client
import json
import time
import sys

def test_endpoint_direct(path, method="GET", data=None):
    """Test an endpoint directly with redirect handling"""
    try:
        conn = http.client.HTTPConnection("localhost", 5000, timeout=10)
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key-123",
            "X-Forwarded-Proto": "http"  # Prevent HTTPS redirect
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
        
        if status == 301 or status == 302:
            print(f"  Redirect to: {response.headers.get('Location', 'Unknown')}")
        elif status >= 400:
            print(f"  Error: {response_data[:200]}")
        
        return status, response_data
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] {method} {path} -> ERROR: {e}")
        return None, str(e)

def check_available_endpoints():
    """Check what endpoints are actually available"""
    print("Checking Available Endpoints:")
    print("=" * 40)
    
    # List of endpoints to test
    endpoints = [
        "/health",
        "/api/health", 
        "/api/ping",
        "/api/fast-test",
        "/api/shield/config",
        "/api/shield/status",
        "/api/issue-credential",
        "/api/verify-credential",
        "/api/verify-offline",
        "/api/shield/revoke-credential",
        "/",
        "/debug-app"
    ]
    
    working_endpoints = []
    
    for endpoint in endpoints:
        status, data = test_endpoint_direct(endpoint)
        if status and status < 400:
            working_endpoints.append(endpoint)
            print(f"✅ {endpoint}")
        elif status == 301 or status == 302:
            working_endpoints.append(endpoint)
            print(f"↪️  {endpoint} (redirect)")
        else:
            print(f"❌ {endpoint}")
    
    print(f"\nWorking endpoints: {len(working_endpoints)}/{len(endpoints)}")
    return working_endpoints

def test_three_flows():
    """Test the three essential flows using working endpoints"""
    print("\n" + "=" * 50)
    print("TESTING THREE ESSENTIAL FLOWS")
    print("=" * 50)
    
    # Test 1: Find a working health endpoint
    print("\n=== TESTING APPLICATION HEALTH ===")
    health_endpoints = ["/health", "/api/health", "/api/ping"]
    
    health_working = False
    for endpoint in health_endpoints:
        status, data = test_endpoint_direct(endpoint)
        if status and status == 200:
            print(f"✅ Health check working: {endpoint}")
            health_working = True
            break
    
    if not health_working:
        print("❌ No health endpoints working")
        return
    
    # Test 2: Shield Flow - Try to issue a credential
    print("\n=== TESTING SHIELD FLOW ===")
    
    # Step 1: Try shield config
    status, data = test_endpoint_direct("/api/shield/config")
    if status == 200:
        print("✅ Shield config endpoint working")
    else:
        print(f"⚠️  Shield config returned: {status}")
    
    # Step 2: Try to create a credential
    credential_data = {
        "user_id": f"test_user_{int(time.time())}",
        "attributes": {"isHuman": True}
    }
    
    status, data = test_endpoint_direct("/api/issue-credential", "POST", credential_data)
    credential_id = None
    
    if status in [200, 201]:
        try:
            result = json.loads(data)
            credential_id = result.get("credential", {}).get("id")
            print(f"✅ Credential created: {credential_id}")
        except:
            print("✅ Credential endpoint responded (JSON parse failed)")
    else:
        print(f"❌ Credential creation failed: {status}")
    
    # Test 3: Check Flow - Try to verify status
    print("\n=== TESTING CHECK FLOW ===")
    
    if credential_id:
        # Test shield status
        status_data = {"credentials": [{"id": credential_id}]}
        status, data = test_endpoint_direct("/api/shield/status", "POST", status_data)
        
        if status == 200:
            print("✅ Shield status check working")
        else:
            print(f"⚠️  Shield status returned: {status}")
        
        # Test credential verification
        verify_data = {"credential_id": credential_id, "challenge": "test"}
        status, data = test_endpoint_direct("/api/verify-credential", "POST", verify_data)
        
        if status in [200, 201]:
            print("✅ Credential verification working")
        else:
            print(f"⚠️  Credential verification returned: {status}")
    else:
        print("❌ No credential ID to test check flow")
    
    # Test 4: Revoke Flow - Try to revoke
    print("\n=== TESTING REVOKE FLOW ===")
    
    if credential_id:
        revoke_data = {
            "credential_id": credential_id,
            "reason": "Flow test",
            "revoked_by": "test"
        }
        
        status, data = test_endpoint_direct("/api/shield/revoke-credential", "POST", revoke_data)
        
        if status in [200, 201]:
            print("✅ Credential revocation working")
            
            # Test that revocation is detected
            time.sleep(1)
            status_data = {"credentials": [{"id": credential_id}]}
            status, data = test_endpoint_direct("/api/shield/status", "POST", status_data)
            
            if status == 200:
                try:
                    result = json.loads(data)
                    shield_action = result.get("shield_action", "unknown")
                    print(f"✅ Post-revocation status: {shield_action}")
                except:
                    print("✅ Status check after revocation responded")
            
        else:
            print(f"❌ Credential revocation failed: {status}")
    else:
        print("❌ No credential ID to test revoke flow")
    
    # Test 5: Offline Verification
    print("\n=== TESTING OFFLINE VERIFICATION ===")
    
    offline_data = {
        "credential_id": "test_offline_credential",
        "credential": {"id": "test_offline", "attributes": {"isHuman": True}}
    }
    
    status, data = test_endpoint_direct("/api/verify-offline", "POST", offline_data)
    
    if status == 200:
        print("✅ Offline verification endpoint working")
    else:
        print(f"⚠️  Offline verification returned: {status}")

def main():
    """Main test function"""
    print("Lemma Three Flows Direct Test")
    print("Waiting for application to start...")
    time.sleep(3)
    
    # Check available endpoints first
    working_endpoints = check_available_endpoints()
    
    # Test the three flows
    test_three_flows()
    
    print("\n" + "=" * 50)
    print("DIRECT FLOW TEST COMPLETE")
    print("Check results above for each flow")
    print("=" * 50)

if __name__ == "__main__":
    main() 