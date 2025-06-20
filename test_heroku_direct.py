#!/usr/bin/env python3
"""Test Heroku app directly"""

import requests
import time

def test_heroku():
    print("🧪 Testing Heroku App Directly")
    print("=" * 40)
    
    heroku_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    try:
        print(f"Testing: {heroku_url}/")
        start = time.time()
        r = requests.get(f"{heroku_url}/", timeout=30)
        elapsed = (time.time() - start) * 1000
        print(f"✅ Status: {r.status_code}")
        print(f"⚡ Time: {elapsed:.0f}ms")
        print(f"📄 Content length: {len(r.text)} chars")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    try:
        print(f"\nTesting: {heroku_url}/api/health")
        start = time.time()
        r = requests.get(f"{heroku_url}/api/health", timeout=30)
        elapsed = (time.time() - start) * 1000
        print(f"✅ Status: {r.status_code}")
        print(f"⚡ Time: {elapsed:.0f}ms")
        print(f"📄 Response: {r.text[:100]}...")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_heroku() 