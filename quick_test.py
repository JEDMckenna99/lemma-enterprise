#!/usr/bin/env python3
"""Quick test of key Day-1 pages"""

import requests

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
TIMEOUT = 5

pages = [
    ("/", "Homepage"),
    ("/landing", "Landing Page"),
    ("/docs", "Documentation"),
    ("/playground", "API Playground"),
    ("/pricing", "Pricing Page"),
    ("/status", "Status Page"),
]

print("🚀 QUICK TEST - KEY DAY-1 PAGES")
print("=" * 50)

for path, name in pages:
    try:
        url = BASE_URL + path
        response = requests.get(url, timeout=TIMEOUT)
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{name:.<30} {status} {response.status_code}")
    except Exception as e:
        print(f"{name:.<30} 💥 ERROR: {str(e)}")

print("=" * 50) 