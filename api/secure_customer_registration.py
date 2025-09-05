"""
Secure Customer Registration System
Requires email confirmation before creating accounts and issuing API keys
"""

from flask import Blueprint, request, jsonify, render_template_string
from flask_cors import cross_origin
from datetime import datetime, timedelta
import secrets
import logging
import os

from .database import get_db, Customer
from .mailgun_email_sender import MailgunSender

logger = logging.getLogger(__name__)

secure_registration_bp = Blueprint('secure_registration', __name__)

# In-memory storage for pending customer registrations
pending_customer_registrations = {}

def send_customer_confirmation_email(email, company_name, confirmation_token):
    """Send customer registration confirmation email"""
    try:
        # Create confirmation link
        confirmation_url = f"https://lemma.id/confirm-customer-registration/{confirmation_token}"
        
        # Email content (consistent styling, no gradients, no emojis per user preference)
        subject = f"Confirm Your Lemma IAM Account - {company_name}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; }}
                .header {{ background: #007bff; color: white; padding: 40px 30px; text-align: center; }}
                .content {{ padding: 40px 30px; }}
                .button {{ background: #007bff; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600; margin: 20px 0; }}
                .footer {{ background: #f8f9fa; padding: 30px; text-align: center; color: #6c757d; font-size: 14px; }}
                .info-box {{ background: #e7f3ff; border: 1px solid #b3d7ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .security-note {{ background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 6px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Confirm Your Lemma IAM Account</h1>
                    <p>Complete your registration to get API keys</p>
                </div>
                
                <div class="content">
                    <h2>Welcome to Lemma IAM, {company_name}!</h2>
                    
                    <p>Thank you for registering for <strong>Lemma IAM</strong>. To complete your account setup and receive your API keys, please confirm your email address.</p>
                    
                    <div class="info-box">
                        <h3>Account Details:</h3>
                        <ul>
                            <li><strong>Email:</strong> {email}</li>
                            <li><strong>Company:</strong> {company_name}</li>
                            <li><strong>Service:</strong> Lemma IAM Platform</li>
                            <li><strong>Performance:</strong> 2.38µs authentication</li>
                            <li><strong>Cost:</strong> $0.20/user/month (90% savings vs Auth0+Duo)</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center;">
                        <a href="{confirmation_url}" class="button">
                            Confirm Email & Get API Keys
                        </a>
                    </div>
                    
                    <h3>What happens after confirmation?</h3>
                    <ol>
                        <li>Your customer account is activated</li>
                        <li>API keys are generated for your company</li>
                        <li>Access to the Lemma IAM dashboard</li>
                        <li>Site registration and user management</li>
                        <li>Real-time usage analytics and billing</li>
                    </ol>
                    
                    <div class="security-note">
                        <h4>Security Notice:</h4>
                        <p>For security, API keys are only issued after email confirmation. This prevents unauthorized access and protects your account.</p>
                    </div>
                    
                    <p style="font-size: 14px; color: #6c757d; margin-top: 30px;">
                        This confirmation link will expire in 24 hours. If you didn't register for Lemma IAM, you can safely ignore this email.
                    </p>
                </div>
                
                <div class="footer">
                    <p><strong>Lemma IAM Platform</strong> - Microsecond Identity & Access Management</p>
                    <p>Replace Auth0/Duo with 210,000x faster verification</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send email using Mailgun HTTP API
        sender = MailgunSender()
        result = sender.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            from_email=f"Lemma IAM <postmaster@{sender.domain}>"
        )
        
        if result['success']:
            logger.info(f"✅ Customer registration confirmation email sent to {email} via Mailgun API")
            return True
        else:
            logger.error(f"❌ Failed to send customer confirmation email to {email}: {result['error']}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Failed to send customer confirmation email to {email}: {e}")
        return False

@secure_registration_bp.route('/api/customer/register-secure', methods=['POST'])
@cross_origin()
def secure_customer_registration():
    """
    Secure customer registration - requires email confirmation before API keys
    """
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip()
        company = data.get('company', '').strip()
        billing_email = data.get('billing_email', '').strip().lower()
        
        # Validation
        if not all([email, name, company]):
            return jsonify({
                'success': False,
                'error': 'Email, name, and company are required'
            }), 400
        
        if '@' not in email:
            return jsonify({
                'success': False,
                'error': 'Invalid email address'
            }), 400
        
        # Check if customer already exists
        db = get_db()
        existing_customer = db.query(Customer).filter(Customer.email == email).first()
        if existing_customer:
            db.close()
            return jsonify({
                'success': False,
                'error': 'Customer with this email already exists'
            }), 409
        
        db.close()
        
        logger.info(f"🔐 Secure customer registration requested: {email} ({company})")
        
        # Generate confirmation token
        confirmation_token = f"customer_reg_{secrets.token_urlsafe(32)}"
        
        # Store pending registration (NO API keys yet)
        pending_customer_registrations[confirmation_token] = {
            'email': email,
            'name': name,
            'company': company,
            'billing_email': billing_email or email,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=24),  # 24 hour expiry
            'confirmed': False,
            'api_keys_issued': False
        }
        
        # Send confirmation email
        email_sent = send_customer_confirmation_email(email, company, confirmation_token)
        
        if email_sent:
            return jsonify({
                'success': True,
                'message': f'Registration confirmation email sent to {email}',
                'company': company,
                'confirmation_required': True,
                'expires_in': '24 hours',
                'note': 'Check your email to complete registration and get API keys'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send confirmation email'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Secure customer registration error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@secure_registration_bp.route('/confirm-customer-registration/<confirmation_token>')
def confirm_customer_registration(confirmation_token):
    """Confirm customer registration and issue API keys"""
    try:
        logger.info(f"🔍 Customer registration confirmation for token: {confirmation_token}")
        
        # Check if token exists
        if confirmation_token not in pending_customer_registrations:
            # Recovery mechanism for server restarts
            if confirmation_token.startswith('customer_reg_') and len(confirmation_token) > 20:
                logger.warning(f"⚠️ Token not found in memory (likely server restart)")
                return render_template_string("""
                    <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                        <h1>Registration Link Not Found</h1>
                        <p>This registration link may have expired due to server maintenance.</p>
                        <p>Please register again to get a fresh confirmation link.</p>
                        <p><a href="https://lemma.id/register">Register Again</a></p>
                    </body></html>
                """), 404
            else:
                return render_template_string("""
                    <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                        <h1>Invalid Registration Link</h1>
                        <p>This registration link is invalid.</p>
                        <p><a href="https://lemma.id/register">Start Registration</a></p>
                    </body></html>
                """), 404
        
        registration = pending_customer_registrations[confirmation_token]
        
        # Check if expired
        if datetime.utcnow() > registration['expires_at']:
            del pending_customer_registrations[confirmation_token]
            return render_template_string("""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Registration Link Expired</h1>
                    <p>This registration link has expired. Please register again.</p>
                    <p><a href="https://lemma.id/register">Register Again</a></p>
                </body></html>
            """), 410
        
        # Check if already confirmed
        if registration['confirmed']:
            return render_template_string(f"""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Already Confirmed</h1>
                    <p>Your registration for {registration['company']} has already been confirmed.</p>
                    <p><a href="https://lemma.id/login">Sign In</a></p>
                </body></html>
            """), 200
        
        # NOW create the customer account with API keys
        from .customer_accounts import CustomerAccountManager
        customer_manager = CustomerAccountManager()
        
        result = customer_manager.create_customer(
            email=registration['email'],
            name=registration['name'],
            company=registration['company'],
            billing_email=registration['billing_email']
        )
        
        if result['success']:
            # Mark as confirmed
            registration['confirmed'] = True
            registration['confirmed_at'] = datetime.utcnow()
            registration['customer_id'] = result['customer_id']
            registration['api_keys_issued'] = True
            
            logger.info(f"✅ Customer registration confirmed and API keys issued: {registration['email']}")
            
            # Success page
            success_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Registration Confirmed</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link rel="stylesheet" href="https://lemma.id/static/css/lemma.css">
            </head>
            <body>
                <div style="max-width: 700px; margin: 40px auto; padding: 0 20px;">
                    <div style="background: var(--white); border: 1px solid var(--gray-200); border-radius: 12px; padding: 32px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);">
                        <h1 style="color: var(--gray-900); margin-bottom: 16px;">Registration Confirmed!</h1>
                        
                        <div style="background: var(--success); color: var(--white); padding: 16px; border-radius: 8px; margin: 20px 0;">
                            <h3 style="margin: 0 0 8px 0; color: var(--white);">Account Successfully Created</h3>
                            <ul style="margin: 8px 0 0 20px; color: var(--white);">
                                <li>Company: {registration['company']}</li>
                                <li>Email: {registration['email']}</li>
                                <li>Customer ID: {result['customer_id']}</li>
                                <li>API Keys: Generated and ready</li>
                                <li>Status: Active</li>
                            </ul>
                        </div>
                        
                        <div style="background: var(--primary-light); border: 1px solid var(--primary); border-radius: 8px; padding: 20px; margin: 20px 0;">
                            <h3 style="color: var(--gray-900);">Your API Key</h3>
                            <div style="background: var(--gray-900); color: var(--gray-100); padding: 16px; border-radius: 6px; font-family: var(--font-mono); font-size: 14px; word-break: break-all;">
                                {result.get('api_key', 'API key will be displayed here')}
                            </div>
                            <p style="color: var(--gray-600); font-size: 14px; margin: 12px 0 0 0;">
                                <strong>Important:</strong> Save this API key securely. You'll need it for integration.
                            </p>
                        </div>
                        
                        <h3 style="color: var(--gray-900);">What's Next?</h3>
                        <ol style="color: var(--gray-700);">
                            <li>Save your API key in a secure location</li>
                            <li>Sign in to access your dashboard</li>
                            <li>Register your first site</li>
                            <li>Start integrating Lemma IAM</li>
                        </ol>
                        
                        <div style="text-align: center; margin: 40px 0;">
                            <a href="https://lemma.id/login" class="btn btn-primary" style="margin: 0 8px;">
                                Sign In to Dashboard
                            </a>
                            <a href="https://lemma.id/integrate" class="btn btn-secondary" style="margin: 0 8px;">
                                Integration Guide
                            </a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            return success_html
        else:
            logger.error(f"❌ Customer account creation failed: {result.get('error')}")
            return render_template_string("""
                <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>Registration Error</h1>
                    <p>There was an error creating your customer account.</p>
                    <p><a href="https://lemma.id/register">Try Again</a></p>
                </body></html>
            """), 500
        
    except Exception as e:
        logger.error(f"❌ Customer registration confirmation error: {e}")
        return render_template_string("""
            <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>Confirmation Error</h1>
                <p>There was an error processing your registration confirmation.</p>
                <p><a href="https://lemma.id/register">Try Again</a></p>
            </body></html>
        """), 500

@secure_registration_bp.route('/api/customer/registration-status/<confirmation_token>', methods=['GET'])
@cross_origin()
def check_registration_status(confirmation_token):
    """Check the status of a pending customer registration"""
    try:
        if confirmation_token in pending_customer_registrations:
            registration = pending_customer_registrations[confirmation_token]
            
            return jsonify({
                'success': True,
                'status': 'confirmed' if registration['confirmed'] else 'pending',
                'email': registration['email'],
                'company': registration['company'],
                'created_at': registration['created_at'].isoformat(),
                'expires_at': registration['expires_at'].isoformat(),
                'api_keys_issued': registration.get('api_keys_issued', False)
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Registration token not found'
            }), 404
            
    except Exception as e:
        logger.error(f"❌ Registration status check error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
