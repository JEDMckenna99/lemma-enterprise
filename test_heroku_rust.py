#!/usr/bin/env python3
"""
Test script to verify the Rust engine is working on Heroku
"""

import requests
import json

def test_heroku_rust_engine():
    print("🧪 Testing Heroku Rust Engine Status")
    print("=" * 50)
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    # Test 1: Bot Shield Status
    print("1. Testing Bot Shield Status...")
    try:
        response = requests.get(f"{base_url}/api/shield/status")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            engine = data.get('engine', 'unknown')
            print(f"   Engine: {engine}")
            
            if engine in ['rust_engine', 'rust_ready']:
                print(f"   ✅ SUCCESS: Rust engine is active! (Status: {engine})")
                return True
            elif engine == 'python_fallback':
                print("   ❌ ISSUE: Still using Python fallback")
                return False
            else:
                print(f"   ⚠️  UNKNOWN: Engine type '{engine}'")
                return False
        else:
            print(f"   ❌ ERROR: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False

    # Test 2: Bot Shield POST with credentials
    print("\n2. Testing Bot Shield POST verification...")
    try:
        test_credentials = [{
            'id': 'test-rust-verification',
            'issuer': 'lemma-heroku-test',
            'subject': 'rust-engine-test'
        }]
        
        response = requests.post(
            f"{base_url}/api/shield/status",
            json={'credentials': test_credentials}
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            engine = data.get('engine', 'unknown')
            print(f"   Engine: {engine}")
            
            # Look for verification results
            valid_creds = data.get('valid_credentials', [])
            invalid_creds = data.get('invalid_credentials', [])
            
            print(f"   Valid credentials: {len(valid_creds)}")
            print(f"   Invalid credentials: {len(invalid_creds)}")
            
            if engine == 'rust_engine':
                print("   ✅ SUCCESS: Rust engine handled POST request!")
                return True
            else:
                print("   ❌ ISSUE: Not using Rust engine for verification")
                return False
        else:
            print(f"   ❌ ERROR: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_heroku_rust_engine()
    
    if success:
        print("\n🎉 HEROKU RUST ENGINE: OPERATIONAL!")
        print("   The Rust engine is successfully deployed and working on Heroku.")
    else:
        print("\n⚠️  HEROKU RUST ENGINE: NOT YET ACTIVE")
        print("   The deployment may still be in progress or needs troubleshooting.") 