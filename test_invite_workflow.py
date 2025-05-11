#!/usr/bin/env python3
"""
Invitation Workflow Testing Script for Lemma Enterprise

This script tests the complete invitation workflow for the Lemma Human Verification System,
including credential issuance and verification.
"""
import os
import sys
import requests
import json
import uuid
from urllib.parse import urljoin

# --- Configuration ---
BASE_URL = os.environ.get('LEMMA_BASE_URL', 'http://localhost:5000')
ADMIN_USER = os.environ.get('LEMMA_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('LEMMA_ADMIN_PASS', 'password')

def login_admin():
    """Log in as admin and get session cookie."""
    print("🔑 Logging in as admin...")
    
    login_url = urljoin(BASE_URL, '/admin/login')
    login_data = {
        'username': ADMIN_USER,
        'password': ADMIN_PASS
    }
    
    session = requests.Session()
    response = session.post(login_url, data=login_data, allow_redirects=True)
    
    if response.status_code == 200 and 'admin' in response.url:
        print("✅ Admin login successful")
        return session
    else:
        print(f"❌ Admin login failed: {response.status_code}")
        return None

def issue_credential(session, user_id):
    """Issue a new credential for a user."""
    print(f"📝 Issuing credential for user: {user_id}")
    
    issue_url = urljoin(BASE_URL, '/admin/issue')
    issue_data = {
        'user_id': user_id
    }
    
    response = session.post(issue_url, data=issue_data, allow_redirects=True)
    
    if response.status_code == 200 and 'success' in response.text.lower():
        print("✅ Credential issued successfully")
        return True
    else:
        print(f"❌ Failed to issue credential: {response.status_code}")
        return False

def get_verification_link(user_id):
    """Get verification link for a user."""
    print(f"🔗 Creating verification link for user: {user_id}")
    
    # Create verification link
    verification_link = urljoin(BASE_URL, f'/verify?user={user_id}')
    print(f"✅ Verification link created: {verification_link}")
    return verification_link

def verify_credential(user_id):
    """Verify a user's credential."""
    print(f"🔍 Verifying credential for user: {user_id}")
    
    # Get the credential
    credential_url = urljoin(BASE_URL, f'/api/credential/{user_id}')
    response = requests.get(credential_url)
    
    if response.status_code != 200:
        print(f"❌ Failed to retrieve credential: {response.status_code}")
        return False
    
    credential = response.json()
    
    # Verify the credential
    verify_url = urljoin(BASE_URL, '/api/verify')
    verify_data = {
        'credential': credential
    }
    
    response = requests.post(verify_url, json=verify_data)
    
    if response.status_code != 200:
        print(f"❌ Failed to verify credential: {response.status_code}")
        return False
    
    result = response.json()
    if result.get('valid'):
        print("✅ Credential verified successfully")
        return True
    else:
        print(f"❌ Credential verification failed: {result.get('reason')}")
        return False

def main():
    """Main function to test the invitation workflow."""
    print("=== Lemma Enterprise Invitation Workflow Testing ===")
    
    # Generate a unique user ID for testing
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    
    print(f"📋 Testing invitation workflow:")
    print(f"  - User ID: {user_id}")
    print(f"  - Base URL: {BASE_URL}")
    print("-" * 50)
    
    # Step 1: Admin login
    session = login_admin()
    if not session:
        return
    
    # Step 2: Issue credential
    if not issue_credential(session, user_id):
        return
    
    # Step 3: Get verification link
    verification_link = get_verification_link(user_id)
    
    # Step 4: Verify credential
    verify_credential(user_id)
    
    print("-" * 50)
    print("🎉 Workflow test completed!")
    print(f"👤 User ID: {user_id}")
    print(f"🔗 Verification URL: {verification_link}")
    print("✅ You can now test the verification process by opening the URL in a browser")

if __name__ == "__main__":
    main()
