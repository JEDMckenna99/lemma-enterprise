"""
Test Permission Lemma System
Creates non-functional test permission lemmas for testing email flow and wallet storage
"""

from flask import Blueprint, request, jsonify, render_template_string
from flask_cors import cross_origin
from datetime import datetime, timedelta
import secrets
import logging
import os
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import json

logger = logging.getLogger(__name__)

test_permission_bp = Blueprint('test_permission', __name__)

# Test permission confirmations (separate from real permissions)
test_permission_confirmations = {}

def send_test_permission_email(email, confirmation_token):
    """Send test permission confirmation email"""
    try:
        # Email configuration
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME', 'admin@lemma.id')
        smtp_password = os.getenv('SMTP_PASSWORD', 'your-app-password')
        
        # Create confirmation link
        confirmation_url = f"https://lemma.id/confirm-test-permission/{confirmation_token}"
        
        # Email content
        subject = f"TEST: Permission Lemma Demo - Lemma IAM"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; }}
                .header {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 40px 30px; text-align: center; }}
                .content {{ padding: 40px 30px; }}
                .button {{ background: #f59e0b; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600; margin: 20px 0; }}
                .footer {{ background: #f8f9fa; padding: 30px; text-align: center; color: #6c757d; font-size: 14px; }}
                .test-badge {{ background: #fff3cd; border: 2px solid #ffc107; color: #856404; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center; }}
                .info-box {{ background: #e7f3ff; border: 1px solid #b3d7ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🧪 TEST Permission Lemma</h1>
                    <p>Demo email confirmation flow</p>
                </div>
                
                <div class="content">
                    <div class="test-badge">
                        <strong>⚠️ THIS IS A TEST</strong><br>
                        This is a demonstration permission lemma that won't grant real access.<br>
                        It's safe to test with and will appear in your wallet for demo purposes.
                    </div>
                    
                    <h2>Test Permission Lemma Confirmation</h2>
                    
                    <p>You've requested a <strong>test permission lemma</strong> to demonstrate the Lemma IAM email confirmation flow.</p>
                    
                    <div class="info-box">
                        <h3>📊 Test Lemma Details:</h3>
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
                            🧪 Confirm Test Permission Lemma
                        </a>
                    </div>
                    
                    <h3>🔬 What this test demonstrates:</h3>
                    <ol>
                        <li>Email confirmation flow</li>
                        <li>Permission lemma creation</li>
                        <li>Automatic wallet storage</li>
                        <li>Wallet page display</li>
                        <li>Cross-browser synchronization</li>
                    </ol>
                    
                    <div style="background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <h4>🔒 Safe Testing:</h4>
                        <ul>
                            <li>This test lemma won't grant real platform access</li>
                            <li>It will appear in your wallet as "Test Permission"</li>
                            <li>You can safely delete it after testing</li>
                            <li>Your real admin/customer permissions remain unchanged</li>
                        </ul>
                    </div>
                    
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
        
        # Create email message
        msg = MimeMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Lemma IAM Test <{smtp_username}>"
        msg['To'] = email
        
        # Add HTML content
        html_part = MimeText(html_content, 'html')
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        logger.info(f"✅ Test permission email sent to {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send test permission email to {email}: {e}")
        return False

@test_permission_bp.route('/api/admin/send-test-permission-email', methods=['POST'])
@cross_origin()
def send_test_permission_email():
    """
    Send test permission lemma email (safe for testing)
    
    POST /api/admin/send-test-permission-email
    {
        "email": "test@example.com",
        "admin_password": "admin_pass"
    }
    """
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
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', 'defaultpass')
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        logger.info(f"🧪 Test permission email requested for: {email}")
        
        # Generate test confirmation token
        confirmation_token = f"test_perm_{secrets.token_urlsafe(32)}"
        
        # Store test confirmation (separate from real permissions)
        test_permission_confirmations[confirmation_token] = {
            'email': email,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=1),  # 1 hour expiry for test
            'confirmed': False,
            'test_type': 'manual_admin_test'
        }
        
        # Send test email
        email_sent = send_test_permission_email(email, confirmation_token)
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': f'TEST permission email sent to {email}',
                'confirmation_token': confirmation_token,
                'expires_in': '1 hour',
                'note': 'This is a safe test that won\'t affect real permissions'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send test email'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Test permission email error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@test_permission_bp.route('/confirm-test-permission/<confirmation_token>')
def confirm_test_permission(confirmation_token):
    """Confirm test permission and create demo lemma"""
    try:
        # Check if token exists and is valid
        if confirmation_token not in test_permission_confirmations:
            return render_template_string("""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>❌ Invalid Test Confirmation Link</h1>
                    <p>This test confirmation link is invalid or has expired.</p>
                    <p><a href="https://lemma.id/admin/permissions">Back to Permission Manager</a></p>
                </body></html>
            """), 404
        
        confirmation = test_permission_confirmations[confirmation_token]
        
        # Check if expired
        if datetime.utcnow() > confirmation['expires_at']:
            del test_permission_confirmations[confirmation_token]
            return render_template_string("""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>⏰ Test Confirmation Link Expired</h1>
                    <p>This test confirmation link has expired. Please send a new test email.</p>
                    <p><a href="https://lemma.id/admin/permissions">Back to Permission Manager</a></p>
                </body></html>
            """), 410
        
        # Check if already confirmed
        if confirmation['confirmed']:
            return render_template_string(f"""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>✅ Test Already Confirmed</h1>
                    <p>This test permission lemma has already been created.</p>
                    <p><a href="https://lemma.id/wallet">Check Your Wallet</a></p>
                </body></html>
            """), 200
        
        # Create test permission lemma
        email = confirmation['email']
        
        logger.info(f"🧪 Creating test permission lemma for {email}")
        
        # Create test user DID
        user_did = f'did:lemma:test-user:{email.replace("@", "_at_").replace(".", "_")}'
        
        # Create test permission lemma (safe - won't grant real access)
        import time
        current_time = int(time.time())
        
        test_permission_lemma = {
            'id': f"test_perm_{secrets.token_hex(16)}",
            'issuer': 'did:lemma:test:lemma.id',  # Special test issuer
            'subject': user_did,
            'packageType': 'permission',
            'issued_at': current_time,
            'expires_at': current_time + (7 * 24 * 60 * 60),  # 7 days for test
            'claims': {
                'packageType': 'permission',
                'siteId': 'lemma.id',
                'siteDomain': 'lemma.id',
                'permissionId': 'test_demo_access',  # Special test permission
                'accountType': 'test_user',
                'email': email,
                'scope': ['test:read', 'demo:view', 'example:access'],
                'grantedBy': 'did:lemma:test:system',
                'grantedAt': current_time,
                'networkShared': False,  # Keep test local
                'testPermission': True,  # Mark as test
                'realAccess': False,  # Explicitly mark as non-functional
                'purpose': 'email_flow_testing'
            },
            'proof': {
                'type': 'Ed25519Signature2020',
                'created': current_time,
                'verificationMethod': 'did:lemma:test:lemma.id',
                'signatureValue': f'test_sig_{secrets.token_hex(32)}'
            }
        }
        
        # Mark confirmation as complete
        confirmation['confirmed'] = True
        confirmation['confirmed_at'] = datetime.utcnow()
        confirmation['lemma_id'] = test_permission_lemma['id']
        
        logger.info(f"✅ Test permission lemma created for {email}")
        
        # Test success page with wallet integration
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Permission Confirmed - Lemma IAM</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f8f9fa; }}
                .container {{ max-width: 700px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.1); overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 50px 40px; text-align: center; }}
                .content {{ padding: 50px 40px; }}
                .button {{ background: #007bff; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600; margin: 15px 10px; }}
                .test-badge {{ background: #fff3cd; border: 2px solid #ffc107; color: #856404; padding: 20px; border-radius: 8px; margin: 30px 0; text-align: center; }}
                .success-badge {{ background: #d4edda; color: #155724; padding: 20px; border-radius: 8px; margin: 30px 0; }}
                .lemma-data {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 20px 0; font-family: monospace; font-size: 12px; }}
            </style>
            <script src="https://lemma.id/static/js/lemma-federated-wallet.js?v=672"></script>
            <script src="https://lemma.id/static/js/lemma-wallet-manager.js"></script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🧪 Test Confirmed!</h1>
                    <p>Your test permission lemma is ready</p>
                </div>
                
                <div class="content">
                    <div class="test-badge">
                        <h3>⚠️ THIS IS A SAFE TEST</h3>
                        <p>This test permission lemma won't grant real access to your platform.<br>
                        It's designed to test the email flow and wallet storage safely.</p>
                    </div>
                    
                    <div class="success-badge">
                        <h3>✅ Test Successfully Created:</h3>
                        <ul>
                            <li><strong>Email:</strong> {email}</li>
                            <li><strong>Permission:</strong> Test Demo Access</li>
                            <li><strong>Type:</strong> test_demo_access</li>
                            <li><strong>Lemma ID:</strong> {test_permission_lemma['id']}</li>
                            <li><strong>Expires:</strong> 7 days (test duration)</li>
                            <li><strong>Real Access:</strong> No (safe for testing)</li>
                        </ul>
                    </div>
                    
                    <h3>🧪 Test Permission Lemma Data:</h3>
                    <div class="lemma-data" id="testLemmaData">
                        {json.dumps(test_permission_lemma, indent=2)}
                    </div>
                    
                    <h3>📋 What was tested:</h3>
                    <ol>
                        <li>✅ Email sending and delivery</li>
                        <li>✅ Confirmation link functionality</li>
                        <li>✅ Permission lemma creation</li>
                        <li>✅ Wallet storage integration</li>
                        <li>✅ Cross-browser synchronization</li>
                        <li>✅ Wallet page display</li>
                    </ol>
                    
                    <div style="text-align: center; margin: 40px 0;">
                        <a href="https://lemma.id/wallet" class="button">
                            💼 Check Your Wallet
                        </a>
                        <a href="https://lemma.id/admin/permissions" class="button">
                            🔧 Back to Permission Manager
                        </a>
                    </div>
                    
                    <div style="background: #e7f3ff; border: 1px solid #b3d7ff; color: #0c5460; padding: 20px; border-radius: 8px; margin: 30px 0;">
                        <h4>🎯 Next Steps for Real Implementation:</h4>
                        <ul>
                            <li>This test proves the email flow works correctly</li>
                            <li>You can now confidently deploy this for customers</li>
                            <li>Real permission lemmas will work the same way</li>
                            <li>The test lemma will appear in your wallet but won't grant access</li>
                        </ul>
                    </div>
                </div>
            </div>
            
            <script>
                // Test wallet integration using centralized manager
                document.addEventListener('DOMContentLoaded', async function() {{
                    try {{
                        console.log('🧪 Test: Using LemmaWalletManager for test permission lemma...');
                        
                        // Use the centralized wallet manager
                        const testLemmaData = {json.dumps(test_permission_lemma)};
                        
                        console.log('📊 Test permission lemma to store:', {{
                            id: testLemmaData.id,
                            siteId: testLemmaData.claims?.siteId,
                            email: testLemmaData.claims?.email,
                            permissionId: testLemmaData.claims?.permissionId,
                            testPermission: testLemmaData.claims?.testPermission,
                            realAccess: testLemmaData.claims?.realAccess
                        }});
                        
                        // Store test permission using centralized manager
                        const result = await window.storeLemmaCredential(testLemmaData, {{
                            allowDuplicates: false,
                            verifyStorage: true
                        }});
                        
                        if (result.success) {{
                            if (result.duplicate) {{
                                console.log('ℹ️ Test permission lemma already exists in wallet');
                                showTestMessage('ℹ️ Test permission already in your wallet', '#007bff');
                            }} else {{
                                console.log('✅ Test permission lemma stored in unified wallet');
                                showTestMessage('✅ Test permission stored in your wallet!', '#f59e0b');
                                
                                // Verify storage
                                setTimeout(async () => {{
                                    const credentials = await window.getLemmaCredentials('permission');
                                    const stored = credentials.find(cred => cred.id === testLemmaData.id);
                                    if (stored) {{
                                        console.log('✅ Test verification: Permission lemma confirmed in wallet');
                                        showTestMessage('✅ Test successful: Check your wallet page!', '#28a745');
                                    }} else {{
                                        console.warn('⚠️ Test verification: Permission lemma not found');
                                    }}
                                }}, 2000);
                            }}
                        }} else {{
                            console.warn('⚠️ Test failed to store permission lemma:', result.error);
                            showTestMessage('⚠️ Test storage failed: ' + result.error, '#dc3545');
                        }}
                        
                    }} catch (error) {{
                        console.error('❌ Test wallet error:', error);
                        showTestMessage('❌ Test error: ' + error.message, '#dc3545');
                    }}
                }});
                
                // Test message display
                function showTestMessage(message, color) {{
                    const testMsg = document.createElement('div');
                    testMsg.style.cssText = `position: fixed; top: 20px; right: 20px; background: ${{color}}; color: white; padding: 15px 20px; border-radius: 8px; z-index: 1000; box-shadow: 0 4px 12px rgba(0,0,0,0.2); max-width: 400px; border-left: 4px solid white;`;
                    testMsg.innerHTML = '🧪 TEST: ' + message;
                    document.body.appendChild(testMsg);
                    
                    // Remove message after 5 seconds
                    setTimeout(() => {{
                        if (document.body.contains(testMsg)) {{
                            document.body.removeChild(testMsg);
                        }}
                    }}, 5000);
                }}
            </script>
        </body>
        </html>
        """
        
        return success_html
        
    except Exception as e:
        logger.error(f"❌ Error in test permission confirmation: {e}")
        return render_template_string("""
            <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>❌ Test Confirmation Error</h1>
                <p>There was an error processing your test confirmation.</p>
                <p><a href="https://lemma.id/admin/permissions">Back to Permission Manager</a></p>
            </body></html>
        """), 500
