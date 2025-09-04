#!/usr/bin/env python3
"""
Test script for Mailgun HTTP API email sending
"""

import sys
import os

# Add the current directory to Python path so we can import from api
sys.path.insert(0, '.')

from api.mailgun_email_sender import test_mailgun_configuration, send_test_permission_email_via_mailgun
import secrets

def main():
    print("🔍 Testing Mailgun HTTP API configuration...")
    
    # Test basic configuration
    result = test_mailgun_configuration()
    
    if result['success']:
        print("✅ Mailgun API test email sent successfully!")
        print(f"📧 Message ID: {result.get('message_id', 'N/A')}")
    else:
        print(f"❌ Mailgun API test failed: {result['error']}")
        print(f"Config: {result.get('config', {})}")
        return False
    
    print("\n🧪 Testing permission lemma email...")
    
    # Test permission lemma email
    test_email = "jedmckenna@lemma.id"
    test_token = f"test_{secrets.token_urlsafe(16)}"
    
    success = send_test_permission_email_via_mailgun(test_email, test_token)
    
    if success:
        print("✅ Test permission lemma email sent successfully!")
        print(f"📧 Email sent to: {test_email}")
        print(f"🔗 Confirmation URL: https://lemma.id/confirm-test-permission/{test_token}")
        return True
    else:
        print("❌ Test permission lemma email failed to send")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n🎉 Mailgun HTTP API is working correctly!")
    else:
        print("\n💥 Mailgun HTTP API has issues that need to be fixed.")
