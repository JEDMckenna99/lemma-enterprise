"""
Beta Access Request Handler for Lemma Platform
Simplified email-based authentication using Lemma IAM
"""

import os
import time
import secrets
import hashlib
import logging
from flask import Blueprint, request, jsonify, render_template
from flask_cors import cross_origin
from .customer_accounts import CustomerAccountManager
from .iam_manager import get_or_create_site_manager
from .email_service import send_email, render_email_template
from .rate_limiting import rate_limit_email_confirmation, check_ip_not_blocked

# Import shared pending requests from IAM confirmation
from .iam_email_confirmation import pending_access_requests

logger = logging.getLogger(__name__)

# Create blueprint
beta_access_bp = Blueprint('beta_access', __name__)

# Initialize customer manager
customer_manager = CustomerAccountManager()


@beta_access_bp.route('/api/auth/request-beta-access', methods=['POST', 'OPTIONS'])
@cross_origin()
@check_ip_not_blocked()
@rate_limit_email_confirmation()
def request_beta_access():
    """
    Request beta access to Lemma platform
    
    POST /api/auth/request-beta-access
    {
        "email": "user@example.com"
    }
    
    Flow:
    1. Check if user exists in database
    2. If exists and suspended/denied → deny
    3. If exists and active OR doesn't exist → send credential email
    4. User clicks email link → gets beta-user permission credential
    """
    try:
        if request.method == 'OPTIONS':
            return jsonify({'success': True}), 200
            
        data = request.get_json()
        user_email = data.get('email', '').strip().lower()
        
        if not user_email:
            return jsonify({
                'success': False,
                'error': 'Email address is required'
            }), 400
        
        # Basic email validation
        if '@' not in user_email or '.' not in user_email.split('@')[1]:
            return jsonify({
                'success': False,
                'error': 'Please enter a valid email address'
            }), 400
        
        # Check if user exists in database
        existing_customer = customer_manager.get_customer_by_email(user_email)
        
        if existing_customer:
            # User exists - check their status
            if existing_customer.status == 'suspended':
                logger.warning(f"❌ Beta access denied for suspended user: {user_email}")
                return jsonify({
                    'success': False,
                    'error': 'Your account has been suspended. Please contact support.'
                }), 403
            
            # User exists and is active/pending - proceed with credential issuance
            logger.info(f"✅ Existing user {user_email} requesting beta access (status: {existing_customer.status})")
        else:
            # New user - will be created when they confirm access
            logger.info(f"🆕 New user {user_email} requesting beta access")
        
        # Generate confirmation token
        confirmation_token = secrets.token_urlsafe(32)
        
        # Get or create site manager for lemma.id
        site_id = 'lemma_platform'
        site_domain = 'lemma.id'
        site_manager = get_or_create_site_manager(site_id, site_domain)
        
        if not site_manager:
            logger.error(f"❌ Failed to get site manager for {site_domain}")
            return jsonify({
                'success': False,
                'error': 'Platform configuration error. Please try again later.'
            }), 500
        
        # Ensure beta_user permission exists
        if 'beta_user' not in site_manager.permissions:
            site_manager.add_permission({
                'permission_id': 'beta_user',
                'display_name': 'Beta User',
                'scope': [
                    'platform:access',
                    'api:read',
                    'api:write',
                    'dashboard:access',
                    'wallet:access'
                ],
                'conditions': [],
                'priority': 100
            })
            logger.info("✅ Created beta_user permission")
        
        # Store pending request
        pending_access_requests[confirmation_token] = {
            'site_id': site_id,
            'site_domain': site_domain,
            'user_email': user_email,
            'permission_level': 'beta_user',
            'redirect_url': f'https://{site_domain}/dashboard',
            'created_at': time.time(),
            'expires_at': time.time() + (24 * 60 * 60)  # 24 hour expiry
        }
        
        # Generate confirmation link
        base_url = request.host_url.rstrip('/')
        confirmation_link = f"{base_url}/confirm-access?token={confirmation_token}"
        
        # Send email with credential link
        email_html = render_email_template(
            'beta_access_confirmation',
            site_domain=site_domain,
            confirmation_link=confirmation_link,
            user_email=user_email
        )
        
        email_result = send_email(
            to=user_email,
            subject=f"Sign in to Lemma Platform - FREE Beta Access",
            html=email_html
        )
        
        if not email_result:
            logger.error(f"❌ Failed to send email to {user_email}")
            return jsonify({
                'success': False,
                'error': 'Failed to send email. Please try again.'
            }), 500
        
        logger.info(f"📧 Sent beta access confirmation email to {user_email}")
        logger.info(f"🔗 Confirmation link: {confirmation_link}")
        
        return jsonify({
            'success': True,
            'message': 'Check your email for the sign-in link',
            'email': user_email
        })
        
    except Exception as e:
        logger.error(f"❌ Request beta access error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }), 500

