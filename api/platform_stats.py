"""
Platform Statistics API
Provides real-time stats for the developer platform
"""

import os
import logging
from datetime import datetime
from flask import Blueprint, jsonify
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


@platform_stats_bp.route('/api/platform/users', methods=['GET'])
def get_platform_users():
    """
    Get all users with permissions for the platform
    
    Returns:
        {
            "users": [
                {
                    "email": str,
                    "permission": str,
                    "granted_at": str,
                    "expires_at": str,
                    "status": str
                }
            ]
        }
    """
    conn = None
    cursor = None
    try:
        site_id = 'lemma_platform'
        
        # Get all user permissions for lemma_platform from permission_instances
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
        
        logger.info(f"📊 Retrieved {len(users)} users for {site_id}")
        
        return jsonify({
            'success': True,
            'users': users,
            'total': len(users)
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
    
    POST /api/platform/revoke-permission
    {
        "email": "user@example.com",
        "credential_id": "cred_xxx",
        "reason": "User requested / Admin action"
    }
    
    This will:
    1. Mark permission as revoked in database
    2. Trigger Bloom filter update
    3. Publish revocation event to all dynos via Redis pub/sub
    4. Clients will sync on next page load or after 7 days
    """
    conn = None
    cursor = None
    try:
        data = request.get_json()
        email = data.get('email')
        credential_id = data.get('credential_id')
        reason = data.get('reason', 'admin_action')
        
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
        cursor.execute("""
            INSERT INTO revocation_list 
            (credential_id, user_did, lemma_type, site_id, revoked_at, reason, bloom_filter_updated)
            VALUES (%s, %s, 'permission', %s, NOW(), %s, FALSE)
            ON CONFLICT (credential_id) DO UPDATE SET revoked_at = NOW()
        """, (credential_id or f'perm_{instance_id}', user_did or f'user_{email}', site_id, reason))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Added to revocation_list table")
        
        # Trigger immediate Bloom filter sync via event bus
        try:
            from api.revocation_sync import trigger_revocation_sync
            
            cred_id_for_sync = credential_id or f'perm_{instance_id}'
            event_published = trigger_revocation_sync(cred_id_for_sync, 'permission')
            
            if event_published:
                logger.info(f"✅ Revocation event published - ALL dynos syncing Bloom filter")
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

