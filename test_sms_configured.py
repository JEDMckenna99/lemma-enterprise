#!/usr/bin/env python3
"""
SMS Testing Script for Lemma Enterprise with Configured Credentials

This script tests the SMS functionality using the configured Twilio credentials.
"""
import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Twilio credentials from environment variables
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

def test_twilio_connection():
    """Test connection to Twilio API."""
    print("=== Testing Twilio Connection ===")
    
    if not TWILIO_ACCOUNT_SID:
        print("❌ TWILIO_ACCOUNT_SID is not set or not loaded from .env file")
        return False
    
    if not TWILIO_AUTH_TOKEN:
        print("❌ TWILIO_AUTH_TOKEN is not set or not loaded from .env file")
        return False
    
    if not TWILIO_PHONE_NUMBER:
        print("❌ TWILIO_PHONE_NUMBER is not set or not loaded from .env file")
        return False
    
    print(f"✅ Twilio credentials found:")
    print(f"  - Account SID: {TWILIO_ACCOUNT_SID[:5]}...{TWILIO_ACCOUNT_SID[-5:]}")
    print(f"  - Auth Token: {TWILIO_AUTH_TOKEN[:2]}...{TWILIO_AUTH_TOKEN[-2:]}")
    print(f"  - Phone Number: {TWILIO_PHONE_NUMBER}")
    
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Get account info to verify credentials
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        print(f"✅ Successfully connected to Twilio account: {account.friendly_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Twilio: {e}")
        return False

def send_test_sms(to_number):
    """Send a test SMS message."""
    print("\n=== Sending Test SMS ===")
    
    if not to_number:
        print("❌ No phone number provided")
        return False
    
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Compose message
        message_body = "This is a test message from your Lemma Human Verification System. Your verification link would appear here."
        
        # Send message
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        
        print(f"✅ Test SMS sent successfully!")
        print(f"  - Message SID: {message.sid}")
        print(f"  - Status: {message.status}")
        print(f"  - From: {message.from_}")
        print(f"  - To: {message.to}")
        return True
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        return False

def main():
    """Main function to run the SMS test."""
    print("=== LEMMA ENTERPRISE SMS TESTING ===\n")
    
    # Test Twilio connection
    if not test_twilio_connection():
        print("\n❌ Twilio connection failed. Please check your credentials.")
        return False
    
    # Get phone number for testing
    if len(sys.argv) < 2:
        print("\nUsage: python test_sms_configured.py <phone_number>")
        print("Example: python test_sms_configured.py +12345678901")
        
        # Ask for phone number interactively
        to_number = input("\nEnter a phone number to send a test SMS (e.g., +12345678901): ").strip()
        if not to_number:
            print("No phone number provided. Exiting.")
            return False
    else:
        to_number = sys.argv[1]
    
    # Send test SMS
    sms_result = send_test_sms(to_number)
    
    # Print summary
    print("\n=== TEST SUMMARY ===")
    print(f"Twilio Connection: ✅ PASSED")
    print(f"SMS Sending: {'✅ PASSED' if sms_result else '❌ FAILED'}")
    
    if sms_result:
        print("\n🎉 SMS TEST PASSED!")
        print("\nYour verified human network is configured correctly for SMS invitations.")
        print("You can now proceed with testing the full invitation workflow or deploy your system.")
    else:
        print("\n❌ SMS TEST FAILED. Please check the error messages above.")
    
    return sms_result

if __name__ == "__main__":
    main()
