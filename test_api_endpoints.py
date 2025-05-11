#!/usr/bin/env python3
"""
API Testing Script for Lemma Enterprise

This script tests the API endpoints of the Lemma Human Verification System
to ensure the system is functioning properly.
"""
import os
import sys
import requests
import uuid
import json
from urllib.parse import urljoin

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Base URL for the application
BASE_URL = "https://localhost:5000"

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 50)
    print(f" {title}")
    print("=" * 50)

def test_endpoint(endpoint, method="GET", data=None, expected_status=200):
    """Test an API endpoint."""
    url = urljoin(BASE_URL, endpoint)
    print(f"Testing {method} {url}...")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, verify=False, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, verify=False, timeout=10)
        else:
            print(f"❌ Unsupported method: {method}")
            return False
        
        if response.status_code == expected_status:
            print(f"✅ Status: {response.status_code}")
            return response
        else:
            print(f"❌ Status: {response.status_code} (expected {expected_status})")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_home_page():
    """Test the home page."""
    print_header("Testing Home Page")
    return test_endpoint("/")

def test_admin_login():
    """Test the admin login page."""
    print_header("Testing Admin Login Page")
    return test_endpoint("/admin/login")

def test_verify_page():
    """Test the verification page."""
    print_header("Testing Verification Page")
    return test_endpoint("/verify")

def test_credential_issuance():
    """Test credential issuance."""
    print_header("Testing Credential Issuance")
    
    # Generate a test user ID
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    print(f"Test User ID: {user_id}")
    
    # Get credential for the user
    response = test_endpoint(f"/api/credential/{user_id}")
    if not response:
        return False
    
    try:
        credential = response.json()
        if "id" in credential and "proof" in credential:
            print(f"✅ Credential issued successfully")
            print(f"  - Credential ID: {credential.get('id')}")
            return credential
        else:
            print("❌ Invalid credential format")
            return False
    except Exception as e:
        print(f"❌ Error parsing credential: {e}")
        return False

def test_credential_verification(credential):
    """Test credential verification."""
    print_header("Testing Credential Verification")
    
    if not credential:
        print("❌ No credential to verify")
        return False
    
    response = test_endpoint("/api/verify", method="POST", data={"credential": credential})
    if not response:
        return False
    
    try:
        result = response.json()
        if result.get("valid"):
            print("✅ Credential verified successfully")
            return True
        else:
            print(f"❌ Credential verification failed: {result.get('reason')}")
            return False
    except Exception as e:
        print(f"❌ Error parsing verification result: {e}")
        return False

def test_presentation_creation(credential):
    """Test presentation creation."""
    print_header("Testing Presentation Creation")
    
    if not credential:
        print("❌ No credential for presentation")
        return False
    
    # Generate a random challenge
    challenge = uuid.uuid4().hex
    print(f"Challenge: {challenge}")
    
    response = test_endpoint("/api/presentation", method="POST", 
                           data={"credential": credential, "challenge": challenge})
    if not response:
        return False
    
    try:
        presentation = response.json()
        if "proof" in presentation and "challenge" in presentation:
            print("✅ Presentation created successfully")
            return presentation, challenge
        else:
            print("❌ Invalid presentation format")
            return False
    except Exception as e:
        print(f"❌ Error parsing presentation: {e}")
        return False

def test_presentation_verification(presentation_data):
    """Test presentation verification."""
    print_header("Testing Presentation Verification")
    
    if not presentation_data:
        print("❌ No presentation to verify")
        return False
    
    presentation, challenge = presentation_data
    
    response = test_endpoint("/api/verify-presentation", method="POST",
                           data={"presentation": presentation, "challenge": challenge})
    if not response:
        return False
    
    try:
        result = response.json()
        if result.get("valid"):
            print("✅ Presentation verified successfully")
            return True
        else:
            print(f"❌ Presentation verification failed: {result.get('reason')}")
            return False
    except Exception as e:
        print(f"❌ Error parsing verification result: {e}")
        return False

def test_human_verification(presentation_data):
    """Test human verification."""
    print_header("Testing Human Verification")
    
    if not presentation_data:
        print("❌ No presentation for human verification")
        return False
    
    presentation, challenge = presentation_data
    
    response = test_endpoint("/api/verify-human", method="POST",
                           data={"presentation": presentation, "challenge": challenge})
    if not response:
        return False
    
    try:
        result = response.json()
        if result.get("success"):
            print("✅ Human verification successful")
            print(f"  - Redirect URL: {result.get('redirect')}")
            return True
        else:
            print(f"❌ Human verification failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Error parsing verification result: {e}")
        return False

def main():
    """Main function to run all API tests."""
    print("=== LEMMA ENTERPRISE API TESTING ===\n")
    
    # Test basic pages
    home_result = test_home_page()
    admin_result = test_admin_login()
    verify_result = test_verify_page()
    
    # Test credential flow
    credential = test_credential_issuance()
    if credential:
        verify_result = test_credential_verification(credential)
        presentation_data = test_presentation_creation(credential)
        if presentation_data:
            pres_verify_result = test_presentation_verification(presentation_data)
            human_verify_result = test_human_verification(presentation_data)
    
    # Print summary and suggestions
    print("\n=== TEST SUMMARY ===")
    
    results = {
        "Home Page": home_result,
        "Admin Login Page": admin_result,
        "Verification Page": verify_result,
        "Credential Issuance": credential is not None,
        "Credential Verification": verify_result,
        "Presentation Creation": presentation_data is not None,
        "Presentation Verification": pres_verify_result,
        "Human Verification": human_verify_result
    }
    
    for endpoint, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{endpoint}: {status}")
    
    print("\n=== NEXT STEPS ===")
    print("1. If all tests passed, you can deploy with confidence")
    print("2. For any failures, review the error messages and fix the issues")
    print("3. After fixes, run the tests again with:")
    print("   python test_api_endpoints.py")
    
    return all(results.values())

if __name__ == "__main__":
    main()
