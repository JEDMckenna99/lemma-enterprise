"""
IAM Permission Types API
Provides structured permission type management (role, scope, time-bound, attribute, hierarchical)
Extends the existing permission_management_api.py with type system
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from auth.decorators import require_site_admin
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

iam_types_bp = Blueprint('iam_types', __name__)

# Valid permission types
VALID_PERMISSION_TYPES = ['role', 'scope', 'time-bound', 'attribute', 'hierarchical']

# Helper function to get database connection
def get_db_conn(site_id=None):
    """
    Get database connection with optional RLS context
    
    Args:
        site_id (str, optional): Site ID for Row-Level Security isolation
    
    Returns connection with RLS session variable set (if site_id provided)
    """
    try:
        from api.database import get_db_connection
        return get_db_connection(site_id=site_id)
    except:
        # Fallback to mock for testing
        return None

def log_audit_event(site_id, event_type, actor, target=None, details=None, ip_address=None):
    """Log IAM audit event with RLS isolation"""
    try:
        # Pass site_id for RLS context
        conn = get_db_conn(site_id=site_id)
        if not conn:
            logger.warning("No DB connection - audit log skipped")
            return
            
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO iam_audit_log (site_id, event_type, actor, target, details, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            site_id,
            event_type,
            actor,
            target,
            json.dumps(details or {}),
            ip_address
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")

# ============================================
# PERMISSION TYPES API
# ============================================

@iam_types_bp.route('/api/iam/sites/<site_id>/permission-types', methods=['GET'])
@cross_origin()
@require_site_admin
def list_permission_types(site_id):
    """
    List all permission types for a site
    GET /api/iam/sites/{site_id}/permission-types?type=role&active=true
    """
    try:
        conn = get_db_conn()
        if not conn:
            # Return mock data for testing
            return jsonify({
                'success': True,
                'permission_types': [],
                'count': 0,
                'message': 'Database not connected - using mock mode'
            })
        
        cursor = conn.cursor()
        
        # Build query with filters
        query = """
            SELECT pt.id, pt.name, pt.type, pt.description, pt.config, 
                   pt.created_at, pt.created_by, pt.active,
                   (SELECT COUNT(*) FROM permission_instances pi 
                    WHERE pi.permission_type_id = pt.id 
                    AND pi.revoked_at IS NULL 
                    AND (pi.expires_at IS NULL OR pi.expires_at > NOW())) as active_instances
            FROM permission_types pt
            WHERE pt.site_id = %s
        """
        params = [site_id]
        
        # Optional filters
        if request.args.get('type'):
            query += " AND pt.type = %s"
            params.append(request.args.get('type'))
            
        if request.args.get('active'):
            query += " AND pt.active = %s"
            params.append(request.args.get('active') == 'true')
        
        query += " ORDER BY pt.created_at DESC"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        permission_types = []
        for row in results:
            permission_types.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'description': row[3],
                'config': row[4],
                'created_at': row[5].isoformat() if row[5] else None,
                'created_by': row[6],
                'active': row[7],
                'active_instances': row[8] or 0
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'permission_types': permission_types,
            'count': len(permission_types)
        })
        
    except Exception as e:
        logger.error(f"List permission types error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_types_bp.route('/api/iam/sites/<site_id>/permission-types', methods=['POST'])
@cross_origin()
@require_site_admin
def create_permission_type(site_id):
    """
    Create a new permission type
    POST /api/iam/sites/{site_id}/permission-types
    {
        "name": "premium_tier_1",
        "type": "time-bound",
        "description": "Premium subscription tier 1",
        "config": {
            "duration_days": 365,
            "auto_renew": false
        }
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('type'):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: name, type'
            }), 400
        
        # Validate permission type
        if data['type'] not in VALID_PERMISSION_TYPES:
            return jsonify({
                'success': False,
                'error': f'Invalid type. Must be one of: {VALID_PERMISSION_TYPES}'
            }), 400
        
        # Get connection with RLS context for this site
        conn = get_db_conn(site_id=site_id)
        if not conn:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503
        
        cursor = conn.cursor()
        
        # Insert permission type
        cursor.execute("""
            INSERT INTO permission_types (site_id, name, type, description, config, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            site_id,
            data['name'],
            data['type'],
            data.get('description', ''),
            json.dumps(data.get('config', {})),
            request.headers.get('X-Admin-Email', 'system')
        ))
        
        permission_type_id = cursor.fetchone()[0]
        conn.commit()
        
        # Log audit event
        log_audit_event(
            site_id=site_id,
            event_type='permission_type_created',
            actor=request.headers.get('X-Admin-Email', 'system'),
            target=data['name'],
            details={
                'permission_type_id': permission_type_id,
                'type': data['type']
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Created permission type '{data['name']}' for site {site_id}")
        
        return jsonify({
            'success': True,
            'permission_type_id': permission_type_id,
            'message': f'Permission type "{data["name"]}" created'
        }), 201
        
    except Exception as e:
        logger.error(f"Create permission type error: {e}")
        if 'duplicate key value violates unique constraint' in str(e):
            return jsonify({
                'success': False,
                'error': f'Permission type "{data["name"]}" already exists'
            }), 400
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_types_bp.route('/api/iam/sites/<site_id>/permission-types/<int:type_id>', methods=['PUT'])
@cross_origin()
@require_site_admin
def update_permission_type(site_id, type_id):
    """
    Update permission type
    PUT /api/iam/sites/{site_id}/permission-types/123
    {
        "description": "Updated description",
        "config": {"duration_days": 730},
        "active": true
    }
    """
    try:
        data = request.get_json()
        
        conn = get_db_conn()
        if not conn:
            return jsonify({'success': False, 'error': 'Database not available'}), 503
        
        cursor = conn.cursor()
        
        # Build update query
        update_fields = []
        params = []
        
        if 'description' in data:
            update_fields.append('description = %s')
            params.append(data['description'])
            
        if 'config' in data:
            update_fields.append('config = %s')
            params.append(json.dumps(data['config']))
            
        if 'active' in data:
            update_fields.append('active = %s')
            params.append(data['active'])
        
        if not update_fields:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400
        
        update_fields.append('updated_at = NOW()')
        params.extend([type_id, site_id])
        
        cursor.execute(f"""
            UPDATE permission_types
            SET {', '.join(update_fields)}
            WHERE id = %s AND site_id = %s
            RETURNING name
        """, params)
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Permission type not found'}), 404
        
        conn.commit()
        
        log_audit_event(
            site_id=site_id,
            event_type='permission_type_updated',
            actor=request.headers.get('X-Admin-Email', 'system'),
            target=result[0],
            details={'permission_type_id': type_id, 'changes': data},
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Permission type updated'})
        
    except Exception as e:
        logger.error(f"Update permission type error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# PERMISSION INSTANCES API
# ============================================

@iam_types_bp.route('/api/iam/sites/<site_id>/permissions/grant', methods=['POST'])
@cross_origin()
@require_site_admin
def grant_permission(site_id):
    """
    Grant permission to a user
    POST /api/iam/sites/{site_id}/permissions/grant
    {
        "email": "user@example.com",
        "permission": "premium_tier_1",
        "expires_at": "2025-12-31T23:59:59Z",
        "metadata": {
            "reason": "Annual subscription",
            "order_id": "ORD-12345"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('email') or not data.get('permission'):
            return jsonify({
                'success': False,
                'error': 'Missing required fields: email, permission'
            }), 400
        
        conn = get_db_conn()
        if not conn:
            return jsonify({'success': False, 'error': 'Database not available'}), 503
        
        cursor = conn.cursor()
        
        # Get permission type
        cursor.execute("""
            SELECT id, type, config FROM permission_types
            WHERE site_id = %s AND name = %s AND active = true
        """, (site_id, data['permission']))
        
        perm_type = cursor.fetchone()
        if not perm_type:
            return jsonify({
                'success': False,
                'error': f'Permission type "{data["permission"]}" not found'
            }), 404
        
        permission_type_id, perm_type_name, perm_config = perm_type
        
        # Calculate expiry for time-bound permissions
        expires_at = data.get('expires_at')
        if perm_type_name == 'time-bound' and not expires_at:
            # Auto-calculate from config
            duration_days = perm_config.get('duration_days', 365) if perm_config else 365
            expires_at = (datetime.now() + timedelta(days=duration_days)).isoformat()
        
        # Grant permission
        cursor.execute("""
            INSERT INTO permission_instances 
            (permission_type_id, site_id, email, granted_by, expires_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            permission_type_id,
            site_id,
            data['email'],
            request.headers.get('X-Admin-Email', 'system'),
            expires_at,
            json.dumps(data.get('metadata', {}))
        ))
        
        instance_id = cursor.fetchone()[0]
        conn.commit()
        
        log_audit_event(
            site_id=site_id,
            event_type='permission_granted',
            actor=request.headers.get('X-Admin-Email', 'system'),
            target=data['email'],
            details={
                'permission': data['permission'],
                'instance_id': instance_id,
                'expires_at': expires_at
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Granted '{data['permission']}' to {data['email']} on site {site_id}")
        
        return jsonify({
            'success': True,
            'instance_id': instance_id,
            'message': f'Permission "{data["permission"]}" granted to {data["email"]}'
        }), 201
        
    except Exception as e:
        logger.error(f"Grant permission error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_types_bp.route('/api/iam/sites/<site_id>/permissions/revoke', methods=['POST'])
@cross_origin()
@require_site_admin
def revoke_permission(site_id):
    """
    Revoke permission from user
    POST /api/iam/sites/{site_id}/permissions/revoke
    {
        "email": "user@example.com",
        "permission": "premium_tier_1",
        "reason": "Subscription cancelled"
    }
    """
    try:
        data = request.get_json()
        
        if not data.get('email'):
            return jsonify({'success': False, 'error': 'Missing email'}), 400
        
        conn = get_db_conn()
        if not conn:
            return jsonify({'success': False, 'error': 'Database not available'}), 503
        
        cursor = conn.cursor()
        
        # Revoke permissions
        if data.get('permission'):
            # Revoke specific permission
            cursor.execute("""
                UPDATE permission_instances pi
                SET revoked_at = NOW(),
                    revoked_by = %s,
                    revocation_reason = %s
                FROM permission_types pt
                WHERE pi.permission_type_id = pt.id
                AND pi.site_id = %s
                AND pi.email = %s
                AND pt.name = %s
                AND pi.revoked_at IS NULL
                RETURNING pi.id
            """, (
                request.headers.get('X-Admin-Email', 'system'),
                data.get('reason', ''),
                site_id,
                data['email'],
                data['permission']
            ))
        else:
            # Revoke ALL permissions for this user on this site
            cursor.execute("""
                UPDATE permission_instances
                SET revoked_at = NOW(),
                    revoked_by = %s,
                    revocation_reason = %s
                WHERE site_id = %s
                AND email = %s
                AND revoked_at IS NULL
                RETURNING id
            """, (
                request.headers.get('X-Admin-Email', 'system'),
                data.get('reason', ''),
                site_id,
                data['email']
            ))
        
        revoked_ids = cursor.fetchall()
        conn.commit()
        
        if not revoked_ids:
            return jsonify({
                'success': False,
                'error': 'No active permissions found to revoke'
            }), 404
        
        log_audit_event(
            site_id=site_id,
            event_type='permission_revoked',
            actor=request.headers.get('X-Admin-Email', 'system'),
            target=data['email'],
            details={
                'permission': data.get('permission', 'ALL'),
                'revoked_count': len(revoked_ids),
                'reason': data.get('reason', '')
            },
            ip_address=request.remote_addr
        )
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Revoked {len(revoked_ids)} permission(s) from {data['email']} on site {site_id}")
        
        return jsonify({
            'success': True,
            'revoked_count': len(revoked_ids),
            'message': f'Revoked {len(revoked_ids)} permission(s) from {data["email"]}'
        })
        
    except Exception as e:
        logger.error(f"Revoke permission error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@iam_types_bp.route('/api/iam/sites/<site_id>/users/search', methods=['GET'])
@cross_origin()
@require_site_admin
def search_users_by_permission(site_id):
    """
    Find all users with specific permission
    GET /api/iam/sites/{site_id}/users/search?permission=admin&active_only=true&limit=50
    """
    try:
        permission = request.args.get('permission')
        active_only = request.args.get('active_only', 'true') == 'true'
        limit = int(request.args.get('limit', 50))
        
        conn = get_db_conn()
        if not conn:
            return jsonify({
                'success': True,
                'users': [],
                'count': 0,
                'message': 'Database not available'
            })
        
        cursor = conn.cursor()
        
        query = """
            SELECT pi.email, pt.name, pi.granted_at, pi.expires_at, pi.metadata
            FROM permission_instances pi
            JOIN permission_types pt ON pi.permission_type_id = pt.id
            WHERE pi.site_id = %s
        """
        params = [site_id]
        
        if permission:
            query += " AND pt.name = %s"
            params.append(permission)
        
        if active_only:
            query += " AND pi.revoked_at IS NULL"
            query += " AND (pi.expires_at IS NULL OR pi.expires_at > NOW())"
        
        query += " ORDER BY pi.granted_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        users = []
        for row in results:
            users.append({
                'email': row[0],
                'permission': row[1],
                'granted_at': row[2].isoformat() if row[2] else None,
                'expires_at': row[3].isoformat() if row[3] else None,
                'metadata': row[4]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'users': users,
            'count': len(users)
        })
        
    except Exception as e:
        logger.error(f"Search users error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# STATISTICS/ANALYTICS
# ============================================

@iam_types_bp.route('/api/iam/sites/<site_id>/stats', methods=['GET'])
@cross_origin()
@require_site_admin
def get_iam_stats(site_id):
    """Get IAM statistics for dashboard"""
    try:
        conn = get_db_conn()
        if not conn:
            # Return mock stats for testing
            return jsonify({
                'success': True,
                'permission_types': 0,
                'active_users': 0,
                'active_instances': 0,
                'expiring_soon': 0
            })
        
        cursor = conn.cursor()
        
        # Count permission types
        cursor.execute("""
            SELECT COUNT(*) FROM permission_types 
            WHERE site_id = %s AND active = true
        """, [site_id])
        permission_types = cursor.fetchone()[0]
        
        # Count active users
        cursor.execute("""
            SELECT COUNT(DISTINCT email) FROM permission_instances 
            WHERE site_id = %s AND revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > NOW())
        """, [site_id])
        active_users = cursor.fetchone()[0]
        
        # Count active permission instances
        cursor.execute("""
            SELECT COUNT(*) FROM permission_instances 
            WHERE site_id = %s AND revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > NOW())
        """, [site_id])
        active_instances = cursor.fetchone()[0]
        
        # Count expiring soon (next 30 days)
        cursor.execute("""
            SELECT COUNT(*) FROM permission_instances 
            WHERE site_id = %s AND revoked_at IS NULL
            AND expires_at BETWEEN NOW() AND NOW() + INTERVAL '30 days'
        """, [site_id])
        expiring_soon = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'permission_types': permission_types or 0,
            'active_users': active_users or 0,
            'active_instances': active_instances or 0,
            'expiring_soon': expiring_soon or 0
        })
        
    except Exception as e:
        logger.error(f"Get IAM stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

