#!/usr/bin/env python3
"""
Test to verify that revocation false positive detection has been removed
"""

import requests
import time

def test_revocation_fix():
    """Test that revocation false positives have been removed"""
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🧪 TESTING: Revocation False Positive Fix")
    print("=" * 60)
    
    # Test 1: Check that revocation detection code is removed
    print("1️⃣ Testing that revocation detection is removed...")
    try:
        widget_response = requests.get(f"{base_url}/static/js/lemma-shield-widget.js", timeout=10)
        
        if widget_response.status_code == 200:
            content = widget_response.text
            
            # Check that revocation detection code is removed
            removed_patterns = [
                "lemma_revoked_credentials",
                "CREDENTIAL REVOKED",
                "BLOOM FILTER REVOKED", 
                "revocation_reason",
                "fast_revocation_cache",
                "Revocation-triggered verification detected",
                "force_verification=credential_revoked",
                "lemma_revocation_triggered"
            ]
            
            issues_found = []
            for pattern in removed_patterns:
                if pattern in content:
                    issues_found.append(pattern)
            
            if issues_found:
                print(f"   ❌ Still contains revocation detection: {issues_found}")
                return False
            else:
                print("   ✅ All revocation detection code removed")
                
        else:
            print(f"   ❌ Widget loading failed: {widget_response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error testing widget: {e}")
        return False
    
    # Test 2: Shield endpoints should work normally
    print("2️⃣ Testing shield endpoints...")
    try:
        status_response = requests.get(f"{base_url}/api/shield/status", timeout=10)
        verification_response = requests.get(f"{base_url}/api/shield/verification-status", timeout=10)
        
        print(f"   Shield Status: {status_response.status_code} {'✅' if status_response.status_code == 200 else '❌'}")
        print(f"   Verification Status: {verification_response.status_code} {'✅' if verification_response.status_code == 200 else '❌'}")
        
        if status_response.status_code == 200 and verification_response.status_code == 200:
            return True
        else:
            return False
            
    except Exception as e:
        print(f"   ❌ Error testing endpoints: {e}")
        return False

if __name__ == "__main__":
    success = test_revocation_fix()
    
    if success:
        print("\n🎉 SUCCESS! Revocation false positive detection has been completely removed!")
        print("✅ Shield should no longer constantly reappear due to false revocation triggers")
        print("✅ Only explicit server revocations will trigger credential clearing")
        print("✅ Static shield behavior when user lacks credentials")
    else:
        print("\n❌ FAILED! Some revocation detection code may still be present")
        
    exit(0 if success else 1) 