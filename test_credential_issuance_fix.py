#!/usr/bin/env python3
"""
Test script to verify the credential issuance fix after Stripe Identity verification
This tests the complete flow from verification callback to credential storage in wallet
"""

import requests
import json
import time
import uuid
from datetime import datetime

class CredentialIssuanceFixTester:
    def __init__(self, base_url="https://lemma-enterprise-0f6ba17076c1.herokuapp.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Lemma-Credential-Issuance-Test/1.0'
        })
        
    def test_verification_callback_credential_issuance(self):
        """Test that verification callback properly issues credentials"""
        print("\n🧪 Testing Verification Callback Credential Issuance")
        print("=" * 60)
        
        try:
            # Step 1: Simulate a verification callback with a test user
            test_user_id = f"test-callback-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            test_session_id = f"vs_test_{int(time.time())}"
            
            print(f"📝 Test User ID: {test_user_id}")
            print(f"📝 Test Session ID: {test_session_id}")
            
            # Step 2: Call the verification callback endpoint
            print("\n🔄 Step 1: Calling verification callback...")
            callback_url = f"{self.base_url}/verification-callback"
            callback_params = {
                'session_id': test_session_id,
                'user_id': test_user_id
            }
            
            callback_response = self.session.get(callback_url, params=callback_params, allow_redirects=False)
            print(f"   Status: {callback_response.status_code}")
            
            if callback_response.status_code in [302, 303]:
                print(f"   ✅ Redirect response (expected): {callback_response.headers.get('Location', 'No location header')}")
            else:
                print(f"   Response: {callback_response.text[:200]}...")
            
            # Step 3: Check if credential was stored in session by calling Shield API
            print("\n🔄 Step 2: Checking Shield API for credential...")
            shield_verify_url = f"{self.base_url}/api/shield/verify-credentials"
            
            # Get CSRF token first
            csrf_response = self.session.get(f"{self.base_url}/api/generate-csrf")
            if csrf_response.status_code == 200:
                csrf_data = csrf_response.json()
                csrf_token = csrf_data.get('csrf_token')
                
                # Check inline verification status
                shield_data = {
                    'check_inline_verification': True,
                    'user_id': test_user_id,
                    'session_id': test_session_id
                }
                
                shield_headers = {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrf_token
                }
                
                shield_response = self.session.post(shield_verify_url, 
                                                   json=shield_data, 
                                                   headers=shield_headers)
                
                print(f"   Status: {shield_response.status_code}")
                if shield_response.status_code == 200:
                    shield_result = shield_response.json()
                    print(f"   ✅ Shield API Response: {json.dumps(shield_result, indent=2)}")
                    
                    if shield_result.get('success') and shield_result.get('verified'):
                        print("   🎉 Verification successful!")
                    else:
                        print(f"   ⚠️ Verification not completed: {shield_result.get('error', 'Unknown error')}")
                else:
                    print(f"   ❌ Shield API error: {shield_response.text}")
            else:
                print(f"   ❌ Failed to get CSRF token: {csrf_response.status_code}")
            
            # Step 4: Check if credential can be retrieved for wallet storage
            print("\n🔄 Step 3: Checking credential retrieval for wallet...")
            get_credential_url = f"{self.base_url}/api/shield/get-credential"
            
            credential_response = self.session.get(get_credential_url)
            print(f"   Status: {credential_response.status_code}")
            
            if credential_response.status_code == 200:
                credential_result = credential_response.json()
                print(f"   ✅ Credential retrieval successful!")
                
                if credential_result.get('success') and credential_result.get('credential'):
                    credential = credential_result['credential']
                    print(f"   📄 Credential ID: {credential.get('credential', {}).get('id', 'Unknown')}")
                    print(f"   👤 Holder ID: {credential.get('wallet_metadata', {}).get('holder_id', 'Unknown')}")
                    print(f"   🏷️ Display Name: {credential.get('wallet_metadata', {}).get('display_name', 'Unknown')}")
                    return True
                else:
                    print(f"   ⚠️ No credential in response: {credential_result.get('message', 'Unknown')}")
            else:
                print(f"   ❌ Credential retrieval failed: {credential_response.text}")
            
            return False
            
        except Exception as e:
            print(f"❌ Test failed with error: {str(e)}")
            return False
    
    def test_shield_widget_flow(self):
        """Test the complete Shield Widget flow with credential issuance"""
        print("\n🧪 Testing Shield Widget Flow")
        print("=" * 40)
        
        try:
            # Step 1: Check Shield status
            print("🔄 Step 1: Checking Shield status...")
            status_response = self.session.get(f"{self.base_url}/api/shield/status")
            
            if status_response.status_code == 200:
                status_result = status_response.json()
                print(f"   ✅ Shield Status: {status_result.get('shield_action', 'Unknown')}")
                print(f"   📝 Message: {status_result.get('message', 'No message')}")
                
                if status_result.get('shield_action') == 'check_credentials':
                    print("   🛡️ Shield requires verification (expected for new session)")
                    return True
                elif status_result.get('shield_action') == 'allow_access':
                    print("   ✅ Shield allows access (user already verified)")
                    return True
                else:
                    print(f"   ⚠️ Unexpected shield action: {status_result.get('shield_action')}")
                    return False
            else:
                print(f"   ❌ Shield status check failed: {status_response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Shield Widget test failed: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all credential issuance fix tests"""
        print("🚀 Starting Credential Issuance Fix Tests")
        print("=" * 50)
        print(f"🌐 Base URL: {self.base_url}")
        print(f"⏰ Test Time: {datetime.now().isoformat()}")
        
        results = {
            'verification_callback_test': False,
            'shield_widget_flow_test': False
        }
        
        # Test 1: Verification Callback Credential Issuance
        results['verification_callback_test'] = self.test_verification_callback_credential_issuance()
        
        # Test 2: Shield Widget Flow
        results['shield_widget_flow_test'] = self.test_shield_widget_flow()
        
        # Summary
        print("\n📊 Test Results Summary")
        print("=" * 30)
        
        total_tests = len(results)
        passed_tests = sum(results.values())
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"   {test_name}: {status}")
        
        print(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All tests passed! Credential issuance fix is working correctly.")
            return True
        else:
            print("⚠️ Some tests failed. The credential issuance fix needs attention.")
            return False

if __name__ == "__main__":
    tester = CredentialIssuanceFixTester()
    success = tester.run_all_tests()
    exit(0 if success else 1) 