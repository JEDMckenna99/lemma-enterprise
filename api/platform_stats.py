"""
Platform Statistics API
Provides real-time stats for the developer platform
"""

import os
import logging
from datetime import datetime
from flask import Blueprint, jsonify
from sqlalchemy import func, and_, or_

from api.database import SessionLocal, Site, SitePermissionGrant
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
    session = None
    try:
        session = SessionLocal()
        current_month = datetime.now().strftime('%Y-%m')
        
        # For lemma.id platform, we track users for 'lemma_platform' site
        site_id = 'lemma_platform'
        
        # 1. Get MAU (from Redis via usage_tracking)
        mau_count = get_monthly_active_users(site_id)
        logger.info(f"📊 MAU for {site_id}: {mau_count}")
        
        # 2. Get total verifications this month (from Redis)
        verification_count = get_verification_count(site_id)
        logger.info(f"📊 Verifications for {site_id}: {verification_count}")
        
        # 3. Get active users count (from database - site_permission_grants table)
        active_users = session.query(SitePermissionGrant).filter(
            and_(
                SitePermissionGrant.site_id == site_id,
                SitePermissionGrant.revoked_at.is_(None),
                or_(
                    SitePermissionGrant.expires_at.is_(None),
                    SitePermissionGrant.expires_at > datetime.utcnow()
                )
            )
        ).count()
        logger.info(f"📊 Active users for {site_id}: {active_users}")
        
        # 4. Get registered sites count (from database - sites table)
        registered_sites = session.query(Site).filter(
            Site.status == 'active'
        ).count()
        logger.info(f"📊 Registered sites: {registered_sites}")
        
        # 5. Get recent activity (last 5 permission grants)
        recent_permissions = session.query(SitePermissionGrant).filter(
            SitePermissionGrant.site_id == site_id
        ).order_by(
            SitePermissionGrant.granted_at.desc()
        ).limit(5).all()
        
        recent_activity = []
        for perm in recent_permissions:
            # Extract email from user_did (format: did:lemma:hash-of-email)
            user_email = perm.user_did.split(':')[-1][:20] + '...'  # Truncate for privacy
            
            recent_activity.append({
                'type': 'permission_granted',
                'user': user_email,
                'permission': perm.permission_id,
                'timestamp': perm.granted_at.isoformat() if perm.granted_at else None,
                'time_ago': get_time_ago(perm.granted_at) if perm.granted_at else 'Unknown'
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
        if session:
            session.close()


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
    session = None
    try:
        session = SessionLocal()
        site_id = 'lemma_platform'
        
        # Get all user permissions for lemma_platform
        permissions = session.query(SitePermissionGrant).filter(
            SitePermissionGrant.site_id == site_id
        ).order_by(
            SitePermissionGrant.granted_at.desc()
        ).all()
        
        users = []
        for perm in permissions:
            # Determine status
            if perm.revoked_at:
                status = 'revoked'
            elif perm.expires_at and perm.expires_at < datetime.utcnow():
                status = 'expired'
            else:
                status = 'active'
            
            users.append({
                'user_did': perm.user_did,
                'email': perm.user_did.split(':')[-1][:40],  # Extract from DID
                'permission': perm.permission_id,
                'granted_at': perm.granted_at.isoformat() if perm.granted_at else None,
                'expires_at': perm.expires_at.isoformat() if perm.expires_at else 'Never',
                'status': status,
                'time_ago': get_time_ago(perm.granted_at) if perm.granted_at else 'Unknown'
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
        if session:
            session.close()


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

