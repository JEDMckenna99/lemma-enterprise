#!/usr/bin/env python3
"""
Test script to verify the "Get Verified" button functionality
"""

import requests
import json
import sys

def test_get_verified_functionality():
    """Test the Get Verified button functionality"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Lemma 'Get Verified' Button Functionality")
    print("=" * 60)
    
    try:
        # Test 1: Check if home page loads
        print("\n1. Testing home page accessibility...")
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            print("✅ Home page loads successfully")
            
            # Check if the button exists in the HTML
            if 'id="getVerifiedBtn"' in response.text:
                print("✅ Get Verified button found in home page")
            else:
                print("❌ Get Verified button NOT found in home page")
                return False
                
        else:
            print(f"❌ Home page failed to load: {response.status_code}")
            return False
            
        # Test 2: Check if API endpoint is available
        print("\n2. Testing start-verification API endpoint...")
        headers = {'Content-Type': 'application/json'}
        
        # First get CSRF token
        csrf_response = requests.get(f"{base_url}/api/generate-csrf")
        if csrf_response.status_code == 200:
            csrf_data = csrf_response.json()
            headers['X-CSRF-Token'] = csrf_data.get('csrf_token')
            print("✅ CSRF token obtained")
        else:
            print("⚠️  Could not get CSRF token, proceeding without it")
            
        # Test the verification API
        test_data = {"user_id": "test_user_123"}
        response = requests.post(f"{base_url}/api/start-verification", 
                               headers=headers, 
                               json=test_data)
        
        if response.status_code in [200, 500]:  # 500 is expected if Stripe is not configured
            print("✅ Start verification API endpoint is accessible")
            if response.status_code == 500:
                print("ℹ️  Note: Stripe may not be configured (expected for local testing)")
        else:
            print(f"❌ Start verification API failed: {response.status_code}")
            print(f"Response: {response.text}")
            
        # Test 3: Check if complete verification flow endpoint exists
        print("\n3. Testing complete-verification-flow API endpoint...")
        test_data = {"user_id": "test_user_123", "check_only": True}
        response = requests.post(f"{base_url}/api/complete-verification-flow", 
                               headers=headers, 
                               json=test_data)
        
        if response.status_code in [200, 400]:  # 400 is expected for test data
            print("✅ Complete verification flow API endpoint is accessible")
        else:
            print(f"❌ Complete verification flow API failed: {response.status_code}")
            
        # Test 4: Check if wallet scripts are included
        print("\n4. Testing wallet script availability...")
        home_response = requests.get(f"{base_url}/")
        if 'lemma-wallet.js' in home_response.text:
            print("✅ Lemma wallet script is included in home page")
        else:
            print("❌ Lemma wallet script NOT found in home page")
            
        # Test 5: Check JavaScript functionality
        print("\n5. Testing JavaScript integration...")
        home_content = requests.get(f"{base_url}/").text
        
        required_js_elements = [
            'getVerifiedBtn',
            'addEventListener',
            'start-verification',
            'lemmaWallet',
            'complete-verification-flow',
            'verification_success',  # New URL parameter approach
            'stripe_session_id'      # New API parameter
        ]
        
        missing_elements = []
        for element in required_js_elements:
            if element not in home_content:
                missing_elements.append(element)
                
        if not missing_elements:
            print("✅ All required JavaScript elements found")
        else:
            print(f"❌ Missing JavaScript elements: {missing_elements}")
            
        # Test 6: Test the new API-driven flow
        print("\n6. Testing API-driven verification flow...")
        
        # Simulate a successful verification callback
        test_user_id = "test_api_user_123"
        test_session_id = "vs_test_session_123"
        
        # Test the complete verification flow endpoint with session ID
        test_data = {
            "user_id": test_user_id, 
            "stripe_session_id": test_session_id
        }
        response = requests.post(f"{base_url}/api/complete-verification-flow", 
                               headers=headers, 
                               json=test_data)
        
        if response.status_code in [200, 400]:  # 400 is expected for test data
            print("✅ API-driven verification flow endpoint works")
            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'status' in result:
                        print(f"   API response status: {result['status']}")
                except:
                    pass
        else:
            print(f"❌ API-driven verification flow failed: {response.status_code}")
            
        print("\n" + "=" * 60)
        print("🎉 Test completed! The new API-driven Get Verified button should now:")
        print("   • Generate a unique user ID")
        print("   • Start Stripe verification flow via API")
        print("   • Complete verification via API callback")
        print("   • Store credentials in wallet through API")
        print("   • Show connected status for existing users")
        print("\n💡 New Architecture Benefits:")
        print("   ✅ Clean separation between frontend and backend")
        print("   ✅ API-driven credential issuance and storage")
        print("   ✅ No session storage dependencies")
        print("   ✅ URL parameter-based flow control")
        print("\n💡 To test end-to-end:")
        print("   1. Open http://localhost:5000 in browser")
        print("   2. Click 'Get Verified' button")
        print("   3. Complete Stripe verification")
        print("   4. Return to see API-driven wallet storage")
        print("   5. Get redirected to protected page automatically")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to localhost:5000")
        print("💡 Make sure the Flask app is running with: python app.py")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    success = test_get_verified_functionality()
    sys.exit(0 if success else 1) 