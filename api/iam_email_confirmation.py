"""
IAM Email Confirmation Flow
Implements email-based permission lemma issuance
"""

import secrets
import time
import json
import logging
import hashlib
from flask import Blueprint, request, jsonify, render_template, redirect
from flask_cors import cross_origin

from api.email_service import send_email, render_email_template
from api.real_iam_manager import get_site_manager, get_or_create_site_manager
from api.rate_limiter import rate_limit_email_confirmation, check_ip_not_blocked

logger = logging.getLogger(__name__)

iam_email_bp = Blueprint('iam_email', __name__)

# In-memory storage for pending access requests
# In production, use Redis with TTL
pending_access_requests = {}

@iam_email_bp.route('/api/v1/iam/request-access', methods=['POST'])
@cross_origin()
@check_ip_not_blocked()
@rate_limit_email_confirmation()
def request_access():
    """
    User requests access to a site via email
    
    POST /api/v1/iam/request-access
    {
        "site_id": "customer_site_123",
        "site_domain": "customer.com",
        "user_email": "user@example.com",
        "permission_level": "user|admin|editor",
        "redirect_url": "https://customer.com/dashboard"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['site_id', 'user_email', 'permission_level']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        site_id = data['site_id']
        site_domain = data.get('site_domain', f'site_{site_id}.com')
        user_email = data['user_email']
        permission_level = data.get('permission_level', 'user')
        redirect_url = data.get('redirect_url', f'https://{site_domain}')
        
        # Validate email format
        if '@' not in user_email or '.' not in user_email:
            return jsonify({'error': 'Invalid email address'}), 400
        
        # Get or create site manager (auto-creates for new sites)
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Generate confirmation token
        confirmation_token = secrets.token_urlsafe(32)
        
        # Store pending request (expires in 24 hours)
        pending_access_requests[confirmation_token] = {
            'site_id': site_id,
            'site_domain': site_domain,
            'user_email': user_email,
            'permission_level': permission_level,
            'redirect_url': redirect_url,
            'created_at': time.time(),
            'expires_at': time.time() + (24 * 60 * 60)
        }
        
        # Generate confirmation link
        base_url = request.host_url.rstrip('/')
        confirmation_link = f"{base_url}/confirm-access?token={confirmation_token}"
        
        # Send confirmation email
        email_html = render_email_template(
            'access_confirmation',
            site_domain=site_domain,
            permission_level=permission_level,
            confirmation_link=confirmation_link
        )
        
        email_result = send_email(
            to=user_email,
            subject=f"Confirm access to {site_domain}",
            html=email_html
        )
        
        if email_result['success']:
            logger.info(f"📧 Sent access confirmation to {user_email} for {site_domain} ({permission_level})")
            
            return jsonify({
                'success': True,
                'message': 'Confirmation email sent. Check your inbox.',
                'expires_in': 86400,
                'email_provider': email_result.get('provider')
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send email',
                'details': email_result.get('message')
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Request access error: {e}")
        return jsonify({'error': str(e)}), 500


@iam_email_bp.route('/confirm-access', methods=['GET'])
def confirm_access():
    """
    User clicks confirmation link
    Issues permission lemma to their browser wallet
    
    GET /confirm-access?token=abc123
    """
    try:
        token = request.args.get('token')
        
        if not token:
            return jsonify({
                'error': 'missing_token',
                'message': 'Missing confirmation token'
            }), 400
        
        # Get pending request
        pending = pending_access_requests.get(token)
        
        if not pending:
            return jsonify({
                'error': 'invalid_token',
                'message': 'Invalid or expired confirmation link'
            }), 400
        
        # Check expiration
        if time.time() > pending['expires_at']:
            del pending_access_requests[token]
            return jsonify({
                'error': 'expired_token',
                'message': 'Confirmation link expired (24 hour limit)'
            }), 400
        
        # Get site manager
        site_id = pending['site_id']
        site_domain = pending['site_domain']
        manager = get_site_manager(site_id, site_domain)
        
        if not manager:
            # Try to recreate manager
            manager = get_or_create_site_manager(site_id, site_domain)
            if not manager:
                return jsonify({
                    'error': 'site_not_found',
                    'message': 'Site not found'
                }), 404
        
        # Recreate permission if not in memory (multi-dyno issue)
        permission_level = pending['permission_level']
        if permission_level not in manager.permissions:
            manager.add_permission({
                'permission_id': permission_level,
                'display_name': permission_level.title(),
                'scope': get_default_scope(permission_level),
                'conditions': [],
                'priority': 100
            })
        
        # Create user DID from email
        user_email = pending['user_email']
        user_did = f"did:lemma:user_{hashlib.sha256(user_email.encode()).hexdigest()[:56]}"
        
        # Issue permission lemma with REAL Ed25519 signature
        start_time = time.perf_counter()
        permission_lemma = manager.issue_permission_lemma(
            user_did,
            permission_level,
            expiry_days=90,
            custom_claims={'email': user_email, 'site_domain': site_domain}
        )
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Clean up pending request
        del pending_access_requests[token]
        
        logger.info(f"✅ Issued {permission_level} credential to {user_email} for {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔐 Credential ID: {permission_lemma['id']}")
        
        # Render confirmation page with credential
        return render_template('modern/confirm_access.html',
                             permission_lemma=json.dumps(permission_lemma),
                             redirect_url=pending['redirect_url'],
                             user_email=user_email,
                             site_domain=site_domain,
                             permission_level=permission_level,
                             issue_time_us=issue_time_us)
        
    except Exception as e:
        logger.error(f"❌ Confirm access error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'internal_error',
            'message': f'Error confirming access: {str(e)}'
        }), 500


def get_default_scope(permission_level: str) -> list:
    """Get default scope for permission level"""
    scopes = {
        'admin': ['*'],
        'super_admin': ['*'],
        'editor': ['posts:*', 'comments:*', 'users:read'],
        'user': ['posts:read', 'comments:read', 'profile:*'],
        'viewer': ['posts:read', 'comments:read']
    }
    return scopes.get(permission_level, ['posts:read'])


@iam_email_bp.route('/api/v1/iam/send-credential-email', methods=['POST'])
@cross_origin()
def send_credential_directly():
    """
    Direct API for sending permission lemma via email
    Used by site admins to grant access to users
    
    POST /api/v1/iam/send-credential-email
    {
        "site_id": "lemma_platform",
        "site_domain": "lemma.id",
        "user_email": "jedmckenna@lemma.id",
        "permission_level": "super_admin",
        "api_key": "your_api_key"
    }
    """
    try:
        data = request.get_json()
        
        # For now, allow direct send (in production, validate API key)
        site_id = data.get('site_id', 'lemma_platform')
        site_domain = data.get('site_domain', 'lemma.id')
        user_email = data['user_email']
        permission_level = data.get('permission_level', 'admin')
        
        # Create confirmation request
        confirmation_token = secrets.token_urlsafe(32)
        
        pending_access_requests[confirmation_token] = {
            'site_id': site_id,
            'site_domain': site_domain,
            'user_email': user_email,
            'permission_level': permission_level,
            'redirect_url': f'https://{site_domain}/dashboard',
            'created_at': time.time(),
            'expires_at': time.time() + (24 * 60 * 60)
        }
        
        # Generate confirmation link
        base_url = request.host_url.rstrip('/')
        confirmation_link = f"{base_url}/confirm-access?token={confirmation_token}"
        
        # Send email
        email_html = render_email_template(
            'access_confirmation',
            site_domain=site_domain,
            permission_level=permission_level,
            confirmation_link=confirmation_link
        )
        
        email_result = send_email(
            to=user_email,
            subject=f"Your {permission_level} access to {site_domain}",
            html=email_html
        )
        
        logger.info(f"📧 Sent credential email to {user_email} for {site_domain}")
        
        return jsonify({
            'success': True,
            'message': f'Credential email sent to {user_email}',
            'confirmation_link': confirmation_link,  # For testing
            'email_provider': email_result.get('provider')
        })
        
    except Exception as e:
        logger.error(f"❌ Send credential email error: {e}")
        return jsonify({'error': str(e)}), 500


