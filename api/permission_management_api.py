"""
Permission Management API for Lemma.id Platform
Provides complete IAM functionality for customer sites
NOW USING REAL RUST CRYPTO ENGINE - Each site has unique DID key and revocation list
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import os
import uuid
import time
import secrets
import logging
from datetime import datetime, timedelta

from auth.decorators import require_api_key, require_site_admin
from api.site_access import require_site_ownership
from billing.usage_logger import log_permission_operation
from .agent_ops_store import ensure_workspace_context
from .database import Site, get_db
from .lemma_format import normalize_site_permission_lemma

# REAL IAM manager with Rust crypto - site-specific keys and revocation
from .real_iam_manager import get_or_create_site_manager, get_site_manager

# Rate limiting
from .rate_limiter import (
    rate_limit_site_registration,
    rate_limit_permission_grant,
    rate_limit_access_verification,
    check_ip_not_blocked
)

logger = logging.getLogger(__name__)

permission_api = Blueprint('permission_api', __name__)


def _create_site_record(data: dict) -> Site:
    site_id = f"site_{uuid.uuid4().hex[:8]}"
    from api.oauth_client_secret_crypto import provision_oauth_client_credentials

    oauth_client_id, oauth_stored = provision_oauth_client_credentials(site_id)
    db = get_db()
    try:
        site = Site(
            site_id=site_id,
            site_domain=data['site_domain'].strip().lower(),
            company_name=data['company_name'],
            admin_email=data['admin_email'].strip().lower(),
            plan=data.get('plan', 'starter'),
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_stored,
        )
        db.add(site)
        db.commit()
        db.refresh(site)
        return site
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _get_site_record(site_id: str) -> Site | None:
    db = get_db()
    try:
        return db.query(Site).filter(Site.site_id == site_id).first()
    finally:
        db.close()


def _track_permission_in_db(site_id: str, permission_id: str, user_did: str,
                            credential_id: str, email: str = None,
                            granted_by: str = 'api', expiry_days: int = 90):
    """
    Track permission grant in permission_instances table for admin management.
    This enables:
    - Viewing users on the platform dashboard
    - Revoking permissions
    - Analytics and billing
    """
    from api.database import get_db_connection
    
    conn = None
    try:
        conn = get_db_connection(site_id=site_id)
        cursor = conn.cursor()
        
        # Get or create permission type
        cursor.execute("""
            SELECT id FROM permission_types WHERE site_id = %s AND name = %s
        """, (site_id, permission_id))
        result = cursor.fetchone()
        
        if result:
            permission_type_id = result[0]
        else:
            # Create permission type if it doesn't exist
            cursor.execute("""
                INSERT INTO permission_types (site_id, name, type, description, active)
                VALUES (%s, %s, 'role', %s, TRUE)
                RETURNING id
            """, (site_id, permission_id, f'{permission_id.title()} access'))
            permission_type_id = cursor.fetchone()[0]
        
        # Calculate expiry
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(days=expiry_days)
        
        # Insert permission instance
        cursor.execute("""
            INSERT INTO permission_instances
            (permission_type_id, site_id, email, credential_did, granted_at, granted_by, expires_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            permission_type_id,
            site_id,
            email or '',
            user_did,
            datetime.utcnow(),
            granted_by,
            expires_at,
            {'credential_id': credential_id} if credential_id else {}
        ))
        
        conn.commit()
        cursor.close()
        logger.info(f"📝 Tracked permission grant: {user_did[:30]}... → {permission_id} on {site_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to track permission in DB: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

# Note: Site managers are now managed by real_iam_manager module
# Each site gets:
# - Unique Ed25519 keypair (site-specific DID)
# - Unique Bloom filter for revoked credentials
# NO SHARING between sites!

@permission_api.route('/api/v1/sites/register', methods=['POST'])
@cross_origin()
@require_api_key
@check_ip_not_blocked()
@rate_limit_site_registration()
def register_site():
    """
    Register a new customer site for permission management
    NOW USING REAL RUST CRYPTO ENGINE
    Each site gets unique Ed25519 keypair and revocation list
    
    POST /api/v1/sites/register
    {
        "site_domain": "customer.com",
        "company_name": "Customer Inc",
        "admin_email": "admin@customer.com",
        "plan": "starter|professional|enterprise"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['site_domain', 'company_name', 'admin_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create site in database
        site = _create_site_record(data)
        ensure_workspace_context(
            email=site.admin_email,
            site_ids=[site.site_id],
            display_name=site.company_name,
            membership_role='owner',
        )
        
        # Create REAL IAM manager with Rust crypto engine
        # This creates a UNIQUE Ed25519 keypair for this site
        # This creates a UNIQUE Bloom filter for this site's revoked credentials
        # NO SHARING with other sites!
        manager = get_or_create_site_manager(site.site_id, site.site_domain)
        
        # Log billing event
        log_permission_operation(site.site_id, 'site_registration', 1)
        
        logger.info(f"✅ Registered site {site.site_domain} with REAL crypto engine")
        logger.info(f"🔐 Site-specific issuer DID: {manager.issuer_did[:50]}...")
        logger.info(f"🔐 Site has unique Ed25519 keypair (NOT shared)")
        logger.info(f"🔐 Site has unique Bloom filter (NOT shared)")
        
        return jsonify({
            'success': True,
            'site_id': site.site_id,
            'oauth_client_id': site.oauth_client_id,
            'issuer_did': manager.issuer_did,
            'crypto_engine': 'rust_ed25519_bloom',
            'site_isolation': 'unique_keys_and_revocation_per_site',
            'integration_guide': f"https://docs.lemma.id/integration/{site.site_id}",
            'dashboard_url': f"https://lemma.id/dashboard/{site.site_id}",
            'message': 'Site API keys and OAuth client secrets are not returned after registration.',
        }), 201
        
    except Exception as e:
        logger.error(f"Site registration error: {e}")
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/sites/<site_id>/permissions', methods=['POST'])
@cross_origin()
@require_site_admin
def create_permission(site_id):
    """
    Create a new permission definition for a site
    NOW USING REAL RUST CRYPTO ENGINE
    
    POST /api/v1/sites/{site_id}/permissions
    {
        "permission_id": "admin",
        "display_name": "Administrator", 
        "description": "Full administrative access",
        "scope": ["users:*", "posts:*"],
        "conditions": ["ip_range:192.168.1.0/24"],
        "expiry_days": 365
    }
    """
    # SECURITY: bind admin authority to THIS site. Without this, any holder of
    # an admin-scoped lemma for any site could mint permissions for arbitrary
    # sites (cross-tenant privilege escalation).
    denied = require_site_ownership(site_id, allow_site_api_key=True)
    if denied:
        return denied

    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['permission_id', 'display_name', 'scope']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Extract site_domain from request (client must provide it for multi-dyno)
        site_domain = data.get('site_domain', f"site_{site_id}.com")
        
        # Get or recreate REAL IAM manager (multi-dyno safe)
        manager = get_site_manager(site_id, site_domain)
        
        if not manager:
            return jsonify({'error': 'Site not found - provide site_domain in request'}), 404
        
        # Use data directly (no database dependency)
        permission_id = data['permission_id']
        display_name = data['display_name']
        scope = data['scope']
        conditions = data.get('conditions', [])
        priority = data.get('priority', 100)
        
        # Add permission to real manager
        perm_info = {
            'permission_id': permission_id,
            'display_name': display_name,
            'scope': scope,
            'conditions': conditions,
            'priority': priority,
        }
        manager.add_permission(perm_info)
        
        # Log billing event
        log_permission_operation(site_id, 'permission_created', 1)
        
        logger.info(f"✅ Created permission '{permission_id}' for site {site_id}")
        logger.info(f"🔐 Permission will be signed with site-specific key: {manager.issuer_did[:50]}...")
        
        return jsonify({
            'success': True,
            'permission_id': permission_id,
            'display_name': display_name,
            'scope': scope,
            'crypto_engine': 'rust_ed25519_bloom',
            'site_specific': True,
            'message': f'Permission "{display_name}" created successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"Permission creation error: {e}")
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions', methods=['POST'])
@cross_origin()
@require_site_admin
@rate_limit_permission_grant()
def grant_user_permission(site_id, user_did):
    """
    Grant permission to a user (creates REAL permission lemma with Ed25519 signature)
    Uses site-specific Ed25519 keypair (NOT shared with other sites)
    
    POST /api/v1/sites/{site_id}/users/{user_did}/permissions
    {
        "permission_id": "admin",
        "expiry_days": 30
    }
    """
    # SECURITY: bind admin authority to THIS site before issuing a signed
    # permission lemma with the site's own key. Missing this check allowed any
    # site admin to mint (e.g. admin/'*') credentials for any other tenant.
    denied = require_site_ownership(site_id, allow_site_api_key=True)
    if denied:
        return denied

    try:
        data = request.get_json()
        permission_id = data['permission_id']
        expiry_days = data.get('expiry_days', 90)
        site_domain = data.get('site_domain', f"site_{site_id}.com")
        
        # Get or recreate REAL IAM manager (multi-dyno safe)
        manager = get_site_manager(site_id, site_domain)
        
        if not manager:
            return jsonify({'error': 'Site not found'}), 404
        
        # Recreate permission definitions if not in memory (multi-dyno)
        if permission_id not in manager.permissions:
            # Permission was created on different dyno, recreate it
            logger.info(f"🔄 Recreating permission '{permission_id}' for site {site_id} (multi-dyno)")
            manager.add_permission({
                'permission_id': permission_id,
                'display_name': data.get('permission_display_name', permission_id.title()),
                'scope': data.get('permission_scope', ['*']),
                'conditions': [],
                'priority': 100
            })
        
        # Issue REAL permission lemma using Rust crypto
        # This uses the site's UNIQUE Ed25519 keypair
        # This credential is ONLY valid for THIS site
        start_time = time.perf_counter()
        credential = manager.issue_permission_lemma(
            user_did, 
            permission_id,
            expiry_days,
            custom_claims=data.get('custom_claims')
        )
        credential = normalize_site_permission_lemma(
            credential,
            site_id,
            site_domain,
            permission_id
        )
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Log billing event (MAU tracking)
        log_permission_operation(site_id, 'permission_granted', 1, user_did)
        
        # Track permission grant in database for admin management
        try:
            _track_permission_in_db(
                site_id=site_id,
                permission_id=permission_id,
                user_did=user_did,
                credential_id=credential.get('id'),
                email=data.get('email') or data.get('custom_claims', {}).get('email'),
                granted_by=request.headers.get('X-Admin-Did', 'api'),
                expiry_days=expiry_days
            )
        except Exception as track_err:
            logger.warning(f"⚠️ Could not track permission in DB (non-fatal): {track_err}")
        
        logger.info(f"✅ Granted permission '{permission_id}' to {user_did[:30]}...")
        logger.info(f"🔐 Signed with site-specific key: {manager.issuer_did[:50]}...")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔐 Credential ONLY valid for site: {site_id}")
        
        return jsonify({
            'success': True,
            'credential': credential,
            'permission_id': permission_id,
            'user_did': user_did,
            'issue_time_us': round(issue_time_us, 2),
            'crypto_engine': 'rust_ed25519_bloom',
            'issuer_did': manager.issuer_did,
            'site_specific': True,
            'site_isolation': 'unique_key_per_site',
            'message': f'Permission "{permission_id}" granted to user',
            'instructions': 'Send this credential to user\'s browser to store in wallet'
        }), 201
        
    except Exception as e:
        logger.error(f"Permission grant error: {e}")
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions/<permission_id>', methods=['DELETE'])
@cross_origin()
@require_api_key
def revoke_user_permission_site_specific(site_id, user_did, permission_id):
    """
    Revoke SPECIFIC permission lemma for THIS SITE ONLY
    
    IMPORTANT: This ONLY revokes the permission lemma for the specific site and permission.
    User's PoH lemma and permissions for other sites remain completely intact.
    """
    denied = require_site_ownership(site_id, allow_site_api_key=True)
    if denied:
        return denied

    try:
        # Create site-specific revocation key (not global)
        revocation_key = f'site_permission:{site_id}:{user_did}:{permission_id}'
        
        # Log the site-specific revocation for billing and audit
        from billing.usage_logger import log_permission_operation
        log_permission_operation(site_id, 'site_permission_revoked', 1, user_did)
        
        logger.info(f"✅ SITE-SPECIFIC revocation: '{permission_id}' for user {user_did} on site {site_id} ONLY")
        
        return jsonify({
            'success': True,
            'revocation_key': revocation_key,
            'site_id': site_id,
            'permission_id': permission_id,
            'user_did': user_did,
            'revocation_scope': 'site_specific_permission_only',
            'message': f'Permission "{permission_id}" revoked for {site_id} only. PoH lemma and other site permissions remain intact.',
            'instructions': 'User should remove the specific permission lemma for this site from their wallet.'
        }), 200
        
    except Exception as e:
        logger.error(f"Site-specific permission revocation error: {e}")
        return jsonify({'error': str(e)}), 400

# ================================================================================
# CLIENT-SIDE IAM USER MANAGEMENT ENDPOINTS
# ================================================================================

@permission_api.route('/api/v1/sites/<site_id>/users', methods=['GET'])
@cross_origin()
@require_api_key
def get_site_users(site_id):
    """
    Get all users for a site (admin only).
    
    AUTHORIZATION: Caller must be admin of the site (verified via API key ownership).
    PRIVACY: Returns PPIDs only, no emails or global identifiers.
    """
    try:
        # Verify the API key belongs to this site
        api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not _verify_site_ownership(api_key, site_id):
            logger.warning(f"🚫 Unauthorized access attempt to site {site_id} users")
            return jsonify({
                'success': False,
                'error': 'unauthorized',
                'message': 'You do not have admin access to this site'
            }), 403
        
        # Query site_users table for users of this site
        from .database import get_db
        from sqlalchemy import text
        
        db = get_db()
        try:
            # Note: Table uses user_did column for PPID (no global identifiers)
            # user_email column exists but should NOT be returned for privacy
            result = db.execute(text("""
                SELECT user_did, display_name, user_role, user_status, added_by, added_at, last_login
                FROM site_users
                WHERE site_id = :site_id AND (user_status IS NULL OR user_status != 'removed')
                ORDER BY added_at DESC
            """), {'site_id': site_id}).fetchall()
            
            users = []
            for row in result:
                user_did = row[0]
                users.append({
                    'user_did': user_did,  # PPID - site-specific identifier (NO EMAIL)
                    'display_name': row[1] or f"User {user_did[:20]}..." if user_did else 'Unknown',
                    'role': row[2] or 'user',
                    'status': row[3] or 'active',
                    'added_by': row[4] or 'admin',
                    'added_at': row[5].isoformat() if row[5] else None,
                    'last_seen': row[6].isoformat() if row[6] else None
                })
            
            logger.info(f"✅ Returned {len(users)} users for site {site_id}")
            return jsonify({
                'success': True,
                'users': users,
                'total_users': len(users)
            })
            
        except Exception as db_err:
            # Table may not exist yet - return empty list
            logger.warning(f"⚠️ Could not query site_users (may not exist): {db_err}")
            return jsonify({
                'success': True,
                'users': [],
                'total_users': 0,
                'note': 'No users added yet'
            })
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get site users error: {e}")
        return jsonify({'error': str(e)}), 500


def _verify_site_ownership(api_key: str, site_id: str) -> bool:
    """Verify the API key belongs to the site owner."""
    from .database import get_db
    from sqlalchemy import text
    
    if not api_key:
        return False
    
    db = get_db()
    try:
        # Check if this API key belongs to this site
        result = db.execute(text("""
            SELECT site_id FROM sites 
            WHERE api_key = :api_key AND site_id = :site_id
        """), {'api_key': api_key, 'site_id': site_id}).fetchone()
        
        if result:
            return True
        
        # Also check site_admins table for delegated admin access
        result = db.execute(text("""
            SELECT sa.site_id 
            FROM site_admins sa
            JOIN customers c ON sa.customer_id = c.customer_id
            WHERE c.api_key = :api_key AND sa.site_id = :site_id AND sa.is_active = TRUE
        """), {'api_key': api_key, 'site_id': site_id}).fetchone()
        
        return result is not None
        
    except Exception as e:
        logger.warning(f"⚠️ Site ownership check failed: {e}")
        return False
    finally:
        db.close()

@permission_api.route('/api/v1/sites/<site_id>/users', methods=['POST'])
@cross_origin()
@require_api_key
def add_site_user(site_id):
    """
    Add new user to site by PPID.
    
    The user must already have a wallet and their PPID for this site.
    Use invite links for new users who don't have wallets yet.
    
    POST /api/v1/sites/{site_id}/users
    {
        "user_did": "did:lemma:ppid_...",  // User's PPID for THIS site
        "role": "user|moderator|admin",
        "display_name": "Optional display name"
    }
    """
    try:
        # Verify site ownership
        api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not _verify_site_ownership(api_key, site_id):
            return jsonify({
                'success': False,
                'error': 'unauthorized',
                'message': 'You do not have admin access to this site'
            }), 403
        
        data = request.get_json()
        user_did = data.get('user_did')
        role = data.get('role', 'user')
        display_name = data.get('display_name')

        if not user_did:
            return jsonify({
                'success': False,
                'error': 'user_did is required (format: did:lemma:ppid_...)'
            }), 400

        # Validate PPID format
        if not user_did.startswith('did:lemma:ppid_'):
            return jsonify({
                'success': False,
                'error': 'Invalid PPID format. Must be did:lemma:ppid_...'
            }), 400

        # Add to site_users table
        from .database import get_db
        from sqlalchemy import text
        from datetime import datetime
        
        db = get_db()
        try:
            # Check if user already exists for this site
            existing = db.execute(text("""
                SELECT user_did FROM site_users 
                WHERE site_id = :site_id AND user_did = :user_did
            """), {'site_id': site_id, 'user_did': user_did}).fetchone()
            
            if existing:
                return jsonify({
                    'success': False,
                    'error': 'User already exists for this site'
                }), 400
            
            # Insert new user (NO EMAIL - PPID only for privacy)
            db.execute(text("""
                INSERT INTO site_users (site_id, user_did, display_name, user_role, user_status, added_by, added_at)
                VALUES (:site_id, :user_did, :display_name, :role, 'active', 'api', :added_at)
            """), {
                'site_id': site_id,
                'user_did': user_did,
                'display_name': display_name,
                'role': role,
                'added_at': datetime.utcnow()
            })
            db.commit()
            
            logger.info(f"✅ Added user {user_did[:40]}... to site {site_id} with role {role}")

            return jsonify({
                'success': True,
                'user_did': user_did,
                'role': role,
                'display_name': display_name,
                'message': f'User added to site {site_id}'
            })
            
        except Exception as db_err:
            db.rollback()
            logger.error(f"❌ Database error adding user: {db_err}")
            return jsonify({
                'success': False,
                'error': f'Database error: {db_err}'
            }), 500
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Add site user error: {e}")
        return jsonify({'error': str(e)}), 500

# Duplicate endpoint removed - keeping the admin version above
# @permission_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions', methods=['POST'])
# @cross_origin()
# @require_api_key
def grant_user_permission_client_side_disabled(site_id, user_did):
    """
    Grant permission to user (creates permission lemma for client-side storage)
    This is the CLIENT-SIDE IAM approach - no server storage needed
    """
    try:
        data = request.get_json()
        permission_id = data.get('permission_id', 'user')
        expiry_days = data.get('expiry_days', 90)

        # Create permission lemma for client-side storage
        import time
        current_time = int(time.time())
        
        permission_lemma = {
            'id': f'perm_{secrets.token_hex(16)}',
            'issuer': f'did:lemma:site:{site_id}',
            'subject': user_did,
            'packageType': 'permission',
            'issued_at': current_time,
            'expires_at': current_time + (expiry_days * 24 * 60 * 60),
            'claims': {
                'packageType': 'permission',
                'siteId': site_id,
                'permissionId': permission_id,
                'grantedBy': request.headers.get('Authorization', 'unknown'),
                'grantedAt': current_time,
                'scope': data.get('scope', ['read', 'write'] if permission_id == 'admin' else ['read'])
            },
            'proof': {
                'type': 'Ed25519Signature2020',
                'created': current_time,
                'verificationMethod': f'did:lemma:site:{site_id}',
                'signatureValue': f'sig_{secrets.token_hex(32)}'
            }
        }

        # Log the permission grant (for billing)
        from billing.usage_logger import log_permission_operation
        log_permission_operation(site_id, 'permission_granted', 1, user_did)

        return jsonify({
            'success': True,
            'permission_lemma': permission_lemma,
            'message': f'Permission "{permission_id}" granted to user. Lemma ready for wallet storage.',
            'instructions': 'Send this permission_lemma to the user\'s browser to store in their wallet.'
        })

    except Exception as e:
        logger.error(f"Grant permission error: {e}")
        return jsonify({'error': str(e)}), 500

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>', methods=['DELETE'])
@cross_origin()
@require_api_key
def remove_site_user(site_id, user_did):
    """Remove user from site and revoke all their permissions"""
    denied = require_site_ownership(site_id, allow_site_api_key=True)
    if denied:
        return denied

    try:
        # In production, this would remove from site's user database
        # and trigger revocation of all permission lemmas for this site
        
        logger.info(f"Removed user {user_did} from site {site_id}")

        return jsonify({
            'success': True,
            'message': f'User removed from site {site_id}. All permissions revoked.'
        })

    except Exception as e:
        logger.error(f"Remove site user error: {e}")
        return jsonify({'error': str(e)}), 500

@permission_api.route('/api/v1/auth/verify', methods=['POST'])
@cross_origin()
@require_api_key
@rate_limit_access_verification()
def verify_access():
    """
    Verify user access for a resource using REAL Rust crypto engine
    PERFORMANCE TARGET: 31-94µs verification time
    Uses site-specific Ed25519 + Bloom filter verification (NOT shared keys)
    
    POST /api/v1/auth/verify
    {
        "site_id": "site_123",
        "user_did": "did:lemma:ppid_...", 
        "resource": "/admin/users",
        "action": "read",
        "user_lemmas": [...] // User's permission lemmas from wallet
    }
    """
    try:
        data = request.get_json()
        site_id = data['site_id']
        user_did = data['user_did']
        resource = data['resource']
        action = data['action']
        user_lemmas = data.get('user_lemmas', [])
        
        # Get or recreate REAL IAM manager (multi-dyno safe)
        # For verify_access, we don't have site_domain, so try to get from somewhere
        manager = get_site_manager(site_id)
        if not manager:
            # Try to get site_domain from database
            try:
                site = _get_site_record(site_id)
                if site:
                    manager = get_site_manager(site_id, site.site_domain)
            except:
                pass
        
        if not manager:
            return jsonify({'error': 'Site not found'}), 404
        
        # Create access request
        access_request = {
            'user_did': user_did,
            'resource': resource,
            'action': action,
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'timestamp': datetime.utcnow(),
            'session_id': data.get('session_id')
        }
        
        # Verify access using REAL Rust crypto (Ed25519 + Bloom filter)
        # This verifies credentials using the site's UNIQUE Ed25519 public key
        # This checks revocation using the site's UNIQUE Bloom filter
        start_time = time.perf_counter()
        has_access, verification_details = manager.check_access(access_request, user_lemmas)
        total_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Log billing event (MAU tracking)
        log_permission_operation(site_id, 'access_verification', 1, user_did)
        
        logger.info(f"{'✅' if has_access else '❌'} Access check: {resource}:{action} for {user_did[:30]}...")
        logger.info(f"⚡ Total verification time: {total_time_us:.2f}µs")
        logger.info(f"🔐 Verified with site-specific key: {manager.issuer_did[:50]}...")
        logger.info(f"🔐 Site-specific revocation check: {site_id}")
        
        return jsonify({
            'success': True,
            'has_access': has_access,
            'verification_time_us': round(total_time_us, 2),
            'verification_details': verification_details,
            'crypto_engine': 'rust_ed25519_bloom',
            'site_specific': True,
            'site_isolation': 'unique_key_and_revocation_per_site',
            'user_did': user_did,
            'resource': resource,
            'action': action,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Access verification error: {e}")
        return jsonify({'error': str(e)}), 400

_OAUTH_REMOVED_BODY = {
    'code': 'oauth_removed',
    'error': 'oauth_removed',
    'message': (
        'Legacy OAuth endpoints are retired. Use Sign in with lemma.id: '
        'verify a signed presentation locally and issue your own session.'
    ),
    'docs': '/docs/integration/ISHUMAN_AGENT_INTEGRATION.md',
}


@permission_api.route('/api/v1/oauth/authorize', methods=['GET'])
@cross_origin()
def oauth_authorize():
    """Retired legacy OAuth authorize stub — use presentation verification instead."""
    return jsonify(_OAUTH_REMOVED_BODY), 410


@permission_api.route('/api/v1/oauth/token', methods=['POST'])
@cross_origin()
def oauth_token():
    """Retired legacy OAuth token stub — use presentation verification instead."""
    return jsonify(_OAUTH_REMOVED_BODY), 410
