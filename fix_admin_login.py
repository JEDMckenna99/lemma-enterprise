#!/usr/bin/env python3
"""
Admin Login Fix for Lemma Enterprise

This script sets the admin credentials in the environment and tests the admin login.
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Base URL for the application
BASE_URL = "https://localhost:5000"

def set_admin_credentials():
    """Set admin credentials in environment variables."""
    # Default credentials
    admin_user = os.environ.get('LEMMA_ADMIN_USER', 'admin')
    admin_pass = os.environ.get('LEMMA_ADMIN_PASS', 'password')
    
    print(f"Current admin credentials:")
    print(f"  - Username: {admin_user}")
    print(f"  - Password: {'*' * len(admin_pass)}")
    
    # Update .env file with admin credentials
    env_path = os.path.join(os.getcwd(), '.env')
    
    # Read existing .env content
    env_content = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_content = f.readlines()
    
    # Check if admin credentials are already in .env
    admin_user_found = False
    admin_pass_found = False
    
    for i, line in enumerate(env_content):
        if line.startswith('LEMMA_ADMIN_USER='):
            env_content[i] = f'LEMMA_ADMIN_USER={admin_user}\n'
            admin_user_found = True
        elif line.startswith('LEMMA_ADMIN_PASS='):
            env_content[i] = f'LEMMA_ADMIN_PASS={admin_pass}\n'
            admin_pass_found = True
    
    # Add admin credentials if not found
    if not admin_user_found:
        env_content.append(f'LEMMA_ADMIN_USER={admin_user}\n')
    if not admin_pass_found:
        env_content.append(f'LEMMA_ADMIN_PASS={admin_pass}\n')
    
    # Write updated .env content
    with open(env_path, 'w') as f:
        f.writelines(env_content)
    
    print(f"✅ Admin credentials set in .env file")
    
    # Set in current environment
    os.environ['LEMMA_ADMIN_USER'] = admin_user
    os.environ['LEMMA_ADMIN_PASS'] = admin_pass
    
    return admin_user, admin_pass

def test_admin_login(admin_user, admin_pass):
    """Test admin login with the provided credentials."""
    print("\nTesting admin login...")
    
    try:
        # First, get the login page to capture any CSRF token
        session = requests.Session()
        response = session.get(f"{BASE_URL}/admin/login", verify=False, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to access admin login page: {response.status_code}")
            return False
        
        # Extract CSRF token if present
        csrf_token = None
        if 'csrf_token' in response.text:
            import re
            match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
            if match:
                csrf_token = match.group(1)
                print(f"Found CSRF token: {csrf_token[:5]}...{csrf_token[-5:]}")
        
        # Prepare login data
        login_data = {
            'username': admin_user,
            'password': admin_pass
        }
        
        # Add CSRF token if found
        if csrf_token:
            login_data['csrf_token'] = csrf_token
        
        # Attempt login
        response = session.post(
            f"{BASE_URL}/admin/login", 
            data=login_data, 
            verify=False, 
            timeout=10,
            allow_redirects=True
        )
        
        # Check if login was successful
        if "/admin" in response.url and response.status_code == 200:
            print("✅ Admin login successful!")
            return True
        else:
            print(f"❌ Admin login failed: {response.status_code}")
            print("Response URL:", response.url)
            print("Response headers:", response.headers)
            return False
    except Exception as e:
        print(f"❌ Error during admin login test: {e}")
        return False

def main():
    """Main function to fix admin login."""
    print("=== LEMMA ADMIN LOGIN FIX ===\n")
    
    # Set admin credentials
    admin_user, admin_pass = set_admin_credentials()
    
    # Test admin login
    login_success = test_admin_login(admin_user, admin_pass)
    
    if login_success:
        print("\n🎉 Admin login is now working!")
        print("You can access the admin interface at:")
        print(f"{BASE_URL}/admin")
    else:
        print("\n⚠️ Admin login is still not working.")
        print("The server may need to be restarted to apply the new credentials.")
        print("Try stopping and restarting the server with:")
        print("  1. Press Ctrl+C to stop the current server")
        print("  2. Run: python app.py")
    
    return login_success

if __name__ == "__main__":
    main()
