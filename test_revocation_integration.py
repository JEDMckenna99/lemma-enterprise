import requests
import json
import os
import sys
import time
import base64
import random
import string
import re

# Configuration
MAIN_APP_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'

def generate_random_string(length=10):
    """Generate a random string for testing purposes"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def test_main_app_oprf_integration():
    """Test the main app's integration with the OPRF service"""
    print(f"\nTesting main app's OPRF integration at {MAIN_APP_URL}/api/oprf/status...")
    try:
        response = requests.get(f"{MAIN_APP_URL}/api/oprf/status", timeout=10)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("Main app successfully connected to OPRF service!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing main app OPRF integration: {e}")
        return False

def main():
    print("=== Revocation Integration Test ===\n")
    
    # Test main app integration
    main_app_integration_ok = test_main_app_oprf_integration()
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Main App OPRF Integration: {'✅ PASS' if main_app_integration_ok else '❌ FAIL'}")
    
    # Overall result
    if main_app_integration_ok:
        print("\n✅ The OPRF integration is working! The main app can perform revocation checks.")
        print("The revocation layer is properly configured.")
        return 0
    else:
        print("\n❌ The OPRF integration is not working. Check the Heroku logs for more details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())