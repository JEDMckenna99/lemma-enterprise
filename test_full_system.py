#!/usr/bin/env python3
"""
Full System Testing Script for Lemma Enterprise

This script tests the complete functionality of the Lemma Human Verification System,
including credential issuance, verification, and protection.
"""
import os
import sys
import requests
import json
import uuid
from urllib.parse import urljoin
import time
import getpass
import random
import string

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Base URL for the application
BASE_URL = os.environ.get('LEMMA_BASE_URL', 'http://localhost:5000')

# Admin credentials
ADMIN_USER = os.environ.get('LEMMA_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('LEMMA_ADMIN_PASS', 'password')

# Verify TLS
VERIFY_TLS = os.environ.get('VERIFY_TLS', 'True').lower() in ('true', '1', 't')

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 50)
    print(f" {title}")
    print("=" * 50)

def test_api_health():
    """Test the API health endpoint."""
    print_header("Testing API Health")
    
    url = urljoin(BASE_URL, "/api/health")
    
    try:
        response = requests.get(url, verify=VERIFY_TLS)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'ok':
                print("✅ API health check passed")
                return True
            else:
                print(f"❌ API returned unexpected data: {data}")
                return False
        else:
            print(f"❌ API health check failed with status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception during API health check: {e}")
        return False

def login_admin():
    """Log in as admin and return the session."""
    print_header("Testing Admin Login")
    
    login_url = urljoin(BASE_URL, "/admin/login")
    session = requests.Session()
    
    # Handle CSRF token if required
    try:
        # Get the login page to extract CSRF token if needed
        response = session.get(login_url, verify=VERIFY_TLS)
        
        # Simple attempt to extract CSRF token from form
        csrf_token = None
        if 'csrf_token' in response.text:
            import re
            csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
                print("✅ CSRF token extracted from login form")
        
        # Prepare login data
        login_data = {
            'username': ADMIN_USER,
            'password': ADMIN_PASS
        }
        
        # Add CSRF token if found
        if csrf_token:
            login_data['csrf_token'] = csrf_token
        
        # Add test header for testing environment
        headers = {'X-Testing': 'True'}
        
        # Attempt login
        response = session.post(
            login_url, 
            data=login_data, 
            headers=headers,
            allow_redirects=True,
            verify=VERIFY_TLS
        )
        
        # Check if login was successful
        if 'admin' in response.url and response.status_code == 200:
            print("✅ Admin login successful")
            return session
        else:
            print(f"❌ Admin login failed - Status: {response.status_code}")
            print(f"Response URL: {response.url}")
            return None
    except Exception as e:
        print(f"❌ Exception during admin login: {e}")
        return None

def test_issue_credential(admin_session):
    """Test credential issuance functionality."""
    print_header("Testing Credential Issuance")
    
    if not admin_session:
        print("❌ Admin session not available, cannot test credential issuance")
        return None
    
    # Generate a test user ID
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    print(f"Generated test user ID: {user_id}")
    
    # Get the issue URL
    issue_url = urljoin(BASE_URL, "/admin/issue")
    
    try:
        # Get CSRF token from the form
        response = admin_session.get(urljoin(BASE_URL, "/admin"), verify=VERIFY_TLS)
        csrf_token = None
        
        if 'csrf_token' in response.text:
            import re
            csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
        
        # Prepare issue data
        issue_data = {
            'user_id': user_id
        }
        
        # Add CSRF token if found
        if csrf_token:
            issue_data['csrf_token'] = csrf_token
        
        # Issue the credential
        response = admin_session.post(
            issue_url, 
            data=issue_data, 
            allow_redirects=True,
            verify=VERIFY_TLS
        )
        
        # Check if issuance was successful
        if response.status_code == 200 and 'success' in response.text.lower():
            print(f"✅ Credential issued successfully for user: {user_id}")
            return user_id
        else:
            print(f"❌ Credential issuance failed - Status: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exception during credential issuance: {e}")
        return None

def test_credential_verification(user_id):
    """Test credential verification functionality."""
    print_header("Testing Credential Verification")
    
    if not user_id:
        print("❌ No user ID available, cannot test credential verification")
        return False
    
    # Get the credential
    credential_url = urljoin(BASE_URL, f"/api/credential/{user_id}")
    
    try:
        # Fetch the credential
        response = requests.get(credential_url, verify=VERIFY_TLS)
        
        if response.status_code != 200:
            print(f"❌ Failed to retrieve credential - Status: {response.status_code}")
            return False
        
        # Parse the credential
        credential = response.json()
        print("✅ Credential retrieved successfully")
        
        # Verify the credential
        verify_url = urljoin(BASE_URL, "/api/verify")
        
        verify_data = {
            'credential': credential
        }
        
        # Send verification request
        response = requests.post(
            verify_url, 
            json=verify_data,
            verify=VERIFY_TLS
        )
        
        if response.status_code != 200:
            print(f"❌ Credential verification request failed - Status: {response.status_code}")
            return False
        
        # Check verification result
        result = response.json()
        
        if result.get('valid'):
            print("✅ Credential verified successfully")
            
            # Print some details about the credential
            print(f"  - User ID: {user_id}")
            print(f"  - Credential ID: {credential.get('id', 'Unknown')}")
            print(f"  - Issuance Date: {credential.get('issuanceDate', 'Unknown')}")
            
            return True
        else:
            print(f"❌ Credential verification failed: {result.get('reason', 'Unknown reason')}")
            return False
    except Exception as e:
        print(f"❌ Exception during credential verification: {e}")
        return False

def test_protected_access(user_id):
    """Test access to protected content with credential."""
    print_header("Testing Protected Access")
    
    if not user_id:
        print("❌ No user ID available, cannot test protected access")
        return False
    
    try:
        # Get the credential
        credential_url = urljoin(BASE_URL, f"/api/credential/{user_id}")
        response = requests.get(credential_url, verify=VERIFY_TLS)
        
        if response.status_code != 200:
            print(f"❌ Failed to retrieve credential - Status: {response.status_code}")
            return False
        
        credential = response.json()
        
        # Generate a challenge
        challenge_url = urljoin(BASE_URL, "/api/generate-challenge")
        response = requests.get(challenge_url, verify=VERIFY_TLS)
        
        if response.status_code != 200:
            print(f"❌ Failed to generate challenge - Status: {response.status_code}")
            return False
        
        challenge = response.json().get('challenge')
        
        # Create a presentation
        presentation_url = urljoin(BASE_URL, "/api/presentation")
        presentation_data = {
            'credential': credential,
            'challenge': challenge
        }
        
        response = requests.post(
            presentation_url, 
            json=presentation_data,
            verify=VERIFY_TLS
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to create presentation - Status: {response.status_code}")
            return False
        
        presentation = response.json()
        
        # Verify presentation for access
        verify_url = urljoin(BASE_URL, "/api/verify-human")
        verify_data = {
            'presentation': presentation,
            'challenge': challenge
        }
        
        response = requests.post(
            verify_url, 
            json=verify_data,
            verify=VERIFY_TLS
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to verify presentation - Status: {response.status_code}")
            return False
        
        result = response.json()
        
        if result.get('success'):
            print("✅ Protected access granted successfully")
            redirect_url = result.get('redirect')
            print(f"  - Redirect URL: {redirect_url}")
            return True
        else:
            print(f"❌ Protected access denied: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Exception during protected access test: {e}")
        return False

def test_api_docs():
    """Test API documentation access."""
    print_header("Testing API Documentation")
    
    url = urljoin(BASE_URL, "/api/docs")
    
    try:
        response = requests.get(url, verify=VERIFY_TLS)
        
        if response.status_code == 200:
            print("✅ API documentation available")
            return True
        elif response.status_code == 404:
            print("⚠️ API documentation not available (endpoint not found)")
            return None  # Not a critical failure
        else:
            print(f"❌ Failed to access API documentation - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exception during API documentation test: {e}")
        return False

def main():
    """Main function to run all tests."""
    print("\n🔍 LEMMA ENTERPRISE FULL SYSTEM TEST 🔍")
    print(f"Base URL: {BASE_URL}")
    
    # Initialize results dictionary
    results = {}
    
    # Test 1: API Health
    results['api_health'] = test_api_health()
    
    # Test 2: Admin Login
    admin_session = login_admin()
    results['admin_login'] = admin_session is not None
    
    # Test 3: Credential Issuance
    user_id = test_issue_credential(admin_session)
    results['credential_issuance'] = user_id is not None
    
    # Test 4: Credential Verification
    results['credential_verification'] = test_credential_verification(user_id)
    
    # Test 5: Protected Access
    results['protected_access'] = test_protected_access(user_id)
    
    # Test 6: API Documentation
    results['api_docs'] = test_api_docs()
    
    # Print summary
    print("\n" + "=" * 50)
    print(" 📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    all_tests_passed = True
    for test_name, result in results.items():
        test_name_formatted = test_name.replace('_', ' ').title()
        
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
            all_tests_passed = False
        else:
            status = "⚠️ SKIPPED"
        
        print(f"{test_name_formatted}: {status}")
    
    print("\n" + "=" * 50)
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED! Your Lemma Enterprise system is functioning correctly.")
    else:
        print("⚠️ SOME TESTS FAILED. Please review the test results above.")
    
    print("=" * 50)
    
    # Return overall result
    return all_tests_passed

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
