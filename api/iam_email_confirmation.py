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
    logger.info("✅ Using Redis for email confirmation tokens")
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
        
        # Store pending request (in Redis with TTL, expires in 24 hours)
        token_data = {
            'site_id': site_id,
            'site_domain': site_domain,
            'user_email': user_email,
            'permission_level': permission_level,
            'redirect_url': redirect_url,
            'created_at': time.time(),
            'expires_at': time.time() + (24 * 60 * 60)
        }
        store_confirmation_token(confirmation_token, token_data, ttl=86400)
        
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
        
        # Get pending request from Redis
        pending = get_confirmation_token(token)
        
        if not pending:
            logger.warning(f"⚠️ Invalid or expired token attempted: {token[:16]}...")
            return jsonify({
                'error': 'invalid_token',
                'message': 'Invalid or expired confirmation link'
            }), 400
        
        # Check expiration
        if time.time() > pending['expires_at']:
            delete_confirmation_token(token)
            logger.warning(f"⏰ Expired token attempted: {token[:16]}...")
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
            custom_claims={
                'email': user_email,
                'site_domain': site_domain,
                'accountType': 'customer' if permission_level == 'user' else permission_level,
                'permissionId': f'{permission_level}_access'
            }
        )
        
        # Add W3C type field and packageType (same as admin bootstrap)
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'
        
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Clean up pending request (delete from Redis)
        delete_confirmation_token(token)
        
        logger.info(f"✅ Issued {permission_level} credential to {user_email} for {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔐 Credential ID: {permission_lemma['id']}")
        
        # Track credential issuance in database using permission_instances table
        try:
            from api.database import get_db_connection
            from datetime import timedelta
            
            conn = get_db_connection(site_id=site_id)
            cursor = conn.cursor()
            
            # Calculate expiry
            expires_at_value = None
            if expiry_days and expiry_days > 0:
                expires_at_value = datetime.utcnow() + timedelta(days=expiry_days)
            
            # Get or create permission type
            cursor.execute("""
                SELECT id FROM permission_types 
                WHERE site_id = %s AND name = %s
            """, (site_id, permission_level))
            
            result = cursor.fetchone()
            if result:
                permission_type_id = result[0]
            else:
                # Create permission type if doesn't exist
                cursor.execute("""
                    INSERT INTO permission_types (site_id, name, type, description, active)
                    VALUES (%s, %s, 'role', %s, TRUE)
                    RETURNING id
                """, (site_id, permission_level, f'{permission_level.title()} access'))
                permission_type_id = cursor.fetchone()[0]
            
            # Insert permission instance (tracks the grant)
            cursor.execute("""
                INSERT INTO permission_instances 
                (permission_type_id, site_id, email, credential_did, granted_at, granted_by, expires_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                permission_type_id,
                site_id,
                user_email,
                user_did,
                datetime.utcnow(),
                'email_confirmation',
                expires_at_value,
                json.dumps({'credential_id': permission_lemma['id'], 'issue_time_us': issue_time_us})
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"📊 Tracked permission grant in permission_instances table")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to track permission in database (non-critical): {e}")
            # Don't fail the whole flow if tracking fails
        
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


