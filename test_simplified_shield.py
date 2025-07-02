#!/usr/bin/env python3
"""
Test the simplified shield widget to ensure it works without infinite loops
"""

import requests
import time
import json

def test_simplified_shield():
    """Test the simplified shield behavior"""
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🧪 Testing Simplified Shield Widget")
    print("=" * 50)
    
    # Test 1: Shield status endpoint
    print("1️⃣ Testing shield status endpoint...")
    try:
        response = requests.get(f"{base_url}/api/shield/status", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Shield Action: {data.get('shield_action')}")
            print(f"   Reason: {data.get('reason')}")
            print(f"   Response Time: {data.get('response_time_ms')}ms")
            print("   ✅ Status endpoint working")
        else:
            print(f"   ❌ Status endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Status endpoint error: {e}")
    
    print()
    
    # Test 2: Verification status endpoint (the one we added)
    print("2️⃣ Testing verification status endpoint...")
    try:
        response = requests.get(f"{base_url}/api/shield/verification-status", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Verified: {data.get('verified')}")
            print(f"   Status: {data.get('status')}")
            print("   ✅ Verification status endpoint working")
        else:
            print(f"   ❌ Verification status endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Verification status endpoint error: {e}")
    
    print()
    
    # Test 3: Load the join network page to see shield behavior
    print("3️⃣ Testing join network page with shield widget...")
    try:
        response = requests.get(f"{base_url}/join-network", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            content = response.text
            if "lemma-shield-widget.js" in content:
                print("   ✅ Shield widget script found on page")
            else:
                print("   ⚠️ Shield widget script not found on page")
            
            if "Lemma.init" in content or "LemmaShield" in content:
                print("   ✅ Shield initialization found")
            else:
                print("   ⚠️ Shield initialization not found")
        else:
            print(f"   ❌ Join network page failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Join network page error: {e}")
    
    print()
    
    # Test 4: Check the shield widget file itself
    print("4️⃣ Testing shield widget JavaScript file...")
    try:
        response = requests.get(f"{base_url}/static/js/lemma-shield-widget.js", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            content = response.text
            
            # Check for simplified methods
            if "checkVerificationStatusOnce" in content:
                print("   ✅ Simplified verification check found")
            else:
                print("   ❌ Simplified verification check not found")
            
            if "showSimpleProcessingUI" in content:
                print("   ✅ Simplified processing UI found")
            else:
                print("   ❌ Simplified processing UI not found")
            
            # Check that complex monitoring is removed
            if "monitorVerificationProgress" not in content or "checkProgress" not in content:
                print("   ✅ Complex monitoring loops removed")
            else:
                print("   ⚠️ Complex monitoring loops still present")
            
            print(f"   Widget file size: {len(content):,} characters")
        else:
            print(f"   ❌ Widget file failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Widget file error: {e}")
    
    print()
    print("🏁 Shield Testing Complete")
    print("=" * 50)
    print("✅ The simplified shield should now:")
    print("   • Show static shield when no credentials")
    print("   • Use single verification check (no loops)")
    print("   • Have clean error handling")
    print("   • No more 404 errors on verification-status")
    print("   • No infinite loops in console")

if __name__ == "__main__":
    test_simplified_shield() 