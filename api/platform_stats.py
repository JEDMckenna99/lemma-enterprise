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


@platform_stats_bp.route('/api/platform/stats', methods=['GET', 'POST'])
def get_platform_stats():
    """
    Get platform statistics for the developer dashboard
    
    Shows stats for the caller's site:
    - Lemma.id admins see lemma_platform stats
    - Beta users see their own site's stats
    
    POST body (optional):
    {
        "user_credential": {...}  // Caller's credential to determine their site
    }
    
    Returns:
        {
            "mau": int,                    # Monthly active users
            "total_verifications": int,    # Verifications this month
            "active_users": int,           # Total users with active permissions
            "registered_sites": int,       # Number of sites registered (for admins only)
            "recent_activity": []          # Last 5 events for this site
        }
    """
    conn = None
    cursor = None
    try:
        current_month = datetime.now().strftime('%Y-%m')
        
        # Determine which site's stats to show
        site_id = None
        site_domain = None
        user_email = None
        is_lemma_admin = False
        available_sites = []
        
        # Get caller's credential to determine their site
        requested_site_id = None
        if request.method == 'POST':
            data = request.get_json() or {}
            requested_site_id = data.get('site_id')  # Allow requesting specific site
            user_credential = data.get('user_credential')
            if user_credential:
                claims = user_credential.get('claims') or user_credential.get('credentialSubject') or {}
                user_email = claims.get('email')
                permission_id = claims.get('permissionId') or claims.get('permission_level') or ''
                
                # Check if this is a lemma.id admin
                admin_permissions = ['admin_access', 'super_admin', 'site_admin', 'admin']
                is_lemma_admin = permission_id in admin_permissions
        
        # Try to get customer_id from session (set during login)
        from flask import session as flask_session
        customer_id = flask_session.get('customer_id')
        
        logger.info(f"📊 Stats request: customer_id={customer_id}, is_lemma_admin={is_lemma_admin}, user_email={user_email}")
        
        # ONLY show lemma.id stats if user is EXPLICITLY a lemma.id admin
        # Regular developers should NEVER see lemma.id stats
        if is_lemma_admin and not requested_site_id:
            site_id = 'lemma_platform'
            site_domain = 'lemma.id'
            logger.info(f"📊 Admin view - showing lemma.id stats")
        else:
            # Look up sites the caller owns
            try:
                site_conn = get_db_connection()
                site_cursor = site_conn.cursor()
                
                # Method 1: Look up sites via customer_id in customers table (API keys stored as JSON)
                if customer_id:
                    try:
                        site_cursor.execute("""
                            SELECT api_keys FROM customers WHERE customer_id = %s
                        """, (customer_id,))
                        
                        customer_row = site_cursor.fetchone()
                        if customer_row and customer_row[0]:
                            import json
                            api_keys_data = customer_row[0]
                            if isinstance(api_keys_data, str):
                                api_keys_data = json.loads(api_keys_data)
                            
                            # Extract unique site_ids from API keys
                            site_ids_from_keys = set()
                            for key_data in api_keys_data or []:
                                key_site_id = key_data.get('site_id')
                                if key_site_id and key_data.get('status') != 'revoked':
                                    site_ids_from_keys.add(key_site_id)
                            
                            # Fetch site details for those site_ids
                            if site_ids_from_keys:
                                placeholders = ','.join(['%s'] * len(site_ids_from_keys))
                                site_cursor.execute(f"""
                                    SELECT site_id, site_domain, company_name 
                                    FROM sites 
                                    WHERE site_id IN ({placeholders})
                                    ORDER BY created_at DESC
                                """, tuple(site_ids_from_keys))
                                
                                for row in site_cursor.fetchall():
                                    available_sites.append({
                                        'site_id': row[0],
                                        'site_domain': row[1],
                                        'company_name': row[2]
                                    })
                            
                            logger.info(f"📊 Found {len(available_sites)} sites via customer {customer_id} API keys")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not look up sites via customer API keys: {e}")
                
                # Method 2: Fallback - look up by admin_email in sites table
                if not available_sites and user_email:
                    site_cursor.execute("""
                        SELECT site_id, site_domain, company_name 
                        FROM sites 
                        WHERE admin_email = %s
                        ORDER BY created_at DESC
                    """, (user_email,))
                    
                    for row in site_cursor.fetchall():
                        available_sites.append({
                            'site_id': row[0],
                            'site_domain': row[1],
                            'company_name': row[2]
                        })
                    
                    logger.info(f"📊 Found {len(available_sites)} sites via admin_email {user_email}")
                
                site_cursor.close()
                site_conn.close()
                
                # If specific site requested, validate and use it
                if requested_site_id:
                    matching_site = next((s for s in available_sites if s['site_id'] == requested_site_id), None)
                    if matching_site or is_lemma_admin:
                        site_id = requested_site_id
                        site_domain = matching_site['site_domain'] if matching_site else requested_site_id
                
                # Use first available site if no specific request
                if not site_id and available_sites:
                    site_id = available_sites[0]['site_id']
                    site_domain = available_sites[0]['site_domain']
                    logger.info(f"📊 Using first available site: {site_domain}")
                
                # No site found - return empty stats
                if not site_id:
                    logger.info(f"📊 No sites found for caller (customer_id={customer_id}, email={user_email})")
                    return jsonify({
                        'success': True,
                        'stats': {
                            'mau': 0,
                            'total_verifications': 0,
                            'active_users': 0,
                            'registered_sites': 0
                        },
                        'recent_activity': [],
                        'site_id': None,
                        'site_domain': None,
                        'available_sites': [],
                        'month': current_month,
                        'message': 'No site registered yet. Register a site to see your stats.'
                    })
                
            except Exception as e:
                logger.warning(f"⚠️ Could not look up sites: {e}")
        
        # SAFETY CHECK: If we still don't have a site_id and user is NOT admin, return empty
        # This prevents accidentally showing lemma.id stats to non-admins
        if not site_id and not is_lemma_admin:
            logger.info(f"📊 Safety check: No site found for non-admin user, returning empty stats")
            return jsonify({
                'success': True,
                'stats': {
                    'mau': 0,
                    'total_verifications': 0,
                    'active_users': 0,
                    'registered_sites': 0
                },
                'recent_activity': [],
                'site_id': None,
                'site_domain': None,
                'available_sites': [],
                'month': current_month,
                'message': 'No site registered yet. Register a site to see your stats.'
            })
        
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
        
        # 4. Get registered sites count (for admins) or just 1 for site owners
        if is_lemma_admin:
            cursor.execute("SELECT COUNT(*) FROM sites")
            registered_sites = cursor.fetchone()[0]
        else:
            # Count sites owned by this user
            cursor.execute("SELECT COUNT(*) FROM sites WHERE admin_email = %s", (user_email,))
            registered_sites = cursor.fetchone()[0] if user_email else 1
        logger.info(f"📊 Registered sites: {registered_sites}")
        
        # 5. Get recent activity (last 5 permission grants for THIS site)
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
        
        logger.info(f"📊 Recent activity for {site_id}: {len(recent_activity)} events")
        
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
            'site_domain': site_domain,
            'is_lemma_admin': is_lemma_admin,
            'available_sites': available_sites,
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
    - Site owners see their own site's users (looked up via customer_id from API keys)
    
    POST body (optional):
    {
        "site_id": "specific_site_id",  // Optional: specific site to query
        "user_credential": {...}  // Caller's credential to determine their site
    }
    
    Returns:
        {
            "users": [...],
            "site_id": "the_site_id",
            "site_domain": "the domain",
            "available_sites": [...]  // List of sites the caller can view
        }
    """
    conn = None
    cursor = None
    try:
        # Determine which site's users to show
        site_id = None
        site_domain = None
        user_email = None
        customer_id = None
        is_lemma_admin = False
        available_sites = []
        
        # Get caller's credential and requested site
        requested_site_id = None
        if request.method == 'POST':
            data = request.get_json() or {}
            requested_site_id = data.get('site_id')  # Specific site requested
            user_credential = data.get('user_credential')
            if user_credential:
                claims = user_credential.get('claims') or user_credential.get('credentialSubject') or {}
                user_email = claims.get('email')
                permission_id = claims.get('permissionId') or claims.get('permission_level') or ''
                
                # Check if this is a lemma.id admin
                admin_permissions = ['admin_access', 'super_admin', 'site_admin', 'admin']
                is_lemma_admin = permission_id in admin_permissions
        else:
            # GET request - try to get from query params
            user_email = request.args.get('email')
            requested_site_id = request.args.get('site_id')
        
        # Try to get customer_id from session (set during login)
        from flask import session as flask_session
        customer_id = flask_session.get('customer_id')
        
        logger.info(f"📊 Users request: customer_id={customer_id}, is_lemma_admin={is_lemma_admin}, user_email={user_email}")
        
        # ONLY show lemma.id users if user is EXPLICITLY a lemma.id admin
        # Regular developers should NEVER see lemma.id users
        if is_lemma_admin and not requested_site_id:
            site_id = 'lemma_platform'
            site_domain = 'lemma.id'
            logger.info(f"📊 Admin view - showing lemma.id users")
        else:
            # Look up sites the caller owns
            try:
                site_conn = get_db_connection()
                site_cursor = site_conn.cursor()
                
                # Method 1: Look up sites via customer_id in customers table (API keys stored as JSON)
                if customer_id:
                    try:
                        site_cursor.execute("""
                            SELECT api_keys FROM customers WHERE customer_id = %s
                        """, (customer_id,))
                        
                        customer_row = site_cursor.fetchone()
                        if customer_row and customer_row[0]:
                            import json
                            api_keys_data = customer_row[0]
                            if isinstance(api_keys_data, str):
                                api_keys_data = json.loads(api_keys_data)
                            
                            # Extract unique site_ids from API keys
                            site_ids_from_keys = set()
                            for key_data in api_keys_data or []:
                                key_site_id = key_data.get('site_id')
                                if key_site_id and key_data.get('status') != 'revoked':
                                    site_ids_from_keys.add(key_site_id)
                            
                            # Fetch site details for those site_ids
                            if site_ids_from_keys:
                                placeholders = ','.join(['%s'] * len(site_ids_from_keys))
                                site_cursor.execute(f"""
                                    SELECT site_id, site_domain, company_name 
                                    FROM sites 
                                    WHERE site_id IN ({placeholders})
                                    ORDER BY created_at DESC
                                """, tuple(site_ids_from_keys))
                                
                                for row in site_cursor.fetchall():
                                    available_sites.append({
                                        'site_id': row[0],
                                        'site_domain': row[1],
                                        'company_name': row[2]
                                    })
                            
                            logger.info(f"📊 Found {len(available_sites)} sites via customer {customer_id} API keys")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not look up sites via customer API keys: {e}")
                
                # Method 2: Fallback - look up by admin_email in sites table
                if not available_sites and user_email:
                    site_cursor.execute("""
                        SELECT site_id, site_domain, company_name 
                        FROM sites 
                        WHERE admin_email = %s
                        ORDER BY created_at DESC
                    """, (user_email,))
                    
                    for row in site_cursor.fetchall():
                        available_sites.append({
                            'site_id': row[0],
                            'site_domain': row[1],
                            'company_name': row[2]
                        })
                    
                    logger.info(f"📊 Found {len(available_sites)} sites via admin_email {user_email}")
                
                # Method 3: Check site_admins table if still no sites
                if not available_sites and user_email:
                    try:
                        site_cursor.execute("""
                            SELECT s.site_id, s.site_domain, s.company_name
                            FROM site_admins sa
                            JOIN sites s ON sa.site_id = s.site_id
                            WHERE sa.admin_email = %s AND sa.is_active = TRUE
                        """, (user_email,))
                        
                        for row in site_cursor.fetchall():
                            if not any(s['site_id'] == row[0] for s in available_sites):
                                available_sites.append({
                                    'site_id': row[0],
                                    'site_domain': row[1],
                                    'company_name': row[2]
                                })
                        
                        if available_sites:
                            logger.info(f"📊 Found {len(available_sites)} sites via site_admins table")
                    except Exception as e:
                        logger.debug(f"site_admins lookup failed (table may not exist): {e}")
                
                site_cursor.close()
                site_conn.close()
                
                # If specific site requested, validate and use it
                if requested_site_id:
                    matching_site = next((s for s in available_sites if s['site_id'] == requested_site_id), None)
                    if matching_site or is_lemma_admin:
                        site_id = requested_site_id
                        site_domain = matching_site['site_domain'] if matching_site else requested_site_id
                    else:
                        logger.warning(f"⚠️ Requested site {requested_site_id} not in available sites")
                
                # Use first available site if no specific request
                if not site_id and available_sites:
                    site_id = available_sites[0]['site_id']
                    site_domain = available_sites[0]['site_domain']
                    logger.info(f"📊 Using first available site: {site_domain}")
                
                if not site_id:
                    logger.info(f"📊 No sites found for caller (customer_id={customer_id}, email={user_email})")
                
            except Exception as e:
                logger.warning(f"⚠️ Could not look up sites: {e}")
        
        # Get users for the determined site
        if not site_id:
            return jsonify({
                'success': True,
                'users': [],
                'total': 0,
                'site_id': None,
                'site_domain': None,
                'available_sites': [],
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
            'is_lemma_admin': is_lemma_admin,
            'available_sites': available_sites
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


@platform_stats_bp.route('/api/platform/issue-site-permission', methods=['POST'])
def issue_site_permission():
    """
    Issue a permission credential directly to a user for any registered site.
    This allows platform admins to grant access without the email confirmation flow.
    
    POST /api/platform/issue-site-permission
    {
        "site_id": "example.com",
        "user_email": "user@example.com", 
        "permission_level": "user" | "editor" | "admin" | "custom_permission",
        "expiry_days": 90
    }
    
    Returns:
        - permission_lemma: The signed credential
        - credential_id: Unique ID
        - stored_in_wallet: Whether stored in user's central wallet
    """
    import time
    import json
    
    conn = None
    cursor = None
    
    try:
        data = request.get_json()
        site_id = data.get('site_id')
        user_email = data.get('user_email')
        permission_level = data.get('permission_level', 'user')
        expiry_days = data.get('expiry_days', 90)
        
        if not site_id or not user_email:
            return jsonify({
                'success': False,
                'error': 'site_id and user_email are required'
            }), 400
        
        logger.info(f"🎫 Issuing permission: {permission_level} for {user_email} on {site_id}")
        
        # Get or create site manager
        from api.real_iam_manager import get_or_create_site_manager
        
        # Get site domain from database or use site_id as domain
        conn = get_db_connection(site_id='lemma_platform')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT site_domain, company_name FROM sites WHERE site_id = %s OR site_domain = %s
        """, (site_id, site_id))
        
        site_row = cursor.fetchone()
        site_domain = site_row[0] if site_row else site_id
        company_name = site_row[1] if site_row else site_id
        
        # Get or create manager for this site
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Ensure permission type exists
        if permission_level not in manager.permissions:
            manager.add_permission({
                'permission_id': permission_level,
                'display_name': permission_level.replace('_', ' ').title(),
                'scope': ['read', 'write'] if permission_level in ['editor', 'admin'] else ['read'],
                'conditions': [],
                'priority': 100
            })
        
        # Derive user DID (PPID) from email + site
        from api.ppid import derive_ppid_did
        user_did = derive_ppid_did(user_email, site_domain)
        
        # Issue the permission lemma
        start_time = time.perf_counter()
        
        permission_lemma = manager.issue_permission_lemma(
            user_did,
            permission_level,
            expiry_days=expiry_days,
            custom_claims={
                'email': user_email,
                'site_domain': site_domain,
                'accountType': permission_level,
                'permissionId': f'{permission_level}_access',
                'issuedBy': 'platform_admin'
            }
        )
        
        # Add W3C type fields
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'
        
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Track in database
        try:
            from datetime import timedelta
            expires_at = datetime.utcnow() + timedelta(days=expiry_days) if expiry_days > 0 else None
            
            # Get or create permission type
            cursor.execute("""
                SELECT id FROM permission_types 
                WHERE site_id = %s AND name = %s
            """, (site_id, permission_level))
            
            perm_type_row = cursor.fetchone()
            if perm_type_row:
                permission_type_id = perm_type_row[0]
            else:
                cursor.execute("""
                    INSERT INTO permission_types (site_id, name, type, description, active)
                    VALUES (%s, %s, 'role', %s, TRUE)
                    RETURNING id
                """, (site_id, permission_level, f'{permission_level.title()} access'))
                permission_type_id = cursor.fetchone()[0]
            
            # Insert permission instance
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
                'platform_admin',
                expires_at,
                json.dumps({
                    'credential_id': permission_lemma.get('id', ''),
                    'issue_time_us': issue_time_us,
                    'issued_via': 'platform_dashboard'
                })
            ))
            
            conn.commit()
            logger.info(f"✅ Tracked permission in database")
            
        except Exception as db_err:
            logger.warning(f"⚠️ Database tracking failed (credential still issued): {db_err}")
            if conn:
                conn.rollback()
        
        logger.info(f"✅ Permission issued: {permission_level} for {user_email} on {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        
        return jsonify({
            'success': True,
            'credential_id': permission_lemma.get('id', 'generated'),
            'permission_lemma': permission_lemma,
            'site_id': site_id,
            'site_domain': site_domain,
            'user_email': user_email,
            'permission_level': permission_level,
            'expiry_days': expiry_days,
            'issue_time_us': issue_time_us,
            'stored_in_wallet': False,  # User needs to claim via email or direct wallet storage
            'message': f'Permission credential issued. User can claim at lemma.id/wallet or via email.'
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to issue site permission: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
