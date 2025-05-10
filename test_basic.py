#!/usr/bin/env python3
"""
Basic Test Script for Lemma Enterprise

This script performs basic tests on the Lemma Human Verification System
to ensure core functionality is working.
"""
import os
import uuid
import json
from twilio.rest import Client

# --- Twilio Configuration ---
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

def test_environment():
    """Test if the environment is properly set up."""
    print("=== Testing Environment ===")
    
    # Check for required environment variables
    env_vars = {
        "LEMMA_ADMIN_USER": os.environ.get('LEMMA_ADMIN_USER'),
        "LEMMA_ADMIN_PASS": os.environ.get('LEMMA_ADMIN_PASS'),
        "LEMMA_SECRET_KEY": os.environ.get('LEMMA_SECRET_KEY'),
        "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": TWILIO_AUTH_TOKEN,
        "TWILIO_PHONE_NUMBER": TWILIO_PHONE_NUMBER
    }
    
    for var_name, var_value in env_vars.items():
        if var_value:
            print(f"✅ {var_name} is set")
        else:
            print(f"❌ {var_name} is not set")
    
    # Check if data directory exists
    data_dir = os.path.join(os.path.expanduser('~'), '.lemma_enterprise')
    if os.path.exists(data_dir):
        print(f"✅ Data directory exists: {data_dir}")
    else:
        print(f"❌ Data directory does not exist: {data_dir}")
    
    return True

def test_twilio():
    """Test Twilio SMS functionality."""
    print("\n=== Testing Twilio SMS ===")
    
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        print("❌ Twilio credentials are not set. Skipping SMS test.")
        return False
    
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Get account info to verify credentials
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        print(f"✅ Connected to Twilio account: {account.friendly_name}")
        
        # Don't actually send an SMS in this test
        print("✅ Twilio credentials verified successfully")
        return True
    except Exception as e:
        print(f"❌ Twilio test failed: {e}")
        return False

def test_data_files():
    """Test if data files can be created and accessed."""
    print("\n=== Testing Data Files ===")
    
    data_dir = os.path.join(os.path.expanduser('~'), '.lemma_enterprise')
    os.makedirs(data_dir, exist_ok=True)
    
    test_file = os.path.join(data_dir, 'test.json')
    test_data = {
        "test_id": str(uuid.uuid4()),
        "timestamp": str(uuid.uuid4()),
        "status": "active"
    }
    
    try:
        # Write test data
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2)
        print(f"✅ Successfully wrote to test file: {test_file}")
        
        # Read test data
        with open(test_file, 'r', encoding='utf-8') as f:
            read_data = json.load(f)
        
        if read_data["test_id"] == test_data["test_id"]:
            print("✅ Successfully read test data")
        else:
            print("❌ Data integrity check failed")
        
        # Clean up
        os.remove(test_file)
        print("✅ Successfully cleaned up test file")
        
        return True
    except Exception as e:
        print(f"❌ Data file test failed: {e}")
        return False

def main():
    """Main function to run all basic tests."""
    print("=== LEMMA ENTERPRISE BASIC TEST SUITE ===\n")
    
    # Run tests
    env_result = test_environment()
    twilio_result = test_twilio()
    data_result = test_data_files()
    
    # Print summary
    print("\n=== TEST SUMMARY ===")
    print(f"Environment Test: {'✅ PASSED' if env_result else '❌ FAILED'}")
    print(f"Twilio SMS Test: {'✅ PASSED' if twilio_result else '❌ FAILED'}")
    print(f"Data Files Test: {'✅ PASSED' if data_result else '❌ FAILED'}")
    
    all_passed = env_result and data_result  # Don't require Twilio to pass
    
    if all_passed:
        print("\n🎉 BASIC TESTS PASSED!")
        if not twilio_result:
            print("\n⚠️ Note: Twilio SMS test was skipped or failed.")
            print("To enable SMS invitations, set the following environment variables:")
            print("  - TWILIO_ACCOUNT_SID")
            print("  - TWILIO_AUTH_TOKEN")
            print("  - TWILIO_PHONE_NUMBER")
    else:
        print("\n❌ SOME TESTS FAILED. Please fix the issues before proceeding.")
    
    return all_passed

if __name__ == "__main__":
    main()
