import requests
import json
import os
import sys

# Configuration
OPRF_SERVICE_URL = os.environ.get('OPRF_SERVICE_INTERNAL', 'https://lemma-oprf-service.herokuapp.com')
MAIN_APP_URL = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'

def test_oprf_status():
    """Test the OPRF service status endpoint"""
    print(f"Testing OPRF service status at {OPRF_SERVICE_URL}/status...")
    try:
        response = requests.get(f"{OPRF_SERVICE_URL}/status", timeout=10)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("OPRF service is running!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error connecting to OPRF service: {e}")
        return False

def test_oprf_evaluate():
    """Test the OPRF evaluation endpoint with a sample input"""
    print(f"\nTesting OPRF evaluation at {OPRF_SERVICE_URL}/evaluate...")
    try:
        # Create a sample blinded element (this is just for testing)
        sample_data = {
            "blinded_element": "X" + "1" * 64,
            "key_id": "test"
        }
        
        response = requests.post(
            f"{OPRF_SERVICE_URL}/evaluate", 
            json=sample_data,
            timeout=10
        )
        
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("OPRF evaluation successful!")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Error testing OPRF evaluation: {e}")
        return False

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
    print("=== OPRF Service and Integration Test ===\n")
    
    # Test OPRF service status
    oprf_status_ok = test_oprf_status()
    
    # Test OPRF evaluation
    oprf_eval_ok = test_oprf_evaluate()
    
    # Test main app integration
    main_app_integration_ok = test_main_app_oprf_integration()
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"OPRF Service Status: {'✅ PASS' if oprf_status_ok else '❌ FAIL'}")
    print(f"OPRF Evaluation: {'✅ PASS' if oprf_eval_ok else '❌ FAIL'}")
    print(f"Main App Integration: {'✅ PASS' if main_app_integration_ok else '❌ FAIL'}")
    
    # Overall result
    if oprf_status_ok and oprf_eval_ok and main_app_integration_ok:
        print("\n✅ All tests passed! The revocation layer is working properly.")
        return 0
    else:
        print("\n❌ Some tests failed. The revocation layer may not be fully functional.")
        return 1

if __name__ == "__main__":
    sys.exit(main())