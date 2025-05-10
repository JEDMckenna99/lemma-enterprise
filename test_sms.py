#!/usr/bin/env python3
"""
SMS Testing Script for Lemma Enterprise

This script tests the SMS invitation functionality for the Lemma Human Verification System.
"""
import os
import sys
from twilio.rest import Client

# --- Twilio Configuration ---
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

def test_twilio_credentials():
    """Test if Twilio credentials are properly configured."""
    if not TWILIO_ACCOUNT_SID:
        print("❌ TWILIO_ACCOUNT_SID is not set. Please set this environment variable.")
        return False
    
    if not TWILIO_AUTH_TOKEN:
        print("❌ TWILIO_AUTH_TOKEN is not set. Please set this environment variable.")
        return False
    
    if not TWILIO_PHONE_NUMBER:
        print("❌ TWILIO_PHONE_NUMBER is not set. Please set this environment variable.")
        return False
    
    print("✅ Twilio credentials are configured.")
    return True

def send_test_sms(to_number):
    """Send a test SMS message."""
    if not test_twilio_credentials():
        return False
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body="This is a test message from Lemma Human Verification System. Your verification link would appear here.",
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        print(f"✅ Test SMS sent successfully! Message SID: {message.sid}")
        return True
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        return False

def main():
    """Main function to run the SMS test."""
    print("=== Lemma Enterprise SMS Testing ===")
    
    if len(sys.argv) < 2:
        print("Usage: python test_sms.py <phone_number>")
        print("Example: python test_sms.py +12345678901")
        return
    
    phone_number = sys.argv[1]
    print(f"Testing SMS functionality with phone number: {phone_number}")
    
    send_test_sms(phone_number)

if __name__ == "__main__":
    main()
