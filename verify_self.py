#!/usr/bin/env python3
"""
Self-Verification Script for Lemma Enterprise

This script allows you to verify yourself as a human in the Lemma system
without requiring SMS verification.
"""
import os
import sys
import requests
import uuid
import json
import webbrowser
from urllib.parse import urljoin
from dotenv import load_dotenv

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Base URL for the application
BASE_URL = "https://localhost:5000"

def create_user_id(name=None):
    """Create a user ID for self-verification."""
    if name:
        # Create a user ID based on the provided name
        user_id = f"{name.lower().replace(' ', '_')}-{uuid.uuid4().hex[:4]}"
    else:
        # Generate a random user ID
        user_id = f"self-{uuid.uuid4().hex[:8]}"
    
    return user_id

def issue_credential(user_id):
    """Issue a credential for the specified user ID."""
    print(f"Issuing credential for user: {user_id}")
    
    url = urljoin(BASE_URL, f"/api/credential/{user_id}")
    try:
        response = requests.get(url, verify=False, timeout=10)
        if response.status_code == 200:
            credential = response.json()
            print("✅ Credential issued successfully!")
            return credential
        else:
            print(f"❌ Failed to issue credential: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error issuing credential: {e}")
        return None

def verify_credential(credential):
    """Verify the issued credential."""
    if not credential:
        print("No credential to verify")
        return False
    
    print("Verifying credential...")
    
    url = urljoin(BASE_URL, "/api/verify")
    try:
        response = requests.post(url, json={"credential": credential}, verify=False, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("valid"):
                print("✅ Credential verified successfully!")
                return True
            else:
                print(f"❌ Credential verification failed: {result.get('reason')}")
                return False
        else:
            print(f"❌ Failed to verify credential: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error verifying credential: {e}")
        return False

def open_verification_page(user_id):
    """Open the verification page in a web browser."""
    verification_url = urljoin(BASE_URL, f"/verify?user={user_id}")
    print(f"Opening verification page: {verification_url}")
    
    try:
        webbrowser.open(verification_url)
        print("✅ Verification page opened in your browser")
        print("Note: You may need to accept the security warning for the self-signed certificate")
        return True
    except Exception as e:
        print(f"❌ Failed to open browser: {e}")
        print(f"Please manually navigate to: {verification_url}")
        return False

def save_credential_info(user_id, credential):
    """Save credential information to a file for future reference."""
    if not credential:
        return False
    
    info = {
        "user_id": user_id,
        "credential_id": credential.get("id"),
        "issued_at": credential.get("issuanceDate"),
        "verification_url": f"{BASE_URL}/verify?user={user_id}"
    }
    
    filename = f"lemma_credential_{user_id}.json"
    with open(filename, "w") as f:
        json.dump(info, f, indent=2)
    
    print(f"✅ Credential information saved to: {filename}")
    return True

def main():
    """Main function to verify yourself as a human."""
    print("=== LEMMA SELF-VERIFICATION ===\n")
    
    # Get or generate user ID
    if len(sys.argv) > 1:
        name = sys.argv[1]
        user_id = create_user_id(name)
    else:
        name = input("Enter your name (or press Enter to generate a random ID): ").strip()
        user_id = create_user_id(name) if name else create_user_id()
    
    print(f"Using user ID: {user_id}")
    
    # Issue credential
    credential = issue_credential(user_id)
    if not credential:
        print("❌ Failed to complete self-verification due to credential issuance failure")
        return False
    
    # Verify credential
    verified = verify_credential(credential)
    
    # Save credential information
    save_credential_info(user_id, credential)
    
    # Open verification page
    open_verification_page(user_id)
    
    print("\n=== VERIFICATION SUMMARY ===")
    print(f"User ID: {user_id}")
    print(f"Credential Issued: {'✅ Yes' if credential else '❌ No'}")
    print(f"Credential Verified: {'✅ Yes' if verified else '❌ No'}")
    print(f"Verification URL: {BASE_URL}/verify?user={user_id}")
    
    print("\n🎉 Self-verification process completed!")
    print("You can now use this credential to access the protected areas of your Lemma system.")
    print("To onboard others, you can use the SMS invitation functionality.")
    
    return True

if __name__ == "__main__":
    main()
