#!/usr/bin/env python3
"""
Simple Alert System Test
"""

import requests

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
API_KEY = "63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e"

def test_endpoint(path):
    """Test an endpoint"""
    url = f"{BASE_URL}{path}"
    headers = {"X-API-Key": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"{path}: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Success: {data.get('success', 'unknown')}")
        else:
            print(f"  Error: {response.text[:100]}")
    except Exception as e:
        print(f"{path}: ERROR - {e}")

# Test endpoints
print("Testing Alert System Endpoints:")
test_endpoint("/api/sre/alerts/rules")
test_endpoint("/api/sre/alerts/current") 
test_endpoint("/api/sre/alerts/history")
test_endpoint("/api/sre/alerts/monitor-status")

print("\nTesting SRE Metrics:")
test_endpoint("/api/sre/metrics/errors")
test_endpoint("/api/sre/metrics/latency")
test_endpoint("/api/sre/metrics/bloom-filter")
test_endpoint("/api/sre/metrics/billing-jobs") 