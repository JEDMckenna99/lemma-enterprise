#!/usr/bin/env python3
"""
Environment Setup for Lemma Enterprise Testing

This script sets up the necessary environment variables for testing the Lemma system.
"""
import os
import sys
import subprocess

def setup_test_environment():
    """Set up environment variables for testing."""
    env_vars = {
        # Admin credentials
        "LEMMA_ADMIN_USER": "admin",
        "LEMMA_ADMIN_PASS": "password",
        "LEMMA_SECRET_KEY": "test-secret-key-for-development-only",
        
        # Flask settings
        "FLASK_DEBUG": "True",
        "FLASK_APP": "app.py",
        
        # Twilio settings (these will be empty by default)
        "TWILIO_ACCOUNT_SID": "",
        "TWILIO_AUTH_TOKEN": "",
        "TWILIO_PHONE_NUMBER": "",
    }
    
    # Set environment variables
    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"Set {key}={value}")
    
    return env_vars

def main():
    """Main function to set up the test environment."""
    print("=== Setting Up Test Environment ===")
    
    # Set up environment variables
    env_vars = setup_test_environment()
    
    # Ask for Twilio credentials if needed
    if not env_vars["TWILIO_ACCOUNT_SID"] or not env_vars["TWILIO_AUTH_TOKEN"]:
        print("\n📱 Would you like to set up Twilio for SMS testing?")
        setup_twilio = input("Enter 'y' to set up Twilio, any other key to skip: ").strip().lower() == 'y'
        
        if setup_twilio:
            account_sid = input("Twilio Account SID: ").strip()
            auth_token = input("Twilio Auth Token: ").strip()
            phone_number = input("Twilio Phone Number: ").strip()
            
            os.environ["TWILIO_ACCOUNT_SID"] = account_sid
            os.environ["TWILIO_AUTH_TOKEN"] = auth_token
            os.environ["TWILIO_PHONE_NUMBER"] = phone_number
            
            print("Twilio credentials set up successfully!")
    
    print("\n✅ Test environment set up successfully!")
    print("You can now run the tests with the configured environment.")

if __name__ == "__main__":
    main()
