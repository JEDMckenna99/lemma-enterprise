import requests
import json

def test_hardcoded_key():
    print("Testing hardcoded API key vulnerability...")
    url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issue-credential"
    headers = {"X-API-Key": "63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e"}
    data = {"user_id": "test_security"}
    
    response = requests.post(url, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("🚨 CRITICAL: Hardcoded API key STILL WORKS - VULNERABILITY ACTIVE!")
        return False
    elif response.status_code in [401, 403]:
        print("✅ SECURE: Hardcoded API key is blocked")
        return True
    else:
        print(f"⚠️  Unexpected response: {response.status_code}")
        return False

if __name__ == "__main__":
    test_hardcoded_key() 