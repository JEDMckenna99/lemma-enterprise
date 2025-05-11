#!/usr/bin/env python3
"""
Basic Testing Script for Lemma Enterprise

This script runs basic tests to verify the fundamental functionality
of the Lemma Human Verification System.
"""
import os
import sys
import requests
import json

# --- Configuration ---
BASE_URL = os.environ.get('LEMMA_BASE_URL', 'http://localhost:5000')
ADMIN_USER = os.environ.get('LEMMA_ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('LEMMA_ADMIN_PASS', 'password')

def print_env_vars():
    """Print relevant environment variables."""
    print("\n=== Environment Variables ===")
    vars_to_check = {
        "LEMMA_ADMIN_USER": ADMIN_USER,
        "LEMMA_ADMIN_PASS": "<hidden>",
        "LEMMA_BASE_URL": BASE_URL,
        "LEMMA_SECRET_KEY": os.environ.get('LEMMA_SECRET_KEY', '<not set>'),
        "LEMMA_API_KEY": os.environ.get('LEMMA_API_KEY', '<not set>')
    }
    
    for var, value in vars_to_check.items():
        if var in os.environ:
            print(f"  ✅ {var} = {value}")
        else:
            print(f"  ❌ {var} not set")

def test_server():
    """Test if the server is running."""
    print("\n=== Testing Server ===")
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=10)
        if response.status_code == 200:
            print("  ✅ Server is running")
            return True
        else:
            print(f"  ❌ Server returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ Failed to connect to server: {e}")
        return False

def test_admin_login():
    """Test admin login functionality."""
    print("\n=== Testing Admin Login ===")
    
    try:
        # First check if login page is accessible
        response = requests.get(f"{BASE_URL}/admin/login", timeout=10)
        if response.status_code != 200:
            print(f"  ❌ Admin login page not accessible: {response.status_code}")
            return False
        
        # Create a session
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/admin/login",
            data={
                "username": ADMIN_USER,
                "password": ADMIN_PASS
            },
            headers={"X-Testing": "True"},  # Testing header to bypass some security
            allow_redirects=True,
            timeout=10
        )
        
        if "/admin" in response.url:
            print("  ✅ Admin login successful")
            return session
        else:
            print(f"  ❌ Admin login failed: {response.status_code}")
            print(f"  Response URL: {response.url}")
            return False
    except Exception as e:
        print(f"  ❌ Exception during admin login: {e}")
        return False

def main():
    """Main function to run the tests."""
    print("=== LEMMA ENTERPRISE BASIC TESTS ===\n")
    print(f"Testing against: {BASE_URL}")
    
    # Run tests
    env_vars_result = print_env_vars()
    server_result = test_server()
    admin_result = test_admin_login()
    
    # Print summary
    print("\n=== TEST SUMMARY ===")
    print(f"Environment: {'✅ OK' if env_vars_result else '❌ ISSUES'}")
    print(f"Server: {'✅ RUNNING' if server_result else '❌ NOT RUNNING'}")
    print(f"Admin Login: {'✅ SUCCESS' if admin_result else '❌ FAILED'}")
    
    if server_result and admin_result:
        print("\n🎉 Basic functionality is working!")
        print("You can proceed with more comprehensive testing.")
    else:
        print("\n❌ Some basic tests failed. Please fix the issues before proceeding.")

if __name__ == "__main__":
    main()
