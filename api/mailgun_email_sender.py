"""
Mailgun HTTP API Email Sender
Alternative to SMTP for more reliable email delivery
"""

import os
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class MailgunSender:
    """Mailgun HTTP API email sender"""
    
    def __init__(self):
        self.api_key = os.getenv('MAILGUN_API_KEY')
        self.domain = os.getenv('MAILGUN_DOMAIN', 'www.lemma.id')
        self.base_url = f"https://api.mailgun.net/v3/{self.domain}"
        
    def send_email(self, to_email: str, subject: str, html_content: str, 
                   from_email: Optional[str] = None) -> Dict[str, Any]:
        """
        Send email using Mailgun HTTP API
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            from_email: Sender email (optional)
            
        Returns:
            Dict with success status and details
        """
        
        if not self.api_key:
            return {
                'success': False,
                'error': 'Mailgun API key not configured'
            }
        
        if not from_email:
            from_email = f"Lemma IAM <postmaster@{self.domain}>"
        
        try:
            # Prepare the email data
            email_data = {
                'from': from_email,
                'to': to_email,
                'subject': subject,
                'html': html_content
            }
            
            # Send via Mailgun API
            response = requests.post(
                f"{self.base_url}/messages",
                auth=("api", self.api_key),
                data=email_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Email sent successfully to {to_email} via Mailgun API")
                return {
                    'success': True,
                    'message_id': result.get('id'),
                    'message': f'Email sent to {to_email}'
                }
            else:
                logger.error(f"❌ Mailgun API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f'Mailgun API error: {response.status_code}',
                    'details': response.text
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Mailgun API request failed: {e}")
            return {
                'success': False,
                'error': f'Request failed: {str(e)}'
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error sending email: {e}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }

def send_test_permission_email_via_mailgun(email: str, confirmation_token: str) -> bool:
    """
    Send test permission email using Mailgun HTTP API
    
    Args:
        email: Recipient email address
        confirmation_token: Confirmation token for the email
        
    Returns:
        True if email sent successfully, False otherwise
    """
    
    # Create confirmation link
    confirmation_url = f"https://lemma.id/confirm-test-permission/{confirmation_token}"
    
    # Email content (consistent with existing styling, no emojis per user preference)
    subject = "TEST: Permission Lemma Demo - Lemma IAM"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; }}
            .header {{ background: #f59e0b; color: white; padding: 40px 30px; text-align: center; }}
            .content {{ padding: 40px 30px; }}
            .button {{ background: #f59e0b; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600; margin: 20px 0; }}
            .footer {{ background: #f8f9fa; padding: 30px; text-align: center; color: #6c757d; font-size: 14px; }}
            .test-badge {{ background: #f59e0b; color: white; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center; }}
            .info-box {{ background: #e7f3ff; border: 1px solid #b3d7ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>TEST Permission Lemma</h1>
                <p>Demo email confirmation flow</p>
            </div>
            
            <div class="content">
                <div class="test-badge">
                    <strong>THIS IS A TEST</strong><br>
                    This is a demonstration permission lemma that won't grant real access.<br>
                    It's safe to test with and will appear in your wallet for demo purposes.
                </div>
                
                <h2>Test Permission Lemma Confirmation</h2>
                
                <p>You've requested a <strong>test permission lemma</strong> to demonstrate the Lemma IAM email confirmation flow.</p>
                
                <div class="info-box">
                    <h3>Test Lemma Details:</h3>
                    <ul>
                        <li><strong>Email:</strong> {email}</li>
                        <li><strong>Type:</strong> Test Demo Permission</li>
                        <li><strong>Site:</strong> lemma.id (test)</li>
                        <li><strong>Access Level:</strong> Demo only (no real access)</li>
                        <li><strong>Purpose:</strong> Test email flow and wallet storage</li>
                    </ul>
                </div>
                
                <div style="text-align: center;">
                    <a href="{confirmation_url}" class="button">
                        Confirm Test Permission Lemma
                    </a>
                </div>
                
                <h3>What this test demonstrates:</h3>
                <ol>
                    <li>Email confirmation flow</li>
                    <li>Permission lemma creation</li>
                    <li>Automatic wallet storage</li>
                    <li>Wallet page display</li>
                    <li>Cross-browser synchronization</li>
                </ol>
                
                <p style="font-size: 14px; color: #6c757d; margin-top: 30px;">
                    This test confirmation link will expire in 1 hour. This is a safe demo that won't affect your real permissions.
                </p>
            </div>
            
            <div class="footer">
                <p><strong>Lemma IAM Test System</strong></p>
                <p>Testing email confirmation and wallet integration</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Send email using Mailgun API
    sender = MailgunSender()
    result = sender.send_email(
        to_email=email,
        subject=subject,
        html_content=html_content,
        from_email=f"Lemma IAM Test <postmaster@{sender.domain}>"
    )
    
    return result['success']

def test_mailgun_configuration() -> Dict[str, Any]:
    """
    Test Mailgun configuration and send a simple test email
    
    Returns:
        Dict with test results
    """
    
    sender = MailgunSender()
    
    # Configuration check
    config_status = {
        'api_key_set': bool(sender.api_key),
        'domain': sender.domain,
        'base_url': sender.base_url
    }
    
    if not sender.api_key:
        return {
            'success': False,
            'error': 'Mailgun API key not configured',
            'config': config_status
        }
    
    # Send test email
    test_email = "jedmckenna@lemma.id"
    test_subject = "Mailgun API Test - Lemma Platform"
    test_html = """
    <html>
    <body style="font-family: Arial, sans-serif; margin: 40px;">
        <h2>Mailgun API Test</h2>
        <p>This is a test email sent via Mailgun HTTP API to verify configuration.</p>
        <div style="background: #f0f8ff; padding: 20px; border-radius: 8px;">
            <h3>Test Details:</h3>
            <ul>
                <li>Method: Mailgun HTTP API</li>
                <li>Domain: www.lemma.id</li>
                <li>Authentication: API Key</li>
            </ul>
        </div>
        <p>If you receive this email, the Mailgun HTTP API is working correctly.</p>
    </body>
    </html>
    """
    
    result = sender.send_email(test_email, test_subject, test_html)
    result['config'] = config_status
    
    return result
