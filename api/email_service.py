"""
Email Service for Lemma Platform
Handles all email sending for IAM confirmation, notifications, etc.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def send_email(to: str, subject: str, html: str, text: Optional[str] = None) -> dict:
    """
    Send email using available email service
    
    Priority:
    1. SendGrid (if SENDGRID_API_KEY set)
    2. Mailgun (if MAILGUN_API_KEY set)
    3. SMTP (if SMTP_HOST set)
    4. Console logging (development)
    
    Returns:
        dict: {'success': bool, 'message': str, 'provider': str}
    """
    
    # Try SendGrid first
    sendgrid_key = os.getenv('SENDGRID_API_KEY')
    if sendgrid_key:
        return send_via_sendgrid(to, subject, html, text, sendgrid_key)
    
    # Try Mailgun second
    mailgun_key = os.getenv('MAILGUN_API_KEY')
    mailgun_domain = os.getenv('MAILGUN_DOMAIN', 'lemma.id')
    if mailgun_key:
        return send_via_mailgun(to, subject, html, text, mailgun_key, mailgun_domain)
    
    # Try SMTP third
    smtp_host = os.getenv('SMTP_HOST')
    if smtp_host:
        return send_via_smtp(to, subject, html, text)
    
    # Development mode: Log to console
    logger.warning("⚠️ No email service configured - logging to console")
    return send_via_console(to, subject, html, text)


def send_via_sendgrid(to: str, subject: str, html: str, text: Optional[str], api_key: str) -> dict:
    """Send email via SendGrid"""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content
        
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        
        from_email = Email(os.getenv('FROM_EMAIL', 'noreply@lemma.id'))
        to_email = To(to)
        
        # Use HTML if provided, fallback to text
        content = Content("text/html", html) if html else Content("text/plain", text or "")
        
        mail = Mail(from_email, to_email, subject, content)
        
        response = sg.client.mail.send.post(request_body=mail.get())
        
        logger.info(f"📧 Email sent via SendGrid to {to}: {subject}")
        
        return {
            'success': True,
            'message': 'Email sent via SendGrid',
            'provider': 'sendgrid',
            'status_code': response.status_code
        }
        
    except Exception as e:
        logger.error(f"❌ SendGrid email failed: {e}")
        return {
            'success': False,
            'message': f'SendGrid error: {str(e)}',
            'provider': 'sendgrid'
        }


def send_via_mailgun(to: str, subject: str, html: str, text: Optional[str], api_key: str, domain: str) -> dict:
    """Send email via Mailgun"""
    try:
        import requests
        
        response = requests.post(
            f"https://api.mailgun.net/v3/{domain}/messages",
            auth=("api", api_key),
            data={
                "from": os.getenv('FROM_EMAIL', f'Lemma <noreply@{domain}>'),
                "to": to,
                "subject": subject,
                "html": html,
                "text": text or ""
            }
        )
        
        if response.status_code == 200:
            logger.info(f"📧 Email sent via Mailgun to {to}: {subject}")
            return {
                'success': True,
                'message': 'Email sent via Mailgun',
                'provider': 'mailgun',
                'status_code': response.status_code
            }
        else:
            raise Exception(f"Mailgun returned {response.status_code}: {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Mailgun email failed: {e}")
        return {
            'success': False,
            'message': f'Mailgun error: {str(e)}',
            'provider': 'mailgun'
        }


def send_via_smtp(to: str, subject: str, html: str, text: Optional[str]) -> dict:
    """Send email via SMTP"""
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        
        smtp_host = os.getenv('SMTP_HOST')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')
        from_email = os.getenv('FROM_EMAIL', 'noreply@lemma.id')
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to
        
        if text:
            msg.attach(MIMEText(text, 'plain'))
        if html:
            msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        logger.info(f"📧 Email sent via SMTP to {to}: {subject}")
        
        return {
            'success': True,
            'message': 'Email sent via SMTP',
            'provider': 'smtp'
        }
        
    except Exception as e:
        logger.error(f"❌ SMTP email failed: {e}")
        return {
            'success': False,
            'message': f'SMTP error: {str(e)}',
            'provider': 'smtp'
        }


def send_via_console(to: str, subject: str, html: str, text: Optional[str]) -> dict:
    """Log email to console (development mode)"""
    logger.info("=" * 80)
    logger.info("📧 EMAIL (CONSOLE MODE - NO EMAIL SERVICE CONFIGURED)")
    logger.info("=" * 80)
    logger.info(f"To: {to}")
    logger.info(f"Subject: {subject}")
    logger.info("-" * 80)
    logger.info(f"HTML Body:\n{html}")
    if text:
        logger.info(f"\nText Body:\n{text}")
    logger.info("=" * 80)
    
    return {
        'success': True,
        'message': 'Email logged to console (development mode)',
        'provider': 'console'
    }


def render_email_template(template_name: str, **kwargs) -> str:
    """
    Render email template with variables
    Simple template renderer for email HTML
    """
    templates = {
        'access_confirmation': '''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }
                    .content { background: #fff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; }
                    .button { display: inline-block; background: #6366f1; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; margin: 20px 0; }
                    .button:hover { background: #4f46e5; }
                    .footer { text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }
                    .credential-box { background: #f3f4f6; border-left: 4px solid #6366f1; padding: 15px; margin: 20px 0; border-radius: 4px; }
                    .code { font-family: 'Courier New', monospace; background: #1f2937; color: #10b981; padding: 2px 6px; border-radius: 3px; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">🔐 Confirm Your Access</h1>
                </div>
                <div class="content">
                    <p>Hi there,</p>
                    <p>You've been granted <strong>{permission_level}</strong> access to <strong>{site_domain}</strong>.</p>
                    <p>Click the button below to confirm and receive your permission credential:</p>
                    <div style="text-align: center;">
                        <a href="{confirmation_link}" class="button">Confirm Access</a>
                    </div>
                    <div class="credential-box">
                        <strong>What happens next:</strong>
                        <ul style="margin: 10px 0;">
                            <li>Your permission credential will be stored in your browser wallet</li>
                            <li>You'll have instant access (verified in <span class="code">182µs</span>)</li>
                            <li>No password needed - just this one-time confirmation</li>
                        </ul>
                    </div>
                    <p style="color: #6b7280; font-size: 14px;">This link expires in 24 hours. If you didn't request this, you can safely ignore this email.</p>
                </div>
                <div class="footer">
                    <p>Powered by Lemma IAM</p>
                    <p style="font-size: 12px;">Authentication as simple as email</p>
                </div>
            </body>
            </html>
        ''',
        
        'credential_issued': '''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }
                    .content { background: #fff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; }
                    .success-box { background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0; border-radius: 4px; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">✅ Access Granted!</h1>
                </div>
                <div class="content">
                    <div class="success-box">
                        <p style="margin: 0;"><strong>Your {permission_level} credential has been issued.</strong></p>
                    </div>
                    <p>You now have access to <strong>{site_domain}</strong> with the following permissions:</p>
                    <ul>
                        {permissions_list}
                    </ul>
                    <p>Your credential has been stored in your browser wallet and will work automatically when you visit the site.</p>
                    <p><a href="{redirect_url}" style="color: #6366f1; text-decoration: none;">Return to {site_domain} →</a></p>
                </div>
                <div class="footer" style="text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px;">
                    <p>Powered by Lemma IAM</p>
                </div>
            </body>
            </html>
        ''',
        
        'beta_access_confirmation': '''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 40px; text-align: center; border-radius: 12px 12px 0 0; }
                    .badge { display: inline-block; background: rgba(255,255,255,0.2); padding: 6px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-bottom: 12px; }
                    .content { background: #fff; padding: 40px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px; }
                    .button { display: inline-block; background: #10b981; color: white !important; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 24px 0; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); }
                    .button:hover { background: #059669; }
                    .info-box { background: #ecfdf5; border-left: 4px solid #10b981; padding: 16px; margin: 24px 0; border-radius: 6px; }
                    .footer { text-align: center; margin-top: 32px; color: #6b7280; font-size: 14px; }
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="badge">FREE BETA ACCESS</div>
                    <h1 style="margin: 0; font-size: 32px;">Sign in to Lemma Platform</h1>
                    <p style="margin: 12px 0 0 0; opacity: 0.95;">Your secure access link is ready</p>
                </div>
                <div class="content">
                    <p>Hi <strong>{user_email}</strong>,</p>
                    <p>Welcome to the Lemma Platform! You've requested beta access to our developer platform.</p>
                    <p style="font-size: 16px;"><strong>Click the button below to receive your beta-user credential and access the platform:</strong></p>
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{confirmation_link}" class="button">Get My Beta Access →</a>
                    </div>
                    <div class="info-box">
                        <strong style="color: #047857;">What happens when you click:</strong>
                        <ul style="margin: 12px 0 8px 0; padding-left: 20px; color: #065f46;">
                            <li>You'll receive a cryptographic permission credential</li>
                            <li>It's stored securely in your browser wallet</li>
                            <li>Authentication happens in 182µs - instant access!</li>
                            <li>No password needed - Lemma IAM uses email-based auth</li>
                        </ul>
                    </div>
                    <p><strong>Included in FREE Beta:</strong></p>
                    <ul style="color: #374151;">
                        <li>Complete IAM system for your applications</li>
                        <li>Optional bot protection via federated identity</li>
                        <li>API access & SDK integration</li>
                        <li>Dashboard & analytics</li>
                        <li>Full documentation & support</li>
                    </ul>
                    <p style="color: #6b7280; font-size: 14px; margin-top: 32px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
                        This link expires in 24 hours. If you didn't request beta access, you can safely ignore this email.
                    </p>
                </div>
                <div class="footer">
                    <p style="font-weight: 600;">Lemma Platform</p>
                    <p style="font-size: 12px; margin-top: 8px;">Authentication as simple as email • 1,000x faster than Auth0</p>
                    <p style="font-size: 12px; color: #9ca3af; margin-top: 16px;">Powered by Lemma IAM</p>
                </div>
            </body>
            </html>
        '''
    }
    
    template = templates.get(template_name, templates['access_confirmation'])
    
    # Simple string replacement (in production, use Jinja2)
    for key, value in kwargs.items():
        template = template.replace(f'{{{key}}}', str(value))
    
    return template


