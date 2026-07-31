"""
Site Management API
Handles site users (PPIDs), permission types, and API keys
"""

import json
import logging
import secrets
import hashlib
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
from flask_cors import cross_origin
from api.agent_credentials import require_agent_or_user_auth
from api.site_access import get_authenticated_ppid, require_site_ownership
from api.forensic_audit import capture_action_proof

logger = logging.getLogger(__name__)

site_management_bp = Blueprint('site_management', __name__)


def _tenant_value(value: str | None, fallback: str, max_len: int = 120) -> str:
    cleaned = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"-", "_", "."})
    cleaned = cleaned[:max_len]
    return cleaned or fallback


@site_management_bp.before_request
def _enforce_site_tenant_context():
    g.org_id = _tenant_value(request.headers.get("X-Lemma-Org-Id") or request.args.get("org_id"), "org_default", 120)
    env = _tenant_value(request.headers.get("X-Lemma-Environment") or request.args.get("environment"), "prod", 32)
    g.environment = env if env in {"dev", "staging", "prod"} else "prod"
    scoped_site = _tenant_value(request.headers.get("X-Lemma-Site-Id"), "", 120)
    route_site = _tenant_value((request.view_args or {}).get("site_id"), "", 120)
    if scoped_site and route_site and scoped_site != route_site:
        return jsonify({"success": False, "error": "site_scope_forbidden"}), 403


@site_management_bp.before_request
def _enforce_site_ownership_context():
    if request.method == "OPTIONS":
        return None
    site_id = (request.view_args or {}).get("site_id")
    if not site_id:
        return None
    return require_site_ownership(site_id)


def _actor_ppid_for_audit() -> str:
    """Resolve authenticated actor PPID for audit fields."""
    ppid = get_authenticated_ppid()
    if ppid:
        return ppid
    return "api"


# ============================================
# SITE USERS (PPIDs) API
# ============================================

@site_management_bp.route('/api/developer/sites/<site_id>/users', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_users(site_id):
    """Get all users (PPIDs) for a site"""
    try:
        from api.database import SessionLocal
        
        # Pagination params
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        per_page = min(per_page, 100)  # Max 100 per page
        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', 'all')
        
        db = SessionLocal()
        
        try:
            # Query site_users table
            query = """
                SELECT 
                    su.id,
                    su.user_ppid,
                    su.display_name,
                    su.role,
                    su.status,
                    su.added_by,
                    su.added_at,
                    su.last_seen,
                    su.metadata,
                    (SELECT COUNT(*) FROM site_permission_grants spg 
                     WHERE spg.site_id = su.site_id AND spg.user_did = su.user_ppid AND spg.is_active = true) as permission_count
                FROM site_users su
                WHERE su.site_id = %s
            """
            params = [site_id]
            
            # Add status filter
            if status_filter != 'all':
                query += " AND su.status = %s"
                params.append(status_filter)
            
            # Add search filter
            if search:
                query += " AND (su.user_ppid ILIKE %s OR su.display_name ILIKE %s)"
                params.extend([f'%{search}%', f'%{search}%'])
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM ({query}) as subq"
            
            from api.database import get_db_connection
            conn = get_db_connection(site_id)
            cursor = conn.cursor()
            
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Add pagination and ordering
            query += " ORDER BY su.last_seen DESC NULLS LAST, su.added_at DESC"
            query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            users = []
            for row in rows:
                users.append({
                    'id': row[0],
                    'ppid': row[1],
                    'display_name': row[2],
                    'role': row[3],
                    'status': row[4],
                    'added_by': row[5],
                    'added_at': row[6].isoformat() if row[6] else None,
                    'last_seen': row[7].isoformat() if row[7] else None,
                    'metadata': row[8] or {},
                    'permission_count': row[9] or 0
                })
            
            cursor.close()
            conn.close()
            
            return jsonify({
                'success': True,
                'users': users,
                'total': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': (total_count + per_page - 1) // per_page
            })
            
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return jsonify({
                'success': False,
                'error': 'directory_unavailable',
            }), 503
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Failed to get site users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def add_site_user(site_id):
    """Add or register a user to the site (auto-happens on login, but can be done manually)
    
    NOTE: We do NOT accept internal_id - developers should store PPID -> internal_id
    mapping in their own database to preserve privacy.
    """
    try:
        from api.database import get_db_connection
        
        data = request.get_json() or {}
        
        user_ppid = data.get('ppid', '').strip()
        if not user_ppid:
            return jsonify({'success': False, 'error': 'PPID is required'}), 400
        
        display_name = data.get('display_name', '').strip() or None
        role = data.get('role', 'user')
        
        if role not in ['user', 'moderator', 'admin']:
            role = 'user'
        
        added_by = _actor_ppid_for_audit()
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        # Upsert user - no metadata/internal_id stored
        cursor.execute("""
            INSERT INTO site_users (site_id, user_ppid, display_name, role, status, added_by)
            VALUES (%s, %s, %s, %s, 'active', %s)
            ON CONFLICT (site_id, user_ppid) 
            DO UPDATE SET 
                display_name = COALESCE(EXCLUDED.display_name, site_users.display_name),
                role = EXCLUDED.role
            RETURNING id, user_ppid, display_name, role, status, added_at
        """, (
            site_id,
            user_ppid,
            display_name,
            role,
            added_by
        ))
        
        row = cursor.fetchone()
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Added/updated user {user_ppid[:20]}... on site {site_id}")
        
        return jsonify({
            'success': True,
            'user': {
                'id': row[0],
                'ppid': row[1],
                'display_name': row[2],
                'role': row[3],
                'status': row[4],
                'added_at': row[5].isoformat() if row[5] else None
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to add user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/<ppid>', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_user_detail(site_id, ppid):
    """Get details for a specific user"""
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        # Get user details
        cursor.execute("""
            SELECT id, user_ppid, display_name, role, status, added_by, added_at, last_seen, metadata
            FROM site_users
            WHERE site_id = %s AND user_ppid = %s
        """, (site_id, ppid))
        
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user = {
            'id': row[0],
            'ppid': row[1],
            'display_name': row[2],
            'role': row[3],
            'status': row[4],
            'added_by': row[5],
            'added_at': row[6].isoformat() if row[6] else None,
            'last_seen': row[7].isoformat() if row[7] else None,
            'metadata': row[8] or {}
        }
        
        # Get user's permissions
        cursor.execute("""
            SELECT spg.permission_id, p.display_name, spg.granted_at, spg.expires_at
            FROM site_permission_grants spg
            LEFT JOIN permissions p ON p.site_id = spg.site_id AND p.permission_id = spg.permission_id
            WHERE spg.site_id = %s AND spg.user_did = %s AND spg.is_active = true
        """, (site_id, ppid))
        
        permissions = []
        for prow in cursor.fetchall():
            permissions.append({
                'permission_id': prow[0],
                'display_name': prow[1],
                'granted_at': prow[2].isoformat() if prow[2] else None,
                'expires_at': prow[3].isoformat() if prow[3] else None
            })
        
        user['permissions'] = permissions
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'user': user})
        
    except Exception as e:
        logger.error(f"Failed to get user detail: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/<ppid>', methods=['PUT'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def update_site_user(site_id, ppid):
    """Update a user's display name or role
    
    NOTE: We deliberately DO NOT store internal_id - that would let Lemma correlate
    users across the developer's system, defeating PPID privacy. Developers should
    store the PPID -> internal_id mapping in THEIR OWN database.
    """
    try:
        from api.database import get_db_connection
        
        data = request.get_json() or {}
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        # Build update query - only allow display_name and role
        updates = []
        params = []
        
        if 'display_name' in data:
            updates.append("display_name = %s")
            params.append(data['display_name'])
        
        if 'role' in data and data['role'] in ['user', 'moderator', 'admin']:
            updates.append("role = %s")
            params.append(data['role'])
        
        if not updates:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'No valid fields to update (only display_name and role allowed)'}), 400
        
        params.extend([site_id, ppid])
        
        cursor.execute(f"""
            UPDATE site_users
            SET {', '.join(updates)}
            WHERE site_id = %s AND user_ppid = %s
            RETURNING id, display_name, role
        """, params)
        
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Updated user {ppid[:20]}... on site {site_id}")
        
        return jsonify({
            'success': True,
            'user': {
                'id': result[0],
                'display_name': result[1],
                'role': result[2]
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/<ppid>/revoke', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def revoke_site_user(site_id, ppid):
    """Revoke a user's access to the site"""
    try:
        from api.database import get_db_connection
        
        reason = (request.get_json(silent=True) or {}).get('reason', '') if request.is_json else ''
        revoked_meta = (
            f'{{"revoked_at": "{datetime.now(timezone.utc).isoformat()}"'
            + (f', "revoke_reason": {json.dumps(reason)}' if reason else '')
            + '}'
        )

        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        # Upsert + mark revoked. We intentionally do NOT 404 when the PPID is
        # not already a stored "site user": operators routinely block a PPID
        # pulled straight from their own logs, and the canonical tier-1
        # revocation below is what actually enforces the block network-wide.
        cursor.execute("""
            INSERT INTO site_users (site_id, user_ppid, status, added_by, metadata)
            VALUES (%s, %s, 'revoked', %s, %s::jsonb)
            ON CONFLICT (site_id, user_ppid)
            DO UPDATE SET
                status = 'revoked',
                metadata = COALESCE(site_users.metadata, '{}'::jsonb) || EXCLUDED.metadata
            RETURNING id
        """, (
            site_id,
            ppid,
            _actor_ppid_for_audit(),
            revoked_meta,
        ))
        
        # Also revoke all their active permissions
        cursor.execute("""
            UPDATE site_permission_grants
            SET is_active = false, revoked_at = NOW()
            WHERE site_id = %s AND user_did = %s AND is_active = true
        """, (site_id, ppid))
        
        revoked_permissions = cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()

        canonical_revocation = None
        try:
            from api.database import SessionLocal, Site
            from api.site_ppid_revocation import revoke_site_bound_ppid

            db = SessionLocal()
            try:
                site = db.query(Site).filter_by(site_id=site_id).first()
                canonical_revocation = revoke_site_bound_ppid(
                    db,
                    site_id=site_id,
                    ppid=ppid,
                    reason=reason or 'developer_site_user_revoke',
                    revoked_by=_actor_ppid_for_audit(),
                    site_domain=getattr(site, 'site_domain', None) if site else None,
                    blocked_by=_actor_ppid_for_audit(),
                )
            finally:
                db.close()
        except Exception as revoke_err:
            logger.warning(
                "IAM user revoked in site DB but canonical PPID revocation failed: %s",
                revoke_err,
            )
        
        logger.info(f"Revoked user {ppid[:20]}... from site {site_id} (permissions: {revoked_permissions})")

        capture_action_proof(action="site_user.revoke", site_id=site_id, resource=ppid)
        
        return jsonify({
            'success': True,
            'message': f'User revoked successfully',
            'revoked_permissions': revoked_permissions,
            'canonical_ppid_revocation': canonical_revocation,
        })
        
    except Exception as e:
        logger.error(f"Failed to revoke user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/<ppid>/unblock', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def unblock_site_user(site_id, ppid):
    """Lift a site-scoped block for a PPID (inverse of /revoke).

    Reverses tier-1 enforcement: deactivates the SiteBlock, removes the
    canonical user-scope RevocationList row, and rebuilds the Bloom so verifiers
    stop rejecting the PPID. The site_users row (if any) is set back to 'active'.
    """
    try:
        from api.database import get_db_connection

        canonical_clear = None
        try:
            from api.database import SessionLocal
            from api.site_ppid_revocation import clear_site_bound_ppid

            db = SessionLocal()
            try:
                canonical_clear = clear_site_bound_ppid(
                    db,
                    site_id=site_id,
                    ppid=ppid,
                    cleared_by=_actor_ppid_for_audit(),
                )
            finally:
                db.close()
        except Exception as clear_err:
            logger.warning("Canonical PPID unblock failed: %s", clear_err)
            return jsonify({'success': False, 'error': 'unblock_failed'}), 500

        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE site_users
            SET status = 'active',
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE site_id = %s AND user_ppid = %s
        """, (
            f'{{"unblocked_at": "{datetime.now(timezone.utc).isoformat()}"}}',
            site_id,
            ppid,
        ))
        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"Unblocked user {ppid[:20]}... on site {site_id}")
        capture_action_proof(action="site_user.unblock", site_id=site_id, resource=ppid)
        return jsonify({
            'success': True,
            'message': 'User unblocked successfully',
            'canonical_ppid_clear': canonical_clear,
        })

    except Exception as e:
        logger.error(f"Failed to unblock user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/export', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def export_site_users(site_id):
    """Export all users as CSV"""
    try:
        from api.database import get_db_connection
        import csv
        from io import StringIO
        from flask import Response
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_ppid, display_name, role, status, added_at, last_seen
            FROM site_users
            WHERE site_id = %s
            ORDER BY added_at DESC
        """, (site_id,))
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['PPID', 'Display Name', 'Role', 'Status', 'Added At', 'Last Seen'])
        
        for row in rows:
            writer.writerow([
                row[0],
                row[1] or '',
                row[2],
                row[3],
                row[4].isoformat() if row[4] else '',
                row[5].isoformat() if row[5] else ''
            ])
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={site_id}_users_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to export users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# PERMISSION TYPES API
# ============================================

@site_management_bp.route('/api/developer/sites/<site_id>/permissions', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_permission_types(site_id):
    """Get all permission types for a site"""
    try:
        from api.database import SessionLocal, Permission
        
        db = SessionLocal()
        
        permissions = db.query(Permission).filter(Permission.site_id == site_id).all()
        
        result = []
        for p in permissions:
            # Count users with this permission
            from api.database import get_db_connection
            conn = get_db_connection(site_id)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM site_permission_grants
                WHERE site_id = %s AND permission_id = %s AND is_active = true
            """, (site_id, p.permission_id))
            user_count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            result.append({
                'id': p.id,
                'permission_id': p.permission_id,
                'display_name': p.display_name,
                'scope': p.scope or {},
                'conditions': p.conditions or [],
                'delegation_allowed': p.delegation_allowed,
                'priority': p.priority,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'user_count': user_count
            })
        
        db.close()
        
        return jsonify({
            'success': True,
            'permissions': result
        })
        
    except Exception as e:
        logger.error(f"Failed to get permissions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/permissions', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def create_permission_type(site_id):
    """Create a new permission type"""
    try:
        data = request.get_json() or {}
        
        permission_id = data.get('permission_id', '').strip().lower().replace(' ', '_')
        display_name = data.get('display_name', '').strip()
        scope = data.get('scope', {})
        description = data.get('description', '')
        
        if not permission_id:
            return jsonify({'success': False, 'error': 'Permission ID is required'}), 400
        
        if not display_name:
            display_name = permission_id.replace('_', ' ').title()
        
        from api.database import SessionLocal, Permission
        
        db = SessionLocal()
        
        # Check for duplicate
        existing = db.query(Permission).filter(
            Permission.site_id == site_id,
            Permission.permission_id == permission_id
        ).first()
        
        if existing:
            db.close()
            return jsonify({'success': False, 'error': 'Permission ID already exists'}), 400
        
        # Create permission
        permission = Permission(
            site_id=site_id,
            permission_id=permission_id,
            display_name=display_name,
            scope=scope if scope else {'description': description},
            conditions=[],
            delegation_allowed=data.get('delegation_allowed', False),
            priority=data.get('priority', 0),
            created_at=datetime.now(timezone.utc),
            created_by=_actor_ppid_for_audit()
        )
        
        db.add(permission)
        db.commit()
        
        result = {
            'id': permission.id,
            'permission_id': permission.permission_id,
            'display_name': permission.display_name
        }
        
        db.close()
        
        logger.info(f"Created permission type {permission_id} for site {site_id}")

        capture_action_proof(action="permission.create", site_id=site_id, resource=permission_id)
        
        return jsonify({
            'success': True,
            'permission': result
        })
        
    except Exception as e:
        logger.error(f"Failed to create permission: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/permissions/<permission_id>', methods=['PUT'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def update_permission_type(site_id, permission_id):
    """Update a permission type"""
    try:
        data = request.get_json() or {}
        
        from api.database import SessionLocal, Permission
        
        db = SessionLocal()
        
        permission = db.query(Permission).filter(
            Permission.site_id == site_id,
            Permission.permission_id == permission_id
        ).first()
        
        if not permission:
            db.close()
            return jsonify({'success': False, 'error': 'Permission not found'}), 404
        
        # Update fields
        if 'display_name' in data:
            permission.display_name = data['display_name']
        if 'scope' in data:
            permission.scope = data['scope']
        if 'delegation_allowed' in data:
            permission.delegation_allowed = data['delegation_allowed']
        if 'priority' in data:
            permission.priority = data['priority']
        
        db.commit()
        db.close()
        
        logger.info(f"Updated permission type {permission_id} for site {site_id}")
        capture_action_proof(action="permission.update", site_id=site_id, resource=permission_id)
        return jsonify({
            'success': True,
            'message': 'Permission updated'
        })
        
    except Exception as e:
        logger.error(f"Failed to update permission: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/permissions/<permission_id>', methods=['DELETE'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def delete_permission_type(site_id, permission_id):
    """Delete a permission type"""
    try:
        from api.database import SessionLocal, Permission, get_db_connection
        
        db = SessionLocal()
        
        permission = db.query(Permission).filter(
            Permission.site_id == site_id,
            Permission.permission_id == permission_id
        ).first()
        
        if not permission:
            db.close()
            return jsonify({'success': False, 'error': 'Permission not found'}), 404
        
        # Check if permission is in use
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM site_permission_grants
            WHERE site_id = %s AND permission_id = %s AND is_active = true
        """, (site_id, permission_id))
        active_grants = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        if active_grants > 0:
            db.close()
            return jsonify({
                'success': False, 
                'error': f'Cannot delete: {active_grants} users have this permission'
            }), 400
        
        db.delete(permission)
        db.commit()
        db.close()
        
        logger.info(f"Deleted permission type {permission_id} from site {site_id}")
        capture_action_proof(action="permission.delete", site_id=site_id, resource=permission_id)
        return jsonify({
            'success': True,
            'message': 'Permission deleted'
        })
        
    except Exception as e:
        logger.error(f"Failed to delete permission: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/<ppid>/permissions', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def grant_user_permission(site_id, ppid):
    """Grant a permission to a user"""
    try:
        data = request.get_json() or {}
        permission_id = data.get('permission_id')
        
        if not permission_id:
            return jsonify({'success': False, 'error': 'Permission ID is required'}), 400
        
        from api.database import get_db_connection, SessionLocal, Permission
        
        # Verify permission exists
        db = SessionLocal()
        permission = db.query(Permission).filter(
            Permission.site_id == site_id,
            Permission.permission_id == permission_id
        ).first()
        
        if not permission:
            db.close()
            return jsonify({'success': False, 'error': 'Permission type not found'}), 404
        
        db.close()
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        # Check if already granted
        cursor.execute("""
            SELECT id FROM site_permission_grants
            WHERE site_id = %s AND user_did = %s AND permission_id = %s AND is_active = true
        """, (site_id, ppid, permission_id))
        
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'User already has this permission'}), 400
        
        # Grant permission
        granted_by = _actor_ppid_for_audit()
        cursor.execute("""
            INSERT INTO site_permission_grants (site_id, user_did, permission_id, granted_by, granted_at, is_active)
            VALUES (%s, %s, %s, %s, NOW(), true)
            RETURNING id
        """, (site_id, ppid, permission_id, granted_by))
        
        grant_id = cursor.fetchone()[0]
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Granted {permission_id} to user {ppid[:20]}... on site {site_id}")
        capture_action_proof(action="permission.grant", site_id=site_id, resource=f"{ppid}:{permission_id}")
        return jsonify({
            'success': True,
            'grant_id': grant_id,
            'message': f'Permission {permission_id} granted'
        })
        
    except Exception as e:
        logger.error(f"Failed to grant permission: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@site_management_bp.route('/api/developer/sites/<site_id>/users/<ppid>/permissions/<permission_id>', methods=['DELETE'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def revoke_user_permission(site_id, ppid, permission_id):
    """Revoke a permission from a user"""
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE site_permission_grants
            SET is_active = false, revoked_at = NOW()
            WHERE site_id = %s AND user_did = %s AND permission_id = %s AND is_active = true
            RETURNING id
        """, (site_id, ppid, permission_id))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Permission grant not found'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Revoked {permission_id} from user {ppid[:20]}... on site {site_id}")
        capture_action_proof(action="permission.revoke", site_id=site_id, resource=f"{ppid}:{permission_id}")
        return jsonify({
            'success': True,
            'message': f'Permission {permission_id} revoked'
        })
        
    except Exception as e:
        logger.error(f"Failed to revoke permission: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# SITE STATS
# ============================================

@site_management_bp.route('/api/developer/sites/<site_id>/stats', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_stats(site_id):
    """Get statistics for a site"""
    try:
        from api.database import get_db_connection, SessionLocal, Permission
        
        conn = get_db_connection(site_id)
        cursor = conn.cursor()
        
        # User counts by status
        cursor.execute("""
            SELECT status, COUNT(*) FROM site_users
            WHERE site_id = %s
            GROUP BY status
        """, (site_id,))
        
        status_counts = dict(cursor.fetchall())
        total_users = sum(status_counts.values())
        active_users = status_counts.get('active', 0)
        
        # Permission grant count
        cursor.execute("""
            SELECT COUNT(*) FROM site_permission_grants
            WHERE site_id = %s AND is_active = true
        """, (site_id,))
        active_permissions = cursor.fetchone()[0]
        
        # API key count
        cursor.execute("""
            SELECT COUNT(*) FROM site_api_keys
            WHERE site_id = %s AND is_active = true
        """, (site_id,))
        active_keys = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Permission type count
        db = SessionLocal()
        permission_types = db.query(Permission).filter(Permission.site_id == site_id).count()
        db.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'active_users': active_users,
                'revoked_users': status_counts.get('revoked', 0),
                'permission_types': permission_types,
                'active_permission_grants': active_permissions,
                'active_api_keys': active_keys
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get site stats: {e}")
        return jsonify({
            'success': True,
            'stats': {
                'total_users': 0,
                'active_users': 0,
                'revoked_users': 0,
                'permission_types': 0,
                'active_permission_grants': 0,
                'active_api_keys': 0
            }
        })
