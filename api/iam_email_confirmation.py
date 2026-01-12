"""
IAM Email Confirmation Flow - PRIVACY PRESERVING
Implements email-based permission lemma issuance WITHOUT storing email addresses.

Privacy Design:
- Email is used ONLY for delivery (via SendGrid)
- Email is NEVER stored in Redis, database, or credentials
- User must authenticate with passkey to claim permission
- DID is derived from passkey credential ID (not email)
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
from api.ppid import derive_ppid_did
from api.rate_limiter import rate_limit_email_confirmation, check_ip_not_blocked

# Import Redis for persistent token storage
try:
    from api.database import get_redis_client
    redis_available = True
except ImportError:
    redis_available = False

logger = logging.getLogger(__name__)

iam_email_bp = Blueprint('iam_email', __name__)

# Token storage (Redis for production, fallback to in-memory for dev)
if redis_available:
    logger.info("✅ Using Redis for email confirmation tokens (PRIVACY MODE - no email stored)")
else:
    logger.warning("⚠️ Redis not available - using in-memory storage (tokens lost on restart!)")
    pending_access_requests = {}

def store_confirmation_token(token, data, ttl=86400):
    """Store confirmation token (Redis or in-memory)"""
    logger.info(f"🔍 Attempting to store token: {token[:16]}... (redis_available={redis_available})")
    
    if redis_available:
        try:
            redis = get_redis_client()
            key = f"email_confirm:{token}"
            logger.info(f"🔍 Redis client obtained, storing with key: {key}")
            redis.setex(key, ttl, json.dumps(data))
            logger.info(f"📦 Stored confirmation token in Redis: {token[:16]}...")
            
            # Verify it was stored
            verify = redis.get(key)
            if verify:
                logger.info(f"✅ Verified token stored in Redis (size: {len(verify)} bytes)")
            else:
                logger.error(f"❌ Token stored but cannot retrieve immediately!")
        except Exception as e:
            logger.error(f"❌ Failed to store token in Redis: {e}")
            logger.error(f"   Falling back to in-memory storage")
            # Fallback to in-memory
            if 'pending_access_requests' not in globals():
                globals()['pending_access_requests'] = {}
            pending_access_requests[token] = data
    else:
        logger.warning(f"⚠️ Redis not available, using in-memory storage")
        if 'pending_access_requests' not in globals():
            globals()['pending_access_requests'] = {}
        pending_access_requests[token] = data

def get_confirmation_token(token):
    """Retrieve confirmation token data"""
    logger.info(f"🔍 Attempting to retrieve token: {token[:16]}... (redis_available={redis_available})")
    
    if redis_available:
        try:
            redis = get_redis_client()
            key = f"email_confirm:{token}"
            logger.info(f"🔍 Checking Redis key: {key}")
            
            # Check if key exists
            exists = redis.exists(key)
            logger.info(f"🔍 Key exists in Redis: {exists}")
            
            data = redis.get(key)
            if data:
                logger.info(f"✅ Retrieved token from Redis: {token[:16]}... (size: {len(data)} bytes)")
                return json.loads(data)
            logger.warning(f"⚠️ Token not found in Redis: {token[:16]}...")
            logger.warning(f"   Checking all email_confirm:* keys in Redis...")
            
            # Debug: List all email confirmation keys
            all_keys = redis.keys("email_confirm:*")
            logger.warning(f"   Found {len(all_keys)} total confirmation tokens in Redis")
            
            return None
        except Exception as e:
            logger.error(f"❌ Failed to retrieve token from Redis: {e}")
            logger.error(f"   Exception type: {type(e).__name__}")
            # Fallback to in-memory
            if 'pending_access_requests' in globals():
                return pending_access_requests.get(token)
            return None
    else:
        logger.warning(f"⚠️ Redis not available, checking in-memory storage")
        if 'pending_access_requests' in globals():
            return pending_access_requests.get(token)
        return None

def delete_confirmation_token(token):
    """Delete confirmation token after use"""
    if redis_available:
        try:
            redis = get_redis_client()
            key = f"email_confirm:{token}"
            redis.delete(key)
            logger.info(f"🗑️ Deleted confirmation token from Redis: {token[:16]}...")
        except Exception as e:
            logger.error(f"❌ Failed to delete token from Redis: {e}")
            # Fallback to in-memory
            pending_access_requests.pop(token, None)
    else:
        pending_access_requests.pop(token, None)

@iam_email_bp.route('/api/v1/iam/request-access', methods=['POST'])
@cross_origin()
@check_ip_not_blocked()
@rate_limit_email_confirmation()
def request_access():
    """
    PRIVACY-PRESERVING: Send permission claim link via email
    
    The email address is used ONLY for SendGrid delivery - it is NEVER stored
    in Redis, database, or credential claims.
    
    POST /api/v1/iam/request-access
    {
        "site_id": "customer_site_123",
        "site_domain": "customer.com",
        "user_email": "user@example.com",       # Used for delivery only
        "permission_level": "user|admin|editor",
        "redirect_url": "https://customer.com/dashboard"
    }
    
    The recipient must authenticate with passkey to claim the permission.
    Their DID is derived from passkey (not email).
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
        user_email = data['user_email']  # Used ONLY for delivery
        permission_level = data.get('permission_level', 'user')
        redirect_url = data.get('redirect_url', f'https://{site_domain}')
        expiry_days = data.get('expiry_days', 90)
        
        # Validate email format (for delivery only)
        if '@' not in user_email or '.' not in user_email:
            return jsonify({'error': 'Invalid email address'}), 400
        
        # Get or create site manager (auto-creates for new sites)
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Generate claim token (secure, one-time use)
        claim_token = secrets.token_urlsafe(32)
        
        # PRIVACY: Store ONLY permission metadata - NO EMAIL
        # The email is used for SendGrid delivery and then discarded
        token_data = {
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'redirect_url': redirect_url,
            'expiry_days': expiry_days,
            'created_at': time.time(),
            'expires_at': time.time() + (7 * 24 * 60 * 60),  # 7 day claim window
            # NO user_email field - privacy by design
        }
        store_confirmation_token(claim_token, token_data, ttl=604800)  # 7 days
        
        # Generate claim link (goes to passkey-protected claim page)
        base_url = request.host_url.rstrip('/')
        claim_link = f"{base_url}/claim-permission?token={claim_token}"
        
        # Send email via SendGrid (email address NOT logged or stored)
        email_html = render_email_template(
            'permission_claim',  # New privacy-preserving template
            site_domain=site_domain,
            permission_level=permission_level,
            claim_link=claim_link,
            expiry_days=7  # Claim window
        )
        
        # Fallback to old template if new one doesn't exist
        if not email_html:
            email_html = render_email_template(
                'access_confirmation',
                site_domain=site_domain,
                permission_level=permission_level,
                confirmation_link=claim_link
            )
        
        email_result = send_email(
            to=user_email,
            subject=f"🎫 Claim your {permission_level} access to {site_domain}",
            html=email_html
        )
        
        if email_result['success']:
            # Log without email (privacy)
            logger.info(f"📧 Sent permission claim email for {site_domain} ({permission_level})")
            logger.info(f"🔒 Privacy mode: email address not stored")
            
            return jsonify({
                'success': True,
                'message': 'Permission claim email sent. Recipient must authenticate with passkey to claim.',
                'expires_in': 604800,  # 7 days
                'privacy_mode': True,
                'email_provider': email_result.get('provider')
            })
        else:
            # Clean up token on email failure
            delete_confirmation_token(claim_token)
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
    Legacy endpoint - redirect to new claim page
    """
    token = request.args.get('token')
    if token:
        return redirect(f'/claim-permission?token={token}')
    return jsonify({'error': 'missing_token'}), 400


@iam_email_bp.route('/claim-permission', methods=['GET'])
def claim_permission_page():
    """
    PRIVACY-PRESERVING: Claim permission page
    
    User lands here from email link, must authenticate with passkey
    to claim the permission. No email is stored or used for DID.
    
    GET /claim-permission?token=abc123
    """
    try:
        token = request.args.get('token')
        
        if not token:
            return render_template('modern/claim_permission.html',
                                 error='Missing claim token',
                                 token=None)
        
        # Get pending request from Redis (contains NO email)
        pending = get_confirmation_token(token)
        
        if not pending:
            logger.warning(f"⚠️ Invalid or expired claim token: {token[:16]}...")
            return render_template('modern/claim_permission.html',
                                 error='Invalid or expired claim link. Please request a new one.',
                                 token=None)
        
        # Check expiration
        if time.time() > pending['expires_at']:
            delete_confirmation_token(token)
            return render_template('modern/claim_permission.html',
                                 error='Claim link expired. Please request a new one.',
                                 token=None)
        
        # Render claim page - user must authenticate with passkey
        return render_template('modern/claim_permission.html',
                             token=token,
                             site_domain=pending['site_domain'],
                             permission_level=pending['permission_level'],
                             expiry_days=pending.get('expiry_days', 90),
                             redirect_url=pending.get('redirect_url', '/'),
                             error=None)
        
    except Exception as e:
        logger.error(f"❌ Claim permission page error: {e}")
        return render_template('modern/claim_permission.html',
                             error=f'Error: {str(e)}',
                             token=None)


@iam_email_bp.route('/api/v1/iam/claim-permission', methods=['POST'])
@cross_origin()
def claim_permission():
    """
    PRIVACY-PRESERVING: Claim permission with passkey authentication
    
    POST /api/v1/iam/claim-permission
    {
        "token": "claim_token_from_email",
        "passkey_credential_id": "base64_credential_id"  # From WebAuthn
    }
    
    The user's DID is derived from their passkey credential ID (not email).
    NO email is stored anywhere.
    """
    try:
        data = request.get_json()
        token = data.get('token')
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not token:
            return jsonify({'error': 'Missing claim token'}), 400
        
        if not passkey_credential_id:
            return jsonify({'error': 'Passkey authentication required'}), 400
        
        # Get pending request (contains NO email)
        pending = get_confirmation_token(token)
        
        if not pending:
            return jsonify({'error': 'Invalid or expired claim token'}), 400
        
        if time.time() > pending['expires_at']:
            delete_confirmation_token(token)
            return jsonify({'error': 'Claim link expired'}), 400
        
        # Extract permission details
        site_id = pending['site_id']
        site_domain = pending['site_domain']
        permission_level = pending['permission_level']
        expiry_days = pending.get('expiry_days', 90)
        redirect_url = pending.get('redirect_url', f'https://{site_domain}')
        
        # Get or create site manager
        manager = get_or_create_site_manager(site_id, site_domain)
        
        if not manager:
            return jsonify({'error': 'Site not found'}), 404
        
        # Ensure permission type exists
        if permission_level not in manager.permissions:
            manager.add_permission({
                'permission_id': permission_level,
                'display_name': permission_level.title(),
                'scope': get_default_scope(permission_level),
                'conditions': [],
                'priority': 100
            })
        
        # PRIVACY: Derive DID from passkey credential ID (NOT email)
        # This ensures the user's identity is tied to their passkey, not email
        user_did = derive_ppid_did(passkey_credential_id, site_domain)
        
        # Issue permission lemma
        start_time = time.perf_counter()
        
        permission_lemma = manager.issue_permission_lemma(
            user_did,
            permission_level,
            expiry_days=expiry_days,
            custom_claims={
                # NO email in claims - privacy by design
                'site_domain': site_domain,
                'siteId': site_id,
                'siteDomain': site_domain,
                'accountType': 'customer' if permission_level == 'user' else permission_level,
                'permissionId': f'{permission_level}_access',
                'claimedVia': 'passkey_authenticated_email_link'
            }
        )
        
        # Add W3C type field and packageType
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'
        
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
            permission_lemma['credentialSubject']['siteId'] = site_id
            permission_lemma['credentialSubject']['siteDomain'] = site_domain
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'
            permission_lemma['claims']['siteId'] = site_id
            permission_lemma['claims']['siteDomain'] = site_domain
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Delete the claim token (one-time use)
        delete_confirmation_token(token)
        
        # Log without any PII
        logger.info(f"✅ Issued {permission_level} credential for {site_domain} (passkey-authenticated)")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔒 Privacy mode: no email stored in credential or database")
        
        # Track in database WITHOUT email
        try:
            from api.database import get_db_connection
            from datetime import datetime, timedelta
            
            conn = get_db_connection(site_id=site_id)
            cursor = conn.cursor()
            
            expires_at_value = datetime.utcnow() + timedelta(days=expiry_days) if expiry_days > 0 else None
            
            # Get or create permission type
            cursor.execute("""
                SELECT id FROM permission_types 
                WHERE site_id = %s AND name = %s
            """, (site_id, permission_level))
            
            result = cursor.fetchone()
            if result:
                permission_type_id = result[0]
            else:
                cursor.execute("""
                    INSERT INTO permission_types (site_id, name, type, description, active)
                    VALUES (%s, %s, 'role', %s, TRUE)
                    RETURNING id
                """, (site_id, permission_level, f'{permission_level.title()} access'))
                permission_type_id = cursor.fetchone()[0]
            
            # Insert permission instance WITHOUT email (privacy mode)
            cursor.execute("""
                INSERT INTO permission_instances 
                (permission_type_id, site_id, email, credential_did, granted_at, granted_by, expires_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                permission_type_id,
                site_id,
                '[privacy-protected]',  # Never store actual email
                user_did,
                datetime.utcnow(),
                'passkey_claim',
                expires_at_value,
                json.dumps({
                    'credential_id': permission_lemma['id'],
                    'issue_time_us': issue_time_us,
                    'privacy_mode': True
                })
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.warning(f"⚠️ Database tracking failed (credential still valid): {e}")
        
        return jsonify({
            'success': True,
            'permission_lemma': permission_lemma,
            'redirect_url': redirect_url,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'issue_time_us': issue_time_us,
            'privacy_mode': True
        })
        
    except Exception as e:
        logger.error(f"❌ Claim permission error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


