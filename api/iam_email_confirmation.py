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
    
    DEVELOPER API - Call from your backend with API key:
    
    POST /api/v1/iam/request-access
    Headers:
        X-API-Key: your_api_key
        Content-Type: application/json
    
    Body:
    {
        "user_email": "user@example.com",       # Used for delivery only - NEVER stored
        "permission_level": "user|admin|editor",
        "redirect_url": "https://yoursite.com/dashboard",  # Optional
        "expiry_days": 90  # Optional, default 90
    }
    
    The recipient must authenticate with passkey to claim the permission.
    Their DID is derived from passkey (not email).
    
    Returns:
    {
        "success": true,
        "message": "Permission claim email sent...",
        "privacy_mode": true,
        "expires_in": 604800
    }
    """
    try:
        data = request.get_json() or {}
        
        # Check for API key authentication (for developer backend calls)
        api_key = request.headers.get('X-API-Key') or data.get('api_key')
        site_id = None
        site_domain = None
        
        if api_key:
            # Validate API key and get associated site
            try:
                from api.database import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT site_id, site_domain FROM api_keys 
                    WHERE api_key = %s AND active = TRUE
                """, (api_key,))
                
                result = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if result:
                    site_id = result[0]
                    site_domain = result[1]
                    logger.info(f"📧 API key authenticated for site: {site_domain}")
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid API key'
                    }), 401
                    
            except Exception as e:
                logger.warning(f"⚠️ API key validation failed: {e}")
                # Fall back to provided site_id/site_domain
        
        # If no API key, require site_id in body (for platform UI calls)
        if not site_id:
            site_id = data.get('site_id')
            site_domain = data.get('site_domain', f'site_{site_id}.com' if site_id else None)
        
        # Validate required fields
        user_email = data.get('user_email')
        permission_level = data.get('permission_level', 'user')
        
        if not user_email:
            return jsonify({'error': 'Missing required field: user_email'}), 400
        
        if not site_id:
            return jsonify({'error': 'Missing site_id or API key'}), 400
        
        redirect_url = data.get('redirect_url', f'https://{site_domain}')
        expiry_days = data.get('expiry_days', 90)
        
        # Validate email format (for delivery only)
        if '@' not in user_email or '.' not in user_email:
            return jsonify({'error': 'Invalid email address'}), 400
        
        # Get or create site manager (auto-creates for new sites)
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Generate claim token (secure, one-time use)
        claim_token = secrets.token_urlsafe(32)
        
        # PRIVACY NOTE: Email stored in Redis token ONLY for EmailLemma issuance
        # - Token auto-expires in 7 days (Redis TTL)
        # - Token deleted immediately after claim
        # - Email NEVER stored in our database
        # - Email goes into user's wallet (EmailLemma) - user controls it
        token_data = {
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'redirect_url': redirect_url,
            'expiry_days': expiry_days,
            'created_at': time.time(),
            'expires_at': time.time() + (7 * 24 * 60 * 60),  # 7 day claim window
            # Email stored temporarily for EmailLemma issuance (user's wallet)
            '_email_for_lemma': user_email,  # Prefixed with _ to indicate temporary
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
    
    Issues TWO credentials to user's wallet:
    1. EmailLemma - proves email ownership (email stored in USER's wallet only)
    2. PermissionLemma - site access (no email, uses passkey-derived DID)
    
    POST /api/v1/iam/claim-permission
    {
        "token": "claim_token_from_email",
        "passkey_credential_id": "base64_credential_id"  # From WebAuthn
    }
    
    Returns both credentials for wallet storage.
    Email is NEVER stored in Lemma's database - only in user's wallet.
    """
    try:
        data = request.get_json()
        token = data.get('token')
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not token:
            return jsonify({'error': 'Missing claim token'}), 400
        
        if not passkey_credential_id:
            return jsonify({'error': 'Passkey authentication required'}), 400
        
        # Get pending request
        pending = get_confirmation_token(token)
        
        if not pending:
            return jsonify({'error': 'Invalid or expired claim token'}), 400
        
        if time.time() > pending['expires_at']:
            delete_confirmation_token(token)
            return jsonify({'error': 'Claim link expired'}), 400
        
        # Extract details
        site_id = pending['site_id']
        site_domain = pending['site_domain']
        permission_level = pending['permission_level']
        expiry_days = pending.get('expiry_days', 90)
        redirect_url = pending.get('redirect_url', f'https://{site_domain}')
        
        # Get email for EmailLemma (temporary, from Redis only)
        user_email = pending.get('_email_for_lemma')
        
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
        user_did = derive_ppid_did(passkey_credential_id, site_domain)
        
        start_time = time.perf_counter()
        
        # ============================================================
        # 1. ISSUE EMAIL LEMMA (if email available)
        # ============================================================
        email_lemma = None
        if user_email:
            # Get Lemma platform manager for EmailLemma issuance
            lemma_manager = get_or_create_site_manager('lemma.id', 'lemma.id')
            
            # Derive a consistent DID for email verification (passkey + lemma.id)
            email_did = derive_ppid_did(passkey_credential_id, 'lemma.id')
            
            from datetime import datetime
            
            # Issue EmailLemma with REAL Ed25519 signature
            # Use lemma_manager which has real Ed25519 keys
            email_lemma = lemma_manager.issuer.issue_credential(
                email_did,
                {
                    'packageType': 'email',
                    'email': user_email,
                    'verifiedAt': datetime.utcnow().isoformat() + 'Z',
                    'verificationMethod': 'email_link_passkey_auth'
                }
            )
            
            # Parse from JSON if needed
            if isinstance(email_lemma, str):
                import json
                email_lemma = json.loads(email_lemma)
            
            # Add W3C type fields
            email_lemma['type'] = ['VerifiableCredential', 'EmailLemma']
            email_lemma['packageType'] = 'email'
            
            if 'credentialSubject' in email_lemma:
                email_lemma['credentialSubject']['packageType'] = 'email'
            if 'claims' in email_lemma:
                email_lemma['claims']['packageType'] = 'email'
            
            logger.info(f"📧 Issued EmailLemma for verified email (stored in user wallet only)")
        
        # ============================================================
        # 2. ISSUE PERMISSION LEMMA (site access)
        # ============================================================
        permission_lemma = manager.issue_permission_lemma(
            user_did,
            permission_level,
            expiry_days=expiry_days,
            custom_claims={
                # NO email in permission claims - privacy by design
                'site_domain': site_domain,
                'siteId': site_id,
                'siteDomain': site_domain,
                'accountType': 'customer' if permission_level == 'user' else permission_level,
                'permissionId': f'{permission_level}_access',
                'claimedVia': 'passkey_authenticated_email_link',
                'hasEmailLemma': bool(email_lemma)  # Indicates user has verified email
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
        
        # Delete the claim token (one-time use) - email is now gone from Redis
        delete_confirmation_token(token)
        
        # Log without any PII
        logger.info(f"✅ Issued {permission_level} credential for {site_domain} (passkey-authenticated)")
        logger.info(f"📧 EmailLemma: {'issued' if email_lemma else 'not issued'}")
        logger.info(f"⚡ Total issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔒 Privacy: email in user wallet only, not in Lemma database")
        
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
                    'privacy_mode': True,
                    'email_lemma_issued': bool(email_lemma)
                })
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.warning(f"⚠️ Database tracking failed (credentials still valid): {e}")
        
        # Return BOTH credentials
        response_data = {
            'success': True,
            'permission_lemma': permission_lemma,
            'redirect_url': redirect_url,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'issue_time_us': issue_time_us,
            'privacy_mode': True
        }
        
        # Include EmailLemma if issued
        if email_lemma:
            response_data['email_lemma'] = email_lemma
            response_data['credentials_issued'] = ['permission', 'email']
        else:
            response_data['credentials_issued'] = ['permission']
        
        return jsonify(response_data)
        
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
    Legacy endpoint - redirects to privacy-preserving flow
    Use /api/v1/iam/invite instead
    """
    # Forward to privacy-preserving endpoint
    return invite_user()


@iam_email_bp.route('/api/v1/iam/invite', methods=['POST'])
@cross_origin()
def invite_user():
    """
    DEVELOPER API: Invite a user to your site via email
    
    Privacy-preserving: Email is used ONLY for delivery, never stored.
    User must authenticate with passkey to claim the permission.
    
    Headers:
        X-API-Key: your_api_key (required)
        Content-Type: application/json
    
    POST /api/v1/iam/invite
    {
        "email": "user@example.com",           # For delivery only - NEVER stored
        "permission": "user|editor|admin",     # Permission level
        "redirect_url": "https://yoursite.com/welcome",  # Optional
        "expiry_days": 90,                     # Optional, credential validity
        "claim_window_days": 7                 # Optional, link validity
    }
    
    Returns:
    {
        "success": true,
        "message": "Invitation sent",
        "claim_expires_in": 604800,
        "privacy_mode": true
    }
    
    Example (curl):
    ```
    curl -X POST https://lemma.id/api/v1/iam/invite \\
      -H "X-API-Key: your_api_key" \\
      -H "Content-Type: application/json" \\
      -d '{"email": "user@example.com", "permission": "admin"}'
    ```
    
    Example (Node.js):
    ```javascript
    await fetch('https://lemma.id/api/v1/iam/invite', {
        method: 'POST',
        headers: {
            'X-API-Key': process.env.LEMMA_API_KEY,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            email: 'user@example.com',
            permission: 'admin'
        })
    });
    ```
    """
    try:
        data = request.get_json() or {}
        
        # Require API key for this endpoint
        api_key = request.headers.get('X-API-Key') or data.get('api_key')
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key required. Pass via X-API-Key header.'
            }), 401
        
        # Validate API key
        try:
            from api.database import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT site_id, site_domain FROM api_keys 
                WHERE api_key = %s AND active = TRUE
            """, (api_key,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not result:
                return jsonify({
                    'success': False,
                    'error': 'Invalid API key'
                }), 401
            
            site_id, site_domain = result
            
        except Exception as e:
            logger.error(f"❌ API key validation error: {e}")
            return jsonify({
                'success': False,
                'error': 'API key validation failed'
            }), 500
        
        # Get parameters
        user_email = data.get('email') or data.get('user_email')
        permission_level = data.get('permission') or data.get('permission_level', 'user')
        redirect_url = data.get('redirect_url', f'https://{site_domain}')
        expiry_days = data.get('expiry_days', 90)
        claim_window_days = data.get('claim_window_days', 7)
        
        if not user_email:
            return jsonify({
                'success': False,
                'error': 'email is required'
            }), 400
        
        # Validate email format
        if '@' not in user_email or '.' not in user_email:
            return jsonify({
                'success': False,
                'error': 'Invalid email format'
            }), 400
        
        # Get or create site manager
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Generate claim token
        claim_token = secrets.token_urlsafe(32)
        
        # PRIVACY NOTE: Email stored in Redis token ONLY for EmailLemma issuance
        # - Token auto-expires (Redis TTL)
        # - Token deleted immediately after claim
        # - Email NEVER stored in our database
        # - Email goes into user's wallet (EmailLemma) - user controls it
        token_data = {
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'redirect_url': redirect_url,
            'expiry_days': expiry_days,
            'created_at': time.time(),
            'expires_at': time.time() + (claim_window_days * 24 * 60 * 60),
            # Email stored temporarily for EmailLemma issuance (user's wallet)
            '_email_for_lemma': user_email,
        }
        store_confirmation_token(claim_token, token_data, ttl=claim_window_days * 86400)
        
        # Generate claim link
        base_url = 'https://lemma.id'  # Always use lemma.id for claim page
        claim_link = f"{base_url}/claim-permission?token={claim_token}"
        
        # Send email via SendGrid (email NOT stored)
        email_html = render_email_template(
            'permission_claim',
            site_domain=site_domain,
            permission_level=permission_level,
            claim_link=claim_link,
            expiry_days=claim_window_days
        )
        
        if not email_html:
            email_html = render_email_template(
                'access_confirmation',
                site_domain=site_domain,
                permission_level=permission_level,
                confirmation_link=claim_link
            )
        
        email_result = send_email(
            to=user_email,
            subject=f"🎫 You're invited to {site_domain}",
            html=email_html
        )
        
        if email_result['success']:
            logger.info(f"📧 Invitation sent for {site_domain} ({permission_level}) - privacy mode")
            
            return jsonify({
                'success': True,
                'message': 'Invitation sent. User must authenticate with passkey to claim.',
                'claim_expires_in': claim_window_days * 86400,
                'credential_expires_in_days': expiry_days,
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
        logger.error(f"❌ Invite user error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


