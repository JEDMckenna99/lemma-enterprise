#!/usr/bin/env python3
"""
Comprehensive System Test for Lemma Enterprise

This script tests all aspects of the Lemma Human Verification System
to ensure it's fully functional before deployment.
"""
import os
import sys
import requests
import uuid
import json
import time
from urllib.parse import urljoin
from twilio.rest import Client
from dotenv import load_dotenv

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Base URL for the application
BASE_URL = "https://localhost:5000"

# Twilio credentials
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def test_server_running():
    """Test if the server is running."""
    print_header("Testing Server Connection")
    
    try:
        response = requests.get(f"{BASE_URL}/", verify=False, timeout=10)
        if response.status_code == 200:
            print("✅ Server is running and accessible")
            return True
        else:
            print(f"❌ Server returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to server: {e}")
        return False

def test_admin_interface():
    """Test the admin interface."""
    print_header("Testing Admin Interface")
    
    try:
        response = requests.get(f"{BASE_URL}/admin/login", verify=False, timeout=10)
        if response.status_code == 200:
            print("✅ Admin login page is accessible")
            
            # Try to log in with default credentials
            admin_user = os.environ.get('LEMMA_ADMIN_USER', 'admin')
            admin_pass = os.environ.get('LEMMA_ADMIN_PASS', 'password')
            
            print(f"Attempting to log in as: {admin_user}")
            session = requests.Session()
            
            # First get the CSRF token
            response = session.get(f"{BASE_URL}/admin/login", verify=False, timeout=10)
            
            # Extract CSRF token if present in the page
            csrf_token = None
            if 'csrf_token' in response.text:
                import re
                match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
                if match:
                    csrf_token = match.group(1)
            
            login_data = {
                'username': admin_user,
                'password': admin_pass
            }
            
            # Add CSRF token if found
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Add testing header to bypass CSRF in testing mode
            headers = {'X-Testing': 'True'}
            
            response = session.post(
                f"{BASE_URL}/admin/login", 
                data=login_data,
                headers=headers,
                verify=False, 
                timeout=10,
                allow_redirects=True
            )
            
            if "/admin" in response.url and response.status_code == 200:
                print("✅ Admin login successful")
                return session
            else:
                print(f"❌ Admin login failed: {response.status_code}")
                return None
        else:
            print(f"❌ Admin login page returned status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error accessing admin interface: {e}")
        return None

def test_credential_issuance():
    """Test credential issuance."""
    print_header("Testing Credential Issuance")
    
    # Generate a test user ID
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    print(f"Test User ID: {user_id}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/credential/{user_id}", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code == 200:
            credential = response.json()
            if "id" in credential and "proof" in credential:
                print("✅ Credential issued successfully")
                print(f"  - Credential ID: {credential.get('id')}")
                return user_id, credential
            else:
                print("❌ Invalid credential format")
                return user_id, None
        else:
            print(f"❌ Failed to issue credential: {response.status_code}")
            return user_id, None
    except Exception as e:
        print(f"❌ Error during credential issuance: {e}")
        return user_id, None

def test_verification_page(user_id):
    """Test the verification page for a user."""
    print_header("Testing Verification Page")
    
    try:
        # Use the correct URL format with user_id parameter
        response = requests.get(f"{BASE_URL}/verify?user_id={user_id}", verify=False, timeout=10)
        
        if response.status_code == 200:
            print("✅ Verification page is accessible")
            
            if user_id in response.text:
                print("✅ User ID found on verification page")
                return True
            else:
                print("❌ User ID not found on verification page")
                return False
        else:
            print(f"❌ Verification page returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error accessing verification page: {e}")
        return False

def test_twilio_integration():
    """Test Twilio SMS integration."""
    print_header("Testing Twilio Integration")
    
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("❌ Twilio credentials not fully configured")
        print("Skipping Twilio integration test")
        return False
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        print(f"✅ Connected to Twilio account: {account.friendly_name}")
        print(f"✅ Twilio phone number: {TWILIO_PHONE_NUMBER}")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Twilio: {e}")
        return False

def test_sms_invitation(admin_session, user_id, to_phone):
    """Test SMS invitation functionality."""
    print_header("Testing SMS Invitation")
    
    if not admin_session:
        print("❌ No admin session available")
        print("Skipping SMS invitation test")
        return False
    
    if not to_phone:
        print("❌ No recipient phone number provided")
        print("Skipping SMS invitation test")
        return False
    
    # Create verification link
    verification_link = f"{BASE_URL}/verify?user={user_id}"
    
    # Send SMS via the admin API
    try:
        sms_data = {
            'phone': to_phone,
            'link': verification_link
        }
        
        response = admin_session.post(
            f"{BASE_URL}/admin/send_sms", 
            json=sms_data, 
            verify=False, 
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ SMS invitation sent successfully")
                return True
            else:
                print(f"❌ Failed to send SMS: {result.get('error')}")
                return False
        else:
            print(f"❌ SMS API returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error sending SMS invitation: {e}")
        return False

def test_protected_access(user_id, credential):
    """Test access to protected resources."""
    print_header("Testing Protected Access")
    
    if not credential:
        print("❌ No credential available")
        print("Skipping protected access test")
        return False
    
    try:
        # Get a challenge from the server
        response = requests.get(
            f"{BASE_URL}/api/generate-challenge", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to get challenge: {response.status_code}")
            return False
        
        challenge = response.json().get('challenge')
        print(f"✅ Got challenge from server: {challenge[:10]}...")
        
        # Create a presentation
        # Add CSRF headers
        headers = {
            'Content-Type': 'application/json',
            'X-Testing': 'True'
        }
        
        response = requests.post(
            f"{BASE_URL}/api/presentation", 
            json={
                'credential': credential,
                'challenge': challenge
            }, 
            headers=headers,
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to create presentation: {response.status_code}")
            return False
        
        presentation = response.json()
        
        # Verify the presentation
        response = requests.post(
            f"{BASE_URL}/api/verify-human", 
            json={
                'presentation': presentation,
                'challenge': challenge
            }, 
            headers=headers,
            verify=False, 
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ Human verification successful")
                print(f"  - Redirect URL: {result.get('redirect')}")
                return True
            else:
                print(f"❌ Human verification failed: {result.get('error')}")
                return False
        else:
            print(f"❌ Human verification API returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error during protected access test: {e}")
        return False

def main():
    """Main function to run all system tests."""
    print_header("LEMMA ENTERPRISE FULL SYSTEM TEST")
    print(f"Testing against: {BASE_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Track test results
    results = {}
    
    # Test 1: Server Connection
    results['server'] = test_server_running()
    if not results['server']:
        print("\n❌ Server is not running. Cannot proceed with tests.")
        return False
    
    # Test 2: Admin Interface
    admin_session = test_admin_interface()
    results['admin'] = bool(admin_session)
    
    # Test 3: Credential Issuance
    user_id, credential = test_credential_issuance()
    results['credential'] = bool(credential)
    
    # Test 4: Verification Page
    if user_id:
        results['verification_page'] = test_verification_page(user_id)
    else:
        results['verification_page'] = False
    
    # Test 5: Twilio Integration
    results['twilio'] = test_twilio_integration()
    
    # Test 6: SMS Invitation (if phone number provided)
    if len(sys.argv) > 1 and results['admin']:
        to_phone = sys.argv[1]
        results['sms'] = test_sms_invitation(admin_session, user_id, to_phone)
    else:
        print("\nNo phone number provided for SMS testing.")
        print("To test SMS, run: python test_full_system.py +1234567890")
        results['sms'] = None
    
    # Test 7: Protected Access
    if credential:
        results['protected'] = test_protected_access(user_id, credential)
    else:
        results['protected'] = False
    
    # Print summary
    print_header("TEST SUMMARY")
    
    all_passed = True
    for test_name, result in results.items():
        if result is None:
            status = "⚠️ SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
            if test_name != 'sms':  # Don't count skipped SMS test as failure
                all_passed = False
        
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYour Lemma Human Verification System is functioning properly and ready for deployment.")
        print("\nTo deploy to Azure:")
        print("  python deploy_to_azure.py")
    else:
        print("\n⚠️ SOME TESTS FAILED.")
        print("Please fix the issues before deploying.")
    
    # If we have a valid credential, save the verification URL
    if user_id and credential:
        verification_url = f"{BASE_URL}/verify?user_id={user_id}"
        print(f"\nVerification URL for testing: {verification_url}")
        
        # Save credential info to file
        info = {
            "user_id": user_id,
            "credential_id": credential.get("id"),
            "verification_url": verification_url
        }
        
        filename = f"lemma_test_credential_{user_id}.json"
        with open(filename, "w") as f:
            json.dump(info, f, indent=2)
        
        print(f"Credential information saved to: {filename}")
    
    return all_passed

if __name__ == "__main__":
    main()
