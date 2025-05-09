#!/usr/bin/env python3
"""
Lemma Verification SMS Sender

This script sends a verification SMS with a link to join your verified human network.
"""
import os
import sys
import uuid
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Twilio credentials from environment variables
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

# Base URL for your application
BASE_URL = os.environ.get('BASE_URL', 'https://localhost:5000')

def send_verification_sms(to_number, user_id=None):
    """Send a verification SMS with a link to join the network."""
    print("=== Sending Lemma Verification SMS ===")
    
    # Generate a user ID if not provided
    if not user_id:
        user_id = f"user-{uuid.uuid4().hex[:8]}"
    
    # Create verification link
    verification_link = f"{BASE_URL}/verify?user={user_id}"
    
    # Compose message
    message_body = f"You have been invited to join the Verified Human Network. Click this link to verify your humanity: {verification_link}"
    
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Send message
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        
        print(f"✅ Verification SMS sent successfully!")
        print(f"  - Message SID: {message.sid}")
        print(f"  - Status: {message.status}")
        print(f"  - From: {message.from_}")
        print(f"  - To: {message.to}")
        print(f"\n📱 Verification link: {verification_link}")
        print(f"👤 User ID: {user_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        return False

def main():
    """Main function to send a verification SMS."""
    print("=== LEMMA VERIFICATION SMS SENDER ===\n")
    
    # Check for Twilio credentials
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("❌ Twilio credentials not found in .env file")
        return False
    
    # Get phone number for sending verification
    if len(sys.argv) < 2:
        print("\nUsage: python send_verification.py <phone_number> [user_id]")
        print("Example: python send_verification.py +12345678901 john_doe")
        
        # Ask for phone number interactively
        to_number = input("\nEnter the recipient's phone number (e.g., +12345678901): ").strip()
        if not to_number:
            print("No phone number provided. Exiting.")
            return False
        
        # Optionally ask for user ID
        user_id = input("Enter a user ID (optional, press Enter to generate one): ").strip() or None
    else:
        to_number = sys.argv[1]
        user_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Make sure the recipient number is different from the Twilio number
    if to_number == TWILIO_PHONE_NUMBER:
        print(f"❌ Error: The recipient number ({to_number}) cannot be the same as your Twilio number.")
        print("Please enter a different phone number.")
        return False
    
    # Send verification SMS
    send_verification_sms(to_number, user_id)
    
    return True

if __name__ == "__main__":
    main()
