#!/usr/bin/env python3
"""
Quick test script to debug email sending issues
"""

import os
import smtplib
import email.mime.text
import email.mime.multipart

def test_smtp_connection():
    """Test SMTP connection step by step"""
    print("🔍 Testing SMTP configuration...")
    
    # Get config from environment (same as Heroku)
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.mailgun.org')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME', 'postmaster@lemma.id')
    smtp_password = os.getenv('SMTP_PASSWORD', 'd01447fec22c1f0a138ee38f63f325c0-1ae02a08-d4f38e12')
    
    print(f"SMTP Server: {smtp_server}")
    print(f"SMTP Port: {smtp_port}")
    print(f"SMTP Username: {smtp_username}")
    print(f"SMTP Password: {'SET' if smtp_password else 'NOT SET'}")
    
    try:
        print("\n📡 Step 1: Creating SMTP connection...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        print("✅ Connection successful")
        
        print("\n🔒 Step 2: Starting TLS...")
        server.starttls()
        print("✅ TLS started successfully")
        
        print("\n🔑 Step 3: Authenticating...")
        server.login(smtp_username, smtp_password)
        print("✅ Authentication successful")
        
        print("\n📧 Step 4: Sending test email...")
        test_email = "jedmckenna@lemma.id"
        
        # Create test message
        msg = email.mime.multipart.MIMEMultipart('alternative')
        msg['Subject'] = "SMTP Test - Lemma Platform Debug"
        msg['From'] = f"Lemma IAM Test <{smtp_username}>"
        msg['To'] = test_email
        
        # Simple text content
        text_content = "This is a simple test email to verify SMTP configuration is working. SMTP Server: smtp.mailgun.org, Port: 587, Authentication: Successful"
        
        text_part = email.mime.text.MIMEText(text_content, 'plain')
        msg.attach(text_part)
        
        # Send the message
        server.send_message(msg)
        server.quit()
        
        print("✅ Test email sent successfully!")
        print(f"📧 Email sent to: {test_email}")
        return True
        
    except Exception as e:
        print(f"❌ SMTP test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_smtp_connection()
    if success:
        print("\n🎉 SMTP configuration is working correctly!")
    else:
        print("\n💥 SMTP configuration has issues that need to be fixed.")
