#!/usr/bin/env python3
"""
Test script for Lemma Enterprise CSRF token handling.

This script tests the /api/issue-credential endpoint with a CSRF token
to diagnose CSRF validation issues.
"""
import os
import time
import requests
import json
from flask import Flask
from flask_wtf.csrf import generate_csrf

def main():
    """Test CSRF token handling in Lemma Enterprise."""
    print("Testing CSRF token handling...")
    
    # Create a Flask app to generate a valid CSRF token
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test_secret_key_for_csrf'
    app.config['WTF_CSRF_ENABLED'] = True
    
    # Generate a CSRF token
    with app.test_request_context():
        local_csrf_token = generate_csrf()
        print(f"Generated local CSRF token: {local_csrf_token[:10]}...")
    
    # Get the API key from environment or use a default
    api_key = os.environ.get('LEMMA_API_KEY', 'test_api_key')
    
    # Base URL for API
    base_url = "http://localhost:5000"  # Default to localhost
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # First, get a session by visiting the home page
    print("Establishing session by visiting home page...")
    try:
        home_response = session.get(f"{base_url}/")
        print(f"Home page status: {home_response.status_code}")
        
        # Print all cookies from the session
        print("Session cookies after visiting home page:")
        for cookie_name, cookie_value in session.cookies.items():
            print(f"  {cookie_name}: {cookie_value[:10]}..." if len(str(cookie_value)) > 10 else f"  {cookie_name}: {cookie_value}")
        
        # Now try to get a CSRF token from the API endpoint
        print("\nGetting CSRF token from API...")
        csrf_response = session.get(f"{base_url}/api/generate-csrf-token")
        
        if csrf_response.status_code == 200:
            try:
                csrf_data = csrf_response.json()
                server_csrf_token = csrf_data.get('csrf_token')
                if server_csrf_token:
                    print(f"Server CSRF token from API: {server_csrf_token[:10]}...")
                    csrf_token = server_csrf_token
                else:
                    print("No CSRF token found in API response")
                    csrf_token = local_csrf_token
            except json.JSONDecodeError:
                print("Invalid JSON response from CSRF token endpoint")
                csrf_token = local_csrf_token
        else:
            print(f"Failed to get CSRF token from API: {csrf_response.status_code}")
            csrf_token = local_csrf_token
            
        # If we still don't have a token from the server, check cookies
        if csrf_token == local_csrf_token:
            print("\nChecking for CSRF token in cookies...")
            for cookie_name, cookie_value in session.cookies.items():
                if '_csrf_token' in cookie_name:
                    print(f"Found CSRF token in cookies: {cookie_name} = {cookie_value[:10]}...")
                    csrf_token = cookie_value
                    break
    except Exception as e:
        print(f"Error establishing session: {e}")
        csrf_token = local_csrf_token
    
    # Test endpoint
    url = f"{base_url}/api/issue-credential"
    
    # Generate test user ID
    user_id = f"test_user_{int(time.time())}"
    
    # Request payload
    payload = {
        'user_id': user_id
    }
    
    # Headers with API key and CSRF token
    headers = {
        'X-API-Key': api_key,
        'X-CSRFToken': csrf_token,
        'Content-Type': 'application/json'
    }
    
    # Make the request
    print(f"\nMaking request to {url}...")
    print(f"User ID: {user_id}")
    print(f"Headers: {headers}")
    print(f"Current cookies: {dict(session.cookies.items())}")
    
    try:
        # Use the session to make the request
        response = session.post(url, json=payload, headers=headers)
        
        # Print response
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Request succeeded!")
            data = response.json()
            credential = data.get('credential')
            if credential:
                print(f"Credential ID: {credential.get('id')}")
        else:
            print("❌ Request failed!")
    except Exception as e:
        print(f"Error making request: {e}")

if __name__ == "__main__":
    main() 