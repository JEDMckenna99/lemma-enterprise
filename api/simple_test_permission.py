"""
Simple Test Permission System
Creates test permission lemmas without database dependencies
"""

from flask import Blueprint, request, jsonify, render_template_string
from flask_cors import cross_origin
from datetime import datetime, timedelta
import secrets
import logging
import os
import json

logger = logging.getLogger(__name__)

simple_test_bp = Blueprint('simple_test', __name__)

# Simple in-memory storage for test confirmations
test_confirmations = {}

def send_test_email(email, confirmation_token):
    """Send test permission confirmation email"""
    try:
        # Email configuration (using Mailgun)
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.mailgun.org')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME', '')
        smtp_password = os.getenv('SMTP_PASSWORD', '')
        
        if not smtp_username or not smtp_password:
            logger.error("SMTP credentials not configured")
            return False
        
        # Create confirmation link
        confirmation_url = f"https://lemma.id/confirm-test-permission/{confirmation_token}"
        
        # Email content (consistent styling, no emojis)
        subject = f"TEST: Permission Lemma Demo - Lemma IAM"
        
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
        
        # Create and send email
        from email.mime.text import MimeText
        from email.mime.multipart import MimeMultipart
        import smtplib
        
        msg = MimeMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Lemma IAM Test <{smtp_username}>"
        msg['To'] = email
        
        html_part = MimeText(html_content, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        logger.info(f"✅ Test permission email sent to {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send test email to {email}: {e}")
        return False

@simple_test_bp.route('/api/admin/send-test-permission-email', methods=['POST'])
@cross_origin()
def send_test_permission_email():
    """Send test permission email (simplified version)"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        admin_password = data.get('admin_password', '')
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Verify admin password
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', '.511MeV/c^2')
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        logger.info(f"🧪 Test permission email requested for: {email}")
        
        # Generate test confirmation token
        confirmation_token = f"test_{secrets.token_urlsafe(32)}"
        
        # Store test confirmation
        test_confirmations[confirmation_token] = {
            'email': email,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=1),
            'confirmed': False
        }
        
        # Send actual email using Mailgun SMTP
        try:
            email_sent = send_test_email(email, confirmation_token)
            
            if email_sent:
                return jsonify({
                    'success': True,
                    'message': f'Test permission email sent to {email}',
                    'confirmation_token': confirmation_token,
                    'confirmation_url': f'https://lemma.id/confirm-test-permission/{confirmation_token}',
                    'expires_in': '1 hour',
                    'note': 'Check your email for the test confirmation link'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to send email - check SMTP configuration'
                }), 500
                
        except Exception as email_error:
            logger.error(f"Email sending failed: {email_error}")
            return jsonify({
                'success': True,
                'message': f'Test permission email prepared for {email} (email failed)',
                'confirmation_token': confirmation_token,
                'confirmation_url': f'https://lemma.id/confirm-test-permission/{confirmation_token}',
                'expires_in': '1 hour',
                'note': f'Email failed to send: {str(email_error)}. Use confirmation URL directly.'
            })
        
    except Exception as e:
        logger.error(f"❌ Test permission email error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@simple_test_bp.route('/confirm-test-permission/<confirmation_token>')
def confirm_test_permission(confirmation_token):
    """Confirm test permission and create demo lemma"""
    try:
        # Check if token exists
        if confirmation_token not in test_confirmations:
            return render_template_string("""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Invalid Test Confirmation Link</h1>
                    <p>This test confirmation link is invalid or has expired.</p>
                    <p><a href="https://lemma.id/admin/permissions">Back to Permission Manager</a></p>
                </body></html>
            """), 404
        
        confirmation = test_confirmations[confirmation_token]
        
        # Check if expired
        if datetime.utcnow() > confirmation['expires_at']:
            del test_confirmations[confirmation_token]
            return render_template_string("""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Test Confirmation Link Expired</h1>
                    <p>This test confirmation link has expired. Please send a new test email.</p>
                    <p><a href="https://lemma.id/admin/permissions">Back to Permission Manager</a></p>
                </body></html>
            """), 410
        
        email = confirmation['email']
        
        # Create test permission lemma
        import time
        current_time = int(time.time())
        
        test_permission_lemma = {
            'id': f"test_perm_{secrets.token_hex(16)}",
            'issuer': 'did:lemma:test:lemma.id',
            'subject': f'did:lemma:test-user:{email.replace("@", "_at_").replace(".", "_")}',
            'packageType': 'permission',
            'issued_at': current_time,
            'expires_at': current_time + (7 * 24 * 60 * 60),  # 7 days
            'claims': {
                'packageType': 'permission',
                'siteId': 'lemma.id',
                'siteDomain': 'lemma.id',
                'permissionId': 'test_demo_access',
                'accountType': 'test_user',
                'email': email,
                'scope': ['test:read', 'demo:view'],
                'grantedBy': 'did:lemma:test:system',
                'grantedAt': current_time,
                'networkShared': False,
                'testPermission': True,
                'realAccess': False,
                'purpose': 'email_flow_testing'
            },
            'proof': {
                'type': 'Ed25519Signature2020',
                'created': current_time,
                'verificationMethod': 'did:lemma:test:lemma.id',
                'signatureValue': f'test_sig_{secrets.token_hex(32)}'
            }
        }
        
        # Mark as confirmed
        confirmation['confirmed'] = True
        confirmation['lemma_id'] = test_permission_lemma['id']
        
        # Success page with consistent styling (no gradients, no emojis)
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Permission Confirmed</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://lemma.id/static/css/lemma.css">
            <style>
                .test-container {{
                    max-width: 700px;
                    margin: 40px auto;
                    padding: 0 20px;
                }}
                .test-badge {{
                    background: var(--warning);
                    color: var(--white);
                    padding: 16px;
                    border-radius: 8px;
                    margin: 20px 0;
                    text-align: center;
                }}
                .success-card {{
                    background: var(--white);
                    border: 1px solid var(--gray-200);
                    border-radius: 12px;
                    padding: 32px;
                    margin: 20px 0;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                }}
                .lemma-data {{
                    background: var(--gray-100);
                    border: 1px solid var(--gray-200);
                    border-radius: 8px;
                    padding: 20px;
                    font-family: var(--font-mono);
                    font-size: 12px;
                    overflow-x: auto;
                    margin: 20px 0;
                }}
            </style>
            <script src="https://lemma.id/static/js/lemma-federated-wallet.js?v=672"></script>
            <script src="https://lemma.id/static/js/lemma-wallet-manager.js"></script>
        </head>
        <body>
            <div class="test-container">
                <div class="test-badge">
                    <h2 style="margin: 0; color: var(--white);">TEST MODE</h2>
                    <p style="margin: 8px 0 0 0; color: var(--white);">This is a safe test that won't grant real access</p>
                </div>
                
                <div class="success-card">
                    <h1 style="color: var(--gray-900); margin-bottom: 16px;">Test Permission Confirmed</h1>
                    
                    <div style="background: var(--success); color: var(--white); padding: 16px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin: 0 0 8px 0; color: var(--white);">Test Successfully Created</h3>
                        <ul style="margin: 8px 0 0 20px; color: var(--white);">
                            <li>Email: {email}</li>
                            <li>Permission: Test Demo Access</li>
                            <li>Type: test_demo_access</li>
                            <li>Expires: 7 days</li>
                            <li>Real Access: No (safe for testing)</li>
                        </ul>
                    </div>
                    
                    <h3 style="color: var(--gray-900);">Test Permission Data</h3>
                    <div class="lemma-data">
{json.dumps(test_permission_lemma, indent=2)}
                    </div>
                    
                    <h3 style="color: var(--gray-900);">What was tested</h3>
                    <ol style="color: var(--gray-700);">
                        <li>Email confirmation flow</li>
                        <li>Permission lemma creation</li>
                        <li>Wallet storage integration</li>
                        <li>Cross-browser synchronization</li>
                    </ol>
                    
                    <div style="text-align: center; margin: 40px 0;">
                        <a href="https://lemma.id/wallet" class="btn btn-primary" style="margin: 0 8px;">
                            Check Your Wallet
                        </a>
                        <a href="https://lemma.id/admin/permissions" class="btn btn-secondary" style="margin: 0 8px;">
                            Back to Permission Manager
                        </a>
                    </div>
                </div>
            </div>
            
            <script>
                // Test wallet integration using centralized manager
                document.addEventListener('DOMContentLoaded', async function() {{
                    try {{
                        console.log('Test: Using LemmaWalletManager for test permission storage...');
                        
                        const testLemmaData = {json.dumps(test_permission_lemma)};
                        
                        console.log('Test permission to store:', {{
                            id: testLemmaData.id,
                            siteId: testLemmaData.claims?.siteId,
                            email: testLemmaData.claims?.email,
                            permissionId: testLemmaData.claims?.permissionId,
                            testPermission: testLemmaData.claims?.testPermission
                        }});
                        
                        // Store test permission using centralized manager
                        const result = await window.storeLemmaCredential(testLemmaData, {{
                            allowDuplicates: false
                        }});
                        
                        if (result.success) {{
                            if (result.duplicate) {{
                                console.log('Test permission already exists in wallet');
                                showMessage('Test permission already in your wallet', var(--primary));
                            }} else {{
                                console.log('Test permission stored in unified wallet');
                                showMessage('Test permission stored successfully', var(--success));
                            }}
                        }} else {{
                            console.warn('Failed to store test permission:', result.error);
                            showMessage('Storage failed: ' + result.error, var(--error));
                        }}
                        
                    }} catch (error) {{
                        console.error('Test wallet error:', error);
                        showMessage('Wallet error: ' + error.message, var(--error));
                    }}
                }});
                
                function showMessage(message, color) {{
                    const msg = document.createElement('div');
                    msg.style.cssText = `position: fixed; top: 20px; right: 20px; background: ${{color}}; color: var(--white); padding: 16px 20px; border-radius: 8px; z-index: 1000; box-shadow: 0 4px 12px rgba(0,0,0,0.2);`;
                    msg.textContent = message;
                    document.body.appendChild(msg);
                    
                    setTimeout(() => {{
                        if (document.body.contains(msg)) {{
                            document.body.removeChild(msg);
                        }}
                    }}, 5000);
                }}
            </script>
        </body>
        </html>
        """
        
        return success_html
        
    except Exception as e:
        logger.error(f"❌ Test confirmation error: {e}")
        return render_template_string("""
            <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>Test Confirmation Error</h1>
                <p>There was an error processing your test confirmation.</p>
                <p><a href="https://lemma.id/admin/permissions">Back to Permission Manager</a></p>
            </body></html>
        """), 500
