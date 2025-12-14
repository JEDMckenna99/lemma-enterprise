"""
Platform Statistics API
Provides real-time stats for the developer platform
"""

import os
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from sqlalchemy import func, and_, or_

from api.database import get_db_connection
from api.usage_tracking import get_monthly_active_users, get_verification_count

logger = logging.getLogger(__name__)

platform_stats_bp = Blueprint('platform_stats', __name__)


@platform_stats_bp.route('/api/platform/stats', methods=['GET'])
def get_platform_stats():
    """
    Get platform statistics for the developer dashboard
    
    Returns:
        {
            "mau": int,                    # Monthly active users
            "total_verifications": int,    # Verifications this month
            "active_users": int,           # Total users with active permissions
            "registered_sites": int,       # Number of sites registered
            "recent_activity": []          # Last 5 events
        }
    """
    conn = None
    cursor = None
    try:
        current_month = datetime.now().strftime('%Y-%m')
        
        # For lemma.id platform, we track users for 'lemma_platform' site
        site_id = 'lemma_platform'
        
        # 1. Get MAU (from Redis via usage_tracking)
        mau_count = get_monthly_active_users(site_id)
        logger.info(f"📊 MAU for {site_id}: {mau_count}")
        
        # 2. Get total verifications this month (from Redis)
        verification_count = get_verification_count(site_id)
        logger.info(f"📊 Verifications for {site_id}: {verification_count}")
        
        # 3. Get active users count (from database - permission_instances table)
        conn = get_db_connection(site_id=site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM permission_instances
            WHERE site_id = %s 
            AND revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > NOW())
        """, (site_id,))
        
        active_users = cursor.fetchone()[0]
        logger.info(f"📊 Active users for {site_id}: {active_users}")
        
        # 4. Get registered sites count (from database - sites table)
        cursor.execute("SELECT COUNT(*) FROM sites")
        registered_sites = cursor.fetchone()[0]
        logger.info(f"📊 Registered sites: {registered_sites}")
        
        # 5. Get recent activity (last 5 permission grants from permission_instances)
        cursor.execute("""
            SELECT pi.email, pt.name as permission_name, pi.granted_at
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.site_id = %s
            ORDER BY pi.granted_at DESC
            LIMIT 5
        """, (site_id,))
        
        recent_activity = []
        for row in cursor.fetchall():
            email, permission_name, granted_at = row
            
            recent_activity.append({
                'type': 'permission_granted',
                'user': email if len(email) < 30 else email[:27] + '...',
                'permission': permission_name,
                'timestamp': granted_at.isoformat() if granted_at else None,
                'time_ago': get_time_ago(granted_at) if granted_at else 'Unknown'
            })
        
        logger.info(f"📊 Recent activity: {len(recent_activity)} events")
        
        return jsonify({
            'success': True,
            'stats': {
                'mau': mau_count,
                'total_verifications': verification_count,
                'active_users': active_users,
                'registered_sites': registered_sites
            },
            'recent_activity': recent_activity,
            'site_id': site_id,
            'month': current_month
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get platform stats: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'stats': {
                'mau': 0,
                'total_verifications': 0,
                'active_users': 0,
                'registered_sites': 0
            },
            'recent_activity': []
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@platform_stats_bp.route('/api/platform/users', methods=['GET', 'POST'])
def get_platform_users():
    """
    Get all users with permissions for the caller's site
    
    - Lemma.id admins see lemma_platform users
    - Site owners see their own site's users
    - Looks up site ownership via admin_email
    
    POST body (optional):
    {
        "user_credential": {...}  // Caller's credential to determine their site
    }
    
    Returns:
        {
            "users": [...],
            "site_id": "the_site_id",
            "site_domain": "the domain"
        }
    """
    conn = None
    cursor = None
    try:
        # Determine which site's users to show
        site_id = 'lemma_platform'  # Default for admins
        site_domain = 'lemma.id'
        user_email = None
        is_lemma_admin = False
        
        # Get caller's credential to determine their site
        if request.method == 'POST':
            data = request.get_json() or {}
            user_credential = data.get('user_credential')
            if user_credential:
                claims = user_credential.get('claims') or user_credential.get('credentialSubject') or {}
                user_email = claims.get('email')
                permission_id = claims.get('permissionId') or claims.get('permission_level') or ''
                
                # Check if this is a lemma.id admin
                admin_permissions = ['admin_access', 'super_admin', 'site_admin', 'admin']
                is_lemma_admin = permission_id in admin_permissions
        else:
            # GET request - try to get email from query param
            user_email = request.args.get('email')
        
        # If not a lemma.id admin, look up their site(s)
        if user_email and not is_lemma_admin:
            try:
                # Look up sites where this user is the admin
                site_conn = get_db_connection()
                site_cursor = site_conn.cursor()
                
                # Check sites table for admin_email match
                site_cursor.execute("""
                    SELECT site_id, site_domain, company_name 
                    FROM sites 
                    WHERE admin_email = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_email,))
                
                site_result = site_cursor.fetchone()
                
                if site_result:
                    site_id = site_result[0]
                    site_domain = site_result[1]
                    logger.info(f"📊 Showing users for site {site_id} (owner: {user_email})")
                else:
                    # Also check site_admins table
                    site_cursor.execute("""
                        SELECT site_id 
                        FROM site_admins 
                        WHERE admin_email = %s AND is_active = TRUE
                        ORDER BY added_at DESC
                        LIMIT 1
                    """, (user_email,))
                    
                    admin_result = site_cursor.fetchone()
                    if admin_result:
                        site_id = admin_result[0]
                        # Get site domain
                        site_cursor.execute("SELECT site_domain FROM sites WHERE site_id = %s", (site_id,))
                        domain_result = site_cursor.fetchone()
                        if domain_result:
                            site_domain = domain_result[0]
                        logger.info(f"📊 Showing users for site {site_id} (admin: {user_email})")
                    else:
                        logger.info(f"📊 No site found for {user_email}, showing empty list")
                        site_id = None  # No site, will return empty list
                
                site_cursor.close()
                site_conn.close()
                
            except Exception as e:
                logger.warning(f"⚠️ Could not look up site for {user_email}: {e}")
        
        # Get users for the determined site
        if not site_id:
            return jsonify({
                'success': True,
                'users': [],
                'total': 0,
                'site_id': None,
                'site_domain': None,
                'message': 'No site registered. Register a site to see your users.'
            })
        
        conn = get_db_connection(site_id=site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                pi.id,
                pi.email, 
                pi.credential_did,
                pt.name as permission_name, 
                pi.granted_at, 
                pi.expires_at,
                pi.revoked_at,
                pi.metadata
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.site_id = %s
            ORDER BY pi.granted_at DESC
        """, (site_id,))
        
        users = []
        for row in cursor.fetchall():
            instance_id, email, credential_did, permission_name, granted_at, expires_at, revoked_at, metadata = row
            
            # Determine status
            if revoked_at:
                status = 'revoked'
            elif expires_at and expires_at < datetime.utcnow():
                status = 'expired'
            else:
                status = 'active'
            
            # Extract credential_id from metadata if available
            credential_id = None
            if metadata and isinstance(metadata, dict):
                credential_id = metadata.get('credential_id')
            
            # Fallback to credential_did or instance-based ID
            if not credential_id:
                credential_id = credential_did or f'perm_{instance_id}'
            
            users.append({
                'email': email,
                'permission': permission_name,
                'granted_at': granted_at.isoformat() if granted_at else None,
                'expires_at': expires_at.isoformat() if expires_at else 'Never',
                'status': status,
                'time_ago': get_time_ago(granted_at) if granted_at else 'Unknown',
                'credential_id': credential_id  # For revocation
            })
        
        logger.info(f"📊 Retrieved {len(users)} users for {site_id} ({site_domain})")
        
        return jsonify({
            'success': True,
            'users': users,
            'total': len(users),
            'site_id': site_id,
            'site_domain': site_domain,
            'is_lemma_admin': is_lemma_admin
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get platform users: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'users': []
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@platform_stats_bp.route('/api/platform/revoke-permission', methods=['POST'])
def revoke_platform_permission():
    """
    Revoke a user's permission from the platform
    
    REQUIRES: Admin permission (admin_access, super_admin, site_admin)
    Beta users CANNOT revoke permissions.
    
    POST /api/platform/revoke-permission
    {
        "email": "user@example.com",
        "credential_id": "cred_xxx",
        "reason": "User requested / Admin action",
        "admin_credential": {...}  // Admin's credential for authorization
    }
    
    This will:
    1. Verify admin has revocation authority
    2. Mark permission as revoked in database
    3. Trigger Bloom filter update
    4. Publish revocation event to all dynos via Redis pub/sub
    5. Clients will sync on next page load or after 7 days
    """
    conn = None
    cursor = None
    try:
        data = request.get_json()
        email = data.get('email')
        credential_id = data.get('credential_id')
        reason = data.get('reason', 'admin_action')
        admin_credential = data.get('admin_credential')
        
        # CRITICAL: Verify caller has admin permission
        admin_permissions = ['admin_access', 'super_admin', 'site_admin', 'admin', 'superadmin']
        
        if not admin_credential:
            logger.warning(f"🚫 Revocation attempt without admin credential")
            return jsonify({
                'success': False,
                'error': 'Admin credential required for revocation'
            }), 403
        
        # Extract permission from admin credential
        admin_claims = admin_credential.get('claims') or admin_credential.get('credentialSubject') or {}
        admin_permission_id = admin_claims.get('permissionId') or admin_claims.get('permission_level') or ''
        
        # Check if this is an actual admin (NOT beta-user)
        is_admin = admin_permission_id in admin_permissions or \
                   admin_permission_id.lower() in ['admin', 'superadmin', 'super_admin']
        
        if not is_admin:
            logger.warning(f"🚫 Non-admin ({admin_permission_id}) attempted to revoke credential for {email}")
            return jsonify({
                'success': False,
                'error': 'Only administrators can revoke permissions. Beta users cannot revoke.'
            }), 403
        
        logger.info(f"✅ Admin {admin_permission_id} authorized to revoke credential for {email}")
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        site_id = 'lemma_platform'
        
        # Mark permission as revoked in database
        conn = get_db_connection(site_id=site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE permission_instances
            SET revoked_at = NOW(),
                revoked_by = %s,
                revocation_reason = %s
            WHERE site_id = %s AND email = %s AND revoked_at IS NULL
            RETURNING id, credential_did
        """, ('platform_admin', reason, site_id, email))
        
        result = cursor.fetchone()
        
        if not result:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'error': 'No active permission found for this user'
            }), 404
        
        instance_id, user_did = result
        conn.commit()
        
        logger.info(f"✅ Marked permission as revoked in database: {email}")
        
        # Add to revocation list table
        # Note: Table has both lemma_id (unique, required) and credential_id (optional, for compatibility)
        cred_id_value = credential_id or f'perm_{instance_id}'
        cursor.execute("""
            INSERT INTO revocation_list 
            (lemma_id, credential_id, user_did, lemma_type, site_id, revoked_at, reason, bloom_filter_updated)
            VALUES (%s, %s, %s, 'permission', %s, NOW(), %s, FALSE)
            ON CONFLICT (lemma_id) DO UPDATE SET revoked_at = NOW()
        """, (cred_id_value, cred_id_value, user_did or f'user_{email}', site_id, reason))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Added to revocation_list table")
        
        # Trigger immediate Bloom filter sync via event bus (site-targeted)
        try:
            from api.revocation_sync import trigger_revocation_sync
            
            cred_id_for_sync = credential_id or f'perm_{instance_id}'
            
            # Site-targeted sync: Only this site's users will sync
            event_published = trigger_revocation_sync(cred_id_for_sync, 'permission', site_id=site_id)
            
            if event_published:
                logger.info(f"✅ Site-targeted revocation event published - ONLY site {site_id} will sync")
            else:
                logger.warning(f"⚠️ Event bus unavailable - local sync only")
                
        except Exception as e:
            logger.error(f"❌ Bloom filter sync error (non-critical): {e}")
        
        return jsonify({
            'success': True,
            'message': f'Permission revoked for {email}',
            'email': email,
            'revoked_at': datetime.utcnow().isoformat(),
            'bloom_filter_updated': True,
            'sync_propagated': event_published if 'event_published' in locals() else False
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"❌ Failed to revoke permission: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_time_ago(timestamp):
    """Convert timestamp to human-readable time ago"""
    if not timestamp:
        return 'Unknown'
    
    now = datetime.utcnow()
    diff = now - timestamp
    
    if diff.days > 365:
        return f"{diff.days // 365}y ago"
    elif diff.days > 30:
        return f"{diff.days // 30}mo ago"
    elif diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600}h ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60}m ago"
    else:
        return "Just now"

