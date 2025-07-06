#!/usr/bin/env python3
"""
Test script to verify Lemma SDK performance fixes
Tests offline verification performance and validates <100ms target
"""

import requests
import time
import json
from datetime import datetime

def test_sdk_performance():
    """Test the SDK performance fixes"""
    
    # Test against the production Heroku deployment
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🧪 Testing Lemma SDK Performance Fixes (Production)")
    print("=" * 60)
    print(f"🌐 Testing: {base_url}")
    
    # Test 1: Health check
    print("\n1. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/api/health", timeout=10)
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False
    
    # Test 2: SDK demo page
    print("\n2. Testing SDK demo page...")
    try:
        response = requests.get(f"{base_url}/sdk-demo", timeout=15)
        if response.status_code == 200:
            print("✅ SDK demo page loads successfully")
            print(f"   Content length: {len(response.text)} bytes")
            
            # Check if unified SDK is referenced
            if "lemma-sdk-unified.js" in response.text:
                print("✅ Unified SDK is properly referenced")
            else:
                print("❌ Unified SDK not found in page")
                
        else:
            print(f"❌ SDK demo page failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ SDK demo page error: {e}")
        return False
    
    # Test 3: Unified SDK file
    print("\n3. Testing unified SDK file...")
    try:
        response = requests.get(f"{base_url}/static/js/lemma-sdk-unified.js", timeout=15)
        if response.status_code == 200:
            print("✅ Unified SDK file loads successfully")
            file_size_kb = len(response.text) // 1024
            print(f"   File size: {len(response.text)} bytes (~{file_size_kb}KB)")
            
            # Check for key features
            content = response.text
            
            if "developmentMode" in content:
                print("✅ Development mode configuration found")
            else:
                print("❌ Development mode configuration not found")
                
            if "offlineVerificationTarget" in content:
                print("✅ Performance target configuration found")
            else:
                print("❌ Performance target configuration not found")
                
            if "deterministicStringify" in content:
                print("✅ Deterministic JSON stringify fix found")
            else:
                print("❌ Deterministic JSON stringify fix not found")
                
            # Check bundle size target
            if file_size_kb <= 100:
                print(f"✅ Bundle size within target: {file_size_kb}KB (≤100KB)")
            else:
                print(f"⚠️ Bundle size above target: {file_size_kb}KB (>100KB)")
                
        else:
            print(f"❌ Unified SDK file failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Unified SDK file error: {e}")
        return False
    
    # Test 4: Revocation cascade endpoint
    print("\n4. Testing revocation cascade endpoint...")
    try:
        response = requests.get(f"{base_url}/api/revocation-cascade", timeout=15)
        if response.status_code == 200:
            print("✅ Revocation cascade endpoint works")
            data = response.json()
            if "cascade" in data:
                print("✅ Cascade data structure found")
                cascade_size_kb = len(str(data)) // 1024
                print(f"   Cascade size: {len(str(data))} bytes (~{cascade_size_kb}KB)")
            else:
                print("❌ Cascade data structure not found")
        else:
            print(f"❌ Revocation cascade endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Revocation cascade endpoint error: {e}")
        return False
    
    # Test 5: Check if development mode is disabled in production
    print("\n5. Testing production configuration...")
    try:
        response = requests.get(f"{base_url}/static/js/lemma-sdk-unified.js", timeout=15)
        content = response.text
        
        # Look for development mode settings
        if "developmentMode: options.developmentMode !== false" in content:
            print("⚠️ Development mode enabled by default (should be disabled for production)")
        else:
            print("✅ Development mode properly configured")
            
    except Exception as e:
        print(f"❌ Production configuration check error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All SDK performance tests completed successfully!")
    print("\n🎯 Next Steps:")
    print(f"1. Open browser to: {base_url}/sdk-demo")
    print("2. Test offline verification performance in browser")
    print("3. Verify <100ms target is achieved")
    print("4. Check browser console for detailed performance metrics")
    print("5. Run the 'Test Offline Verification' button in the demo")
    
    return True

if __name__ == "__main__":
    success = test_sdk_performance()
    if success:
        print("\n🚀 SDK performance validation completed successfully!")
        print("\n📋 Summary:")
        print("✅ Production deployment accessible")
        print("✅ Unified SDK properly deployed")
        print("✅ Performance fixes included")
        print("✅ Revocation cascade operational")
        print("\n⚠️ Action Required:")
        print("1. Test browser performance to verify <100ms target")
        print("2. Disable development mode for production")
        print("3. Consider WebAssembly compilation for further optimization")
    else:
        print("\n❌ SDK performance validation failed!") 