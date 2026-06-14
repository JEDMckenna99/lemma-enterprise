"""
Permission Type Management API
==============================

Allows site admins to define and manage permission types for their sites.
This is the developer-facing API for configuring what permissions their site offers.

Supports two authentication methods:
1. API Key in Authorization header (for SDK/server-to-server calls)
2. Credential in Authorization header (for platform UI)

Endpoints:
- GET  /api/v1/sites/{site_id}/permission-types         - List permission types
- POST /api/v1/sites/{site_id}/permission-types         - Create permission type
- GET  /api/v1/sites/{site_id}/permission-types/{name}  - Get permission type
- PUT  /api/v1/sites/{site_id}/permission-types/{name}  - Update permission type
- DELETE /api/v1/sites/{site_id}/permission-types/{name} - Delete permission type
- GET  /api/v1/permission-templates                     - Get standard templates
"""

import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from auth.decorators import require_customer_or_admin

logger = logging.getLogger(__name__)

permission_type_api = Blueprint('permission_type_api', __name__)


def _verify_site_access(site_id: str) -> bool:
    """
    Verify the request has admin access to this site.

    Uses verified credentials (X-Lemma-Credential) or validated API keys only.
    """
    from auth.request_principal import resolve_admin_principal

    principal, _admin_error = resolve_admin_principal()
    if principal:
        return True

    from api.site_access import verify_site_ownership, get_authenticated_ppid
    from auth.decorators import extract_authenticated_ppid_from_request
    from api.authz_engine import extract_user_lemma_principal

    principal, _error = extract_user_lemma_principal(request.headers)
    if principal and principal.ppid:
        if verify_site_ownership(site_id, principal.ppid):
            return True
        if principal.permission_id in ("admin_access", "super_admin"):
            return True

    ppid = get_authenticated_ppid() or extract_authenticated_ppid_from_request()
    if ppid and verify_site_ownership(site_id, ppid):
        return True

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    token = auth_header.replace("Bearer ", "").strip()
    if not (token.startswith("lemma_") or token.startswith("lm_")):
        return False

    from api.customer_accounts import customer_manager

    validation = customer_manager.validate_api_key(token)
    if validation.get("valid") and validation.get("site_id") == site_id:
        return True

    from api.database import SessionLocal, Site

    db = SessionLocal()
    try:
        row = db.query(Site).filter(Site.site_id == site_id, Site.api_key == token).first()
        return row is not None
    except Exception as exc:
        logger.warning("Site access check failed: %s", exc)
        return False
    finally:
        db.close()


@permission_type_api.route('/api/v1/sites/<site_id>/permission-types', methods=['GET'])
@cross_origin()
def list_permission_types(site_id):
    """
    List all permission types for a site.
    
    Returns both custom types and available templates.
    """
    try:
        if not _verify_site_access(site_id):
            return jsonify({
                'success': False,
                'error': 'unauthorized',
                'message': 'You do not have admin access to this site'
            }), 401
        
        from .database import get_db
        from sqlalchemy import text
        
        db = get_db()
        try:
            # Get site's permission types
            result = db.execute(text("""
                SELECT id, name, type, description, config, created_at, active
                FROM permission_types
                WHERE site_id = :site_id
                ORDER BY name
            """), {'site_id': site_id}).fetchall()
            
            permission_types = []
            for row in result:
                permission_types.append({
                    'id': row[0],
                    'name': row[1],
                    'type': row[2],
                    'description': row[3],
                    'config': row[4] if isinstance(row[4], dict) else json.loads(row[4] or '{}'),
                    'created_at': row[5].isoformat() if row[5] else None,
                    'active': row[6]
                })
            
            return jsonify({
                'success': True,
                'permission_types': permission_types,
                'count': len(permission_types)
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"List permission types error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@permission_type_api.route('/api/v1/sites/<site_id>/permission-types', methods=['POST'])
@cross_origin()
@require_customer_or_admin
def create_permission_type(site_id):
    """
    Create a new permission type for a site.
    
    POST body:
    {
        "name": "editor",
        "type": "role",  // role, subscription, time-bound, scope
        "description": "Can edit content",
        "config": {
            "scopes": ["content:read", "content:write"],
            "duration_days": null  // for time-bound
        }
    }
    """
    try:
        if not _verify_site_access(site_id):
            return jsonify({
                'success': False,
                'error': 'unauthorized'
            }), 401
        
        data = request.get_json() or {}
        name = data.get('name', '').strip().lower()
        perm_type = data.get('type', 'role')
        description = data.get('description', '')
        config = data.get('config', {})
        
        if not name:
            return jsonify({
                'success': False,
                'error': 'name is required'
            }), 400
        
        # Validate name format (alphanumeric, underscores, hyphens)
        import re
        if not re.match(r'^[a-z0-9_-]+$', name):
            return jsonify({
                'success': False,
                'error': 'Invalid name format. Use lowercase letters, numbers, underscores, hyphens.'
            }), 400
        
        # Validate type
        valid_types = ['role', 'subscription', 'time-bound', 'scope']
        if perm_type not in valid_types:
            return jsonify({
                'success': False,
                'error': f'Invalid type. Must be one of: {", ".join(valid_types)}'
            }), 400
        
        from .database import get_db
        from sqlalchemy import text
        
        db = get_db()
        try:
            # Check if name already exists
            existing = db.execute(text("""
                SELECT id FROM permission_types
                WHERE site_id = :site_id AND name = :name
            """), {'site_id': site_id, 'name': name}).fetchone()
            
            if existing:
                return jsonify({
                    'success': False,
                    'error': f'Permission type "{name}" already exists'
                }), 400
            
            # Insert new permission type
            db.execute(text("""
                INSERT INTO permission_types (site_id, name, type, description, config, created_by, active)
                VALUES (:site_id, :name, :type, :description, :config, 'api', true)
            """), {
                'site_id': site_id,
                'name': name,
                'type': perm_type,
                'description': description,
                'config': json.dumps(config)
            })
            db.commit()
            
            logger.info(f"✅ Created permission type '{name}' for site {site_id}")
            
            return jsonify({
                'success': True,
                'message': f'Permission type "{name}" created',
                'permission_type': {
                    'name': name,
                    'type': perm_type,
                    'description': description,
                    'config': config
                }
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Create permission type error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@permission_type_api.route('/api/v1/sites/<site_id>/permission-types/<name>', methods=['GET'])
@cross_origin()
def get_permission_type(site_id, name):
    """Get a specific permission type."""
    try:
        if not _verify_site_access(site_id):
            return jsonify({'success': False, 'error': 'unauthorized'}), 401
        
        from .database import get_db
        from sqlalchemy import text
        
        db = get_db()
        try:
            result = db.execute(text("""
                SELECT id, name, type, description, config, created_at, active
                FROM permission_types
                WHERE site_id = :site_id AND name = :name
            """), {'site_id': site_id, 'name': name}).fetchone()
            
            if not result:
                return jsonify({
                    'success': False,
                    'error': f'Permission type "{name}" not found'
                }), 404
            
            return jsonify({
                'success': True,
                'permission_type': {
                    'id': result[0],
                    'name': result[1],
                    'type': result[2],
                    'description': result[3],
                    'config': result[4] if isinstance(result[4], dict) else json.loads(result[4] or '{}'),
                    'created_at': result[5].isoformat() if result[5] else None,
                    'active': result[6]
                }
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Get permission type error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@permission_type_api.route('/api/v1/sites/<site_id>/permission-types/<name>', methods=['PUT'])
@cross_origin()
@require_customer_or_admin
def update_permission_type(site_id, name):
    """
    Update a permission type.
    
    PUT body (all fields optional):
    {
        "description": "Updated description",
        "config": { ... },
        "active": true/false
    }
    """
    try:
        if not _verify_site_access(site_id):
            return jsonify({'success': False, 'error': 'unauthorized'}), 401
        
        data = request.get_json() or {}
        
        from .database import get_db
        from sqlalchemy import text
        
        db = get_db()
        try:
            # Check if exists
            existing = db.execute(text("""
                SELECT id FROM permission_types
                WHERE site_id = :site_id AND name = :name
            """), {'site_id': site_id, 'name': name}).fetchone()
            
            if not existing:
                return jsonify({
                    'success': False,
                    'error': f'Permission type "{name}" not found'
                }), 404
            
            # Build update query
            updates = []
            params = {'site_id': site_id, 'name': name}
            
            if 'description' in data:
                updates.append('description = :description')
                params['description'] = data['description']
            
            if 'config' in data:
                updates.append('config = :config')
                params['config'] = json.dumps(data['config'])
            
            if 'active' in data:
                updates.append('active = :active')
                params['active'] = data['active']
            
            if 'type' in data:
                updates.append('type = :type')
                params['type'] = data['type']
            
            if not updates:
                return jsonify({
                    'success': False,
                    'error': 'No fields to update'
                }), 400
            
            db.execute(text(f"""
                UPDATE permission_types
                SET {', '.join(updates)}
                WHERE site_id = :site_id AND name = :name
            """), params)
            db.commit()
            
            logger.info(f"✅ Updated permission type '{name}' for site {site_id}")
            
            return jsonify({
                'success': True,
                'message': f'Permission type "{name}" updated'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Update permission type error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@permission_type_api.route('/api/v1/sites/<site_id>/permission-types/<name>', methods=['DELETE'])
@cross_origin()
@require_customer_or_admin
def delete_permission_type(site_id, name):
    """
    Delete a permission type (soft delete - sets active=false).
    
    Note: This doesn't revoke existing permissions of this type.
    """
    try:
        if not _verify_site_access(site_id):
            return jsonify({'success': False, 'error': 'unauthorized'}), 401
        
        from .database import get_db
        from sqlalchemy import text
        
        db = get_db()
        try:
            # Soft delete (set active=false)
            result = db.execute(text("""
                UPDATE permission_types
                SET active = false
                WHERE site_id = :site_id AND name = :name
                RETURNING id
            """), {'site_id': site_id, 'name': name}).fetchone()
            
            if not result:
                return jsonify({
                    'success': False,
                    'error': f'Permission type "{name}" not found'
                }), 404
            
            db.commit()
            
            logger.info(f"✅ Deleted (deactivated) permission type '{name}' for site {site_id}")
            
            return jsonify({
                'success': True,
                'message': f'Permission type "{name}" deleted'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Delete permission type error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@permission_type_api.route('/api/v1/permission-templates', methods=['GET'])
@cross_origin()
def get_permission_templates():
    """
    Get standard permission templates that sites can use.
    No authentication required - public endpoint.
    """
    templates = [
        {
            'name': 'viewer',
            'type': 'role',
            'description': 'Read-only access',
            'config': {'scopes': ['content:read']}
        },
        {
            'name': 'member',
            'type': 'role',
            'description': 'Standard member access',
            'config': {'scopes': ['content:read', 'content:write', 'profile:manage']}
        },
        {
            'name': 'moderator',
            'type': 'role',
            'description': 'Content moderation access',
            'config': {'scopes': ['content:read', 'content:write', 'content:moderate', 'users:view']}
        },
        {
            'name': 'admin',
            'type': 'role',
            'description': 'Full site administration',
            'config': {'scopes': ['*']}
        },
        {
            'name': 'trial',
            'type': 'time-bound',
            'description': '14-day trial access',
            'config': {'duration_days': 14, 'scopes': ['content:read', 'content:write']}
        },
        {
            'name': 'premium',
            'type': 'subscription',
            'description': 'Premium subscription access',
            'config': {'scopes': ['content:read', 'content:write', 'features:premium']}
        }
    ]
    
    return jsonify({
        'success': True,
        'templates': templates,
        'count': len(templates)
    })


# Register blueprint function
def register_permission_type_api(app):
    app.register_blueprint(permission_type_api)
    logger.info("✅ Permission Type API registered")
