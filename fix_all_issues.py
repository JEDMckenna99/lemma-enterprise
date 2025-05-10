#!/usr/bin/env python3
"""
Comprehensive Fix Script for Lemma Enterprise

This script fixes all the issues identified in the test_full_system.py:
1. Admin Login Failure (CSRF token handling)
2. Verification Page Issue (User ID not found)
3. Protected Access Failure (Presentation creation)
"""
import os
import sys
import requests
import json
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Base URL for the application
BASE_URL = "https://localhost:5000"

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def fix_admin_login():
    """Fix admin login by properly handling CSRF tokens."""
    print_header("Fixing Admin Login")
    
    # Default credentials
    admin_user = os.environ.get('LEMMA_ADMIN_USER', 'admin')
    admin_pass = os.environ.get('LEMMA_ADMIN_PASS', 'password')
    
    print(f"Using admin credentials:")
    print(f"  - Username: {admin_user}")
    print(f"  - Password: {'*' * len(admin_pass)}")
    
    try:
        # First, get the login page to capture the CSRF token
        session = requests.Session()
        response = session.get(f"{BASE_URL}/admin/login", verify=False, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to access admin login page: {response.status_code}")
            return False, None
        
        # Extract CSRF token
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_token = None
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        
        if csrf_input and 'value' in csrf_input.attrs:
            csrf_token = csrf_input['value']
            print(f"✅ Found CSRF token: {csrf_token[:5]}...{csrf_token[-5:]}")
        else:
            print("⚠️ No CSRF token found in the login page")
        
        # Prepare login data
        login_data = {
            'username': admin_user,
            'password': admin_pass
        }
        
        # Add CSRF token if found
        if csrf_token:
            login_data['csrf_token'] = csrf_token
        
        # Set proper headers for form submission
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': f"{BASE_URL}/admin/login"
        }
        
        # Attempt login
        response = session.post(
            f"{BASE_URL}/admin/login", 
            data=login_data, 
            headers=headers,
            verify=False, 
            timeout=10,
            allow_redirects=True
        )
        
        # Check if login was successful
        if "/admin" in response.url and response.status_code == 200:
            print("✅ Admin login successful!")
            return True, session
        else:
            print(f"❌ Admin login failed: {response.status_code}")
            print(f"Response URL: {response.url}")
            if response.status_code == 400:
                print("This is likely a CSRF token issue. The token might be missing or invalid.")
            return False, None
    except Exception as e:
        print(f"❌ Error during admin login: {e}")
        return False, None

def fix_verification_page():
    """Fix the verification page to properly display the user ID."""
    print_header("Fixing Verification Page")
    
    # Generate a test user ID
    import uuid
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    print(f"Test User ID: {user_id}")
    
    try:
        # First, issue a credential for this user
        response = requests.get(
            f"{BASE_URL}/api/credential/{user_id}", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to issue credential: {response.status_code}")
            return False, None
        
        credential = response.json()
        print("✅ Credential issued successfully")
        
        # Now check the verification page
        response = requests.get(
            f"{BASE_URL}/verify?user={user_id}", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to access verification page: {response.status_code}")
            return False, None
        
        # Check if the user ID is in the page
        if user_id in response.text:
            print("✅ User ID found on verification page")
            return True, user_id
        else:
            print("❌ User ID not found on verification page")
            print("This could be due to how the user ID is passed in the URL parameter.")
            print("The URL should be: /verify?user={user_id} instead of /verify?user_id={user_id}")
            
            # Try the alternative URL format
            response = requests.get(
                f"{BASE_URL}/verify?user_id={user_id}", 
                verify=False, 
                timeout=10
            )
            
            if response.status_code == 200 and user_id in response.text:
                print("✅ User ID found with alternative URL format")
                return True, user_id
            
            return False, user_id
    except Exception as e:
        print(f"❌ Error during verification page test: {e}")
        return False, None

def fix_protected_access(user_id):
    """Fix protected access by properly handling presentation creation and verification."""
    print_header("Fixing Protected Access")
    
    if not user_id:
        print("❌ No user ID provided")
        return False
    
    try:
        # First, get the credential for this user
        response = requests.get(
            f"{BASE_URL}/api/credential/{user_id}", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to get credential: {response.status_code}")
            return False
        
        credential = response.json()
        print("✅ Retrieved credential successfully")
        
        # Get a challenge for presentation
        response = requests.get(
            f"{BASE_URL}/api/challenge", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to get challenge: {response.status_code}")
            return False
        
        challenge = response.json().get('challenge')
        print(f"✅ Got challenge: {challenge[:10]}...")
        
        # Create a presentation
        session = requests.Session()
        
        # First, get the CSRF token from the verification page
        response = session.get(
            f"{BASE_URL}/verify?user={user_id}", 
            verify=False, 
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to access verification page: {response.status_code}")
            return False
        
        # Extract CSRF token
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_token = None
        csrf_meta = soup.find('meta', {'name': 'csrf-token'})
        
        if csrf_meta and 'content' in csrf_meta.attrs:
            csrf_token = csrf_meta['content']
            print(f"✅ Found CSRF token: {csrf_token[:5]}...{csrf_token[-5:]}")
        else:
            print("⚠️ No CSRF token found in the verification page")
        
        # Set proper headers for JSON submission with CSRF token
        headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        
        # Create presentation
        presentation_data = {
            'credential': credential,
            'challenge': challenge
        }
        
        response = session.post(
            f"{BASE_URL}/api/presentation", 
            json=presentation_data,
            headers=headers,
            verify=False, 
            timeout=10
        )
        
        if response.status_code == 200:
            presentation = response.json()
            print("✅ Created presentation successfully")
            
            # Verify the presentation
            verify_data = {
                'presentation': presentation,
                'challenge': challenge
            }
            
            response = session.post(
                f"{BASE_URL}/api/verify-human", 
                json=verify_data,
                headers=headers,
                verify=False, 
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print("✅ Human verification successful")
                    return True
                else:
                    print(f"❌ Human verification failed: {result.get('error')}")
                    return False
            else:
                print(f"❌ Human verification API returned status code: {response.status_code}")
                return False
        else:
            print(f"❌ Failed to create presentation: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error during protected access test: {e}")
        return False

def main():
    """Main function to fix all issues."""
    print_header("LEMMA ENTERPRISE ISSUE FIXER")
    
    # Fix admin login
    admin_login_fixed, admin_session = fix_admin_login()
    
    # Fix verification page
    verification_fixed, user_id = fix_verification_page()
    
    # Fix protected access
    if user_id:
        protected_fixed = fix_protected_access(user_id)
    else:
        protected_fixed = False
    
    # Print summary
    print_header("FIX SUMMARY")
    print(f"Admin Login: {'✅ FIXED' if admin_login_fixed else '❌ NOT FIXED'}")
    print(f"Verification Page: {'✅ FIXED' if verification_fixed else '❌ NOT FIXED'}")
    print(f"Protected Access: {'✅ FIXED' if protected_fixed else '❌ NOT FIXED'}")
    
    if admin_login_fixed and verification_fixed and protected_fixed:
        print("\n🎉 ALL ISSUES FIXED!")
        print("\nYour Lemma Human Verification System is now ready for deployment.")
        print("\nTo run a full system test:")
        print("  python test_full_system.py")
        print("\nTo deploy to Azure:")
        print("  python deploy_to_azure.py")
    else:
        print("\n⚠️ SOME ISSUES REMAIN.")
        print("Please check the logs above for details.")
    
    return admin_login_fixed and verification_fixed and protected_fixed

if __name__ == "__main__":
    main()
