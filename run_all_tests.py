#!/usr/bin/env python3
"""
Comprehensive Test Suite for Lemma Enterprise

This script runs all necessary tests to ensure the Lemma Human Verification System
is functioning properly before deployment.
"""
import os
import sys
import subprocess
import time
import json
import uuid
import requests
from urllib.parse import urljoin

# Import environment setup
import test_env

# Base URL for the application
BASE_URL = "http://localhost:5000"

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 50)
    print(f" {title}")
    print("=" * 50)

def run_command(command, cwd=None):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            shell=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, f"Error: {e.stderr}"

def test_dependencies():
    """Test if all dependencies are installed."""
    print_header("Testing Dependencies")
    
    success, output = run_command("pip list")
    if not success:
        print("❌ Failed to list dependencies")
        print(output)
        return False
    
    # Check for required packages
    required_packages = [
        "Flask", "Werkzeug", "cryptography", "gunicorn", 
        "pytest", "passlib", "requests", "twilio"
    ]
    
    missing_packages = []
    for package in required_packages:
        if package.lower() not in output.lower():
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing dependencies: {', '.join(missing_packages)}")
        print("Please install missing dependencies with: pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies are installed")
    return True

def test_unit_tests():
    """Run the unit tests."""
    print_header("Running Unit Tests")
    
    success, output = run_command("python run_tests.py")
    if not success:
        print("❌ Unit tests failed")
        print(output)
        return False
    
    print("✅ Unit tests passed")
    return True

def start_server():
    """Start the Flask server for testing."""
    print_header("Starting Flask Server")
    
    # Check if the server is already running
    try:
        response = requests.get(f"{BASE_URL}/")
        print("✅ Server is already running")
        return True
    except requests.exceptions.ConnectionError:
        print("Starting new server instance...")
    
    # Start the server in a new process
    server_process = subprocess.Popen(
        ["python", "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for the server to start
    max_attempts = 10
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{BASE_URL}/")
            print(f"✅ Server started successfully (PID: {server_process.pid})")
            return server_process
        except requests.exceptions.ConnectionError:
            if attempt < max_attempts - 1:
                print(f"Waiting for server to start... ({attempt + 1}/{max_attempts})")
                time.sleep(2)
            else:
                print("❌ Failed to start server")
                return None

def stop_server(server_process):
    """Stop the Flask server."""
    if server_process:
        server_process.terminate()
        server_process.wait()
        print("✅ Server stopped")

def test_api_endpoints():
    """Test the API endpoints."""
    print_header("Testing API Endpoints")
    
    endpoints = [
        "/",                    # Home page
        "/admin/login",         # Admin login
        "/verify",              # Verification page
    ]
    
    all_passed = True
    for endpoint in endpoints:
        try:
            url = urljoin(BASE_URL, endpoint)
            response = requests.get(url)
            if response.status_code == 200:
                print(f"✅ {endpoint} - OK (200)")
            else:
                print(f"❌ {endpoint} - Failed ({response.status_code})")
                all_passed = False
        except Exception as e:
            print(f"❌ {endpoint} - Error: {e}")
            all_passed = False
    
    return all_passed

def test_credential_issuance():
    """Test credential issuance functionality."""
    print_header("Testing Credential Issuance")
    
    # Generate a test user ID
    user_id = f"test-{uuid.uuid4().hex[:8]}"
    
    # Try to get a credential for this user
    try:
        url = urljoin(BASE_URL, f"/api/credential/{user_id}")
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"❌ Failed to issue credential: {response.status_code}")
            return False
        
        credential = response.json()
        if "id" in credential and "proof" in credential:
            print(f"✅ Credential issued successfully for user: {user_id}")
            print(f"  - Credential ID: {credential.get('id')}")
            return credential
        else:
            print("❌ Invalid credential format")
            return False
    except Exception as e:
        print(f"❌ Error during credential issuance: {e}")
        return False

def test_credential_verification(credential):
    """Test credential verification functionality."""
    print_header("Testing Credential Verification")
    
    if not credential:
        print("❌ No credential to verify")
        return False
    
    try:
        url = urljoin(BASE_URL, "/api/verify")
        response = requests.post(url, json={"credential": credential})
        
        if response.status_code != 200:
            print(f"❌ Failed to verify credential: {response.status_code}")
            return False
        
        result = response.json()
        if result.get("valid"):
            print("✅ Credential verified successfully")
            return True
        else:
            print(f"❌ Credential verification failed: {result.get('reason')}")
            return False
    except Exception as e:
        print(f"❌ Error during credential verification: {e}")
        return False

def test_presentation_creation(credential):
    """Test presentation creation functionality."""
    print_header("Testing Presentation Creation")
    
    if not credential:
        print("❌ No credential for presentation")
        return False
    
    try:
        # Generate a random challenge
        challenge = uuid.uuid4().hex
        
        url = urljoin(BASE_URL, "/api/presentation")
        response = requests.post(
            url, 
            json={"credential": credential, "challenge": challenge}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to create presentation: {response.status_code}")
            return False
        
        presentation = response.json()
        if "proof" in presentation and "challenge" in presentation:
            print("✅ Presentation created successfully")
            return presentation, challenge
        else:
            print("❌ Invalid presentation format")
            return False
    except Exception as e:
        print(f"❌ Error during presentation creation: {e}")
        return False

def test_presentation_verification(presentation_data):
    """Test presentation verification functionality."""
    print_header("Testing Presentation Verification")
    
    if not presentation_data:
        print("❌ No presentation to verify")
        return False
    
    presentation, challenge = presentation_data
    
    try:
        url = urljoin(BASE_URL, "/api/verify-presentation")
        response = requests.post(
            url, 
            json={"presentation": presentation, "challenge": challenge}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to verify presentation: {response.status_code}")
            return False
        
        result = response.json()
        if result.get("valid"):
            print("✅ Presentation verified successfully")
            return True
        else:
            print(f"❌ Presentation verification failed: {result.get('reason')}")
            return False
    except Exception as e:
        print(f"❌ Error during presentation verification: {e}")
        return False

def test_human_verification(presentation_data):
    """Test human verification endpoint."""
    print_header("Testing Human Verification")
    
    if not presentation_data:
        print("❌ No presentation for human verification")
        return False
    
    presentation, challenge = presentation_data
    
    try:
        url = urljoin(BASE_URL, "/api/verify-human")
        response = requests.post(
            url, 
            json={"presentation": presentation, "challenge": challenge}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed human verification: {response.status_code}")
            return False
        
        result = response.json()
        if result.get("success"):
            print("✅ Human verification successful")
            print(f"  - Redirect URL: {result.get('redirect')}")
            return True
        else:
            print(f"❌ Human verification failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Error during human verification: {e}")
        return False

def test_twilio_integration():
    """Test Twilio SMS integration if credentials are available."""
    print_header("Testing Twilio SMS Integration")
    
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    phone_number = os.environ.get("TWILIO_PHONE_NUMBER")
    
    if not account_sid or not auth_token or not phone_number:
        print("⚠️ Twilio credentials not set. Skipping SMS test.")
        print("To test SMS functionality, set the following environment variables:")
        print("  - TWILIO_ACCOUNT_SID")
        print("  - TWILIO_AUTH_TOKEN")
        print("  - TWILIO_PHONE_NUMBER")
        return None
    
    # If we have a test phone number, run the SMS test
    test_phone = input("Enter a phone number to test SMS (or press Enter to skip): ").strip()
    if not test_phone:
        print("⚠️ No test phone number provided. Skipping SMS test.")
        return None
    
    print(f"Testing SMS to: {test_phone}")
    success, output = run_command(f"python test_sms.py {test_phone}")
    
    if success and "Test SMS sent successfully" in output:
        print("✅ SMS test passed")
        return True
    else:
        print("❌ SMS test failed")
        print(output)
        return False

def main():
    """Main function to run all tests."""
    print_header("LEMMA ENTERPRISE COMPREHENSIVE TEST SUITE")
    print(f"Starting tests at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Set up test environment
    test_env.setup_test_environment()
    
    # Track test results
    test_results = {}
    
    # Test dependencies
    test_results["dependencies"] = test_dependencies()
    
    # Run unit tests
    test_results["unit_tests"] = test_unit_tests()
    
    # Start the server
    server_process = start_server()
    if not server_process:
        print("❌ Cannot proceed with API tests without a running server")
        return
    
    try:
        # Give the server a moment to fully initialize
        time.sleep(2)
        
        # Test API endpoints
        test_results["api_endpoints"] = test_api_endpoints()
        
        # Test credential issuance
        credential = test_credential_issuance()
        test_results["credential_issuance"] = bool(credential)
        
        # Test credential verification
        test_results["credential_verification"] = test_credential_verification(credential)
        
        # Test presentation creation
        presentation_data = test_presentation_creation(credential)
        test_results["presentation_creation"] = bool(presentation_data)
        
        # Test presentation verification
        test_results["presentation_verification"] = test_presentation_verification(presentation_data)
        
        # Test human verification
        test_results["human_verification"] = test_human_verification(presentation_data)
        
        # Test Twilio integration
        test_results["twilio_integration"] = test_twilio_integration()
        
    finally:
        # Stop the server
        stop_server(server_process)
    
    # Print summary
    print_header("TEST SUMMARY")
    
    all_passed = True
    for test_name, result in test_results.items():
        if result is None:
            status = "⚠️ SKIPPED"
        elif result:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
            all_passed = False
        
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Your system is ready for deployment.")
        print("\nTo deploy to Azure, run: python deploy_to_azure.py")
    else:
        print("\n⚠️ SOME TESTS FAILED. Please fix the issues before deploying.")
    
    return all_passed

if __name__ == "__main__":
    main()
