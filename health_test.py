#!/usr/bin/env python3
"""Simple health test"""

import requests
import time

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

print("🏥 HEALTH CHECK")
print("=" * 30)

endpoints = [
    "/api/health",
    "/api/ping", 
    "/",
]

for endpoint in endpoints:
    try:
        print(f"Testing {endpoint}... ", end="")
        start = time.time()
        response = requests.get(BASE_URL + endpoint, timeout=10)
        elapsed = time.time() - start
        print(f"✅ {response.status_code} ({elapsed:.2f}s)")
        break  # If one works, app is running
    except Exception as e:
        print(f"❌ {str(e)}")

print("=" * 30) 