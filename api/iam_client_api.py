"""
IAM Client API - Complete Site Control Endpoints
Provides full IAM subnet management for client sites
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from .iam_subnet_manager import get_subnet_manager
from .auth.decorators import require_api_key, require_site_admin
import logging

logger = logging.getLogger(__name__)

iam_client_api = Blueprint('iam_client_api', __name__)

# ================================================================================
# USER MANAGEMENT ENDPOINTS - Complete Client Control
# ================================================================================

@iam_client_api.route('/api/v1/sites/<site_id>/users', methods=['POST'])
@cross_origin()
@require_site_admin
def add_site_user(site_id):
    """
    Add user to IAM subnet (client has complete control)
    
    POST /api/v1/sites/{site_id}/users
    {
        "user_did": "did:lemma:user123",  // Optional: auto-generated if not provided
        "email": "user@example.com",
        "display_name": "John Doe",
        "role": "user",                   // Site-defined role
        "status": "active",               // active, pending, suspended
        "metadata": {                     // Site-specific data
            "department": "Engineering",
            "employee_id": "EMP001",
            "custom_fields": {}
        }
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')  # From auth decorator
        
        manager = get_subnet_manager(site_id)
        result = manager.add_user(admin_did, data)
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"❌ Add site user failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/users/<user_did>', methods=['PUT'])
@cross_origin()
@require_site_admin
def update_site_user(site_id, user_did):
    """
    Update user information (client has complete control)
    
    PUT /api/v1/sites/{site_id}/users/{user_did}
    {
        "display_name": "John Smith",
        "user_status": "suspended",
        "user_role": "admin",
        "user_metadata": {
            "department": "Management"
        }
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.update_user(admin_did, user_did, data)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Update site user failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/users/<user_did>', methods=['DELETE'])
@cross_origin()
@require_site_admin
def remove_site_user(site_id, user_did):
    """
    Remove user from site (client has complete control)
    
    DELETE /api/v1/sites/{site_id}/users/{user_did}?reason=violation
    """
    try:
        reason = request.args.get('reason', 'Removed by admin')
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.remove_user(admin_did, user_did, reason)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Remove site user failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/users', methods=['GET'])
@cross_origin()
@require_site_admin
def list_site_users(site_id):
    """
    List all users on site (client has complete visibility)
    
    GET /api/v1/sites/{site_id}/users?status=active&role=admin&search=john
    """
    try:
        filters = {
            'status': request.args.get('status'),
            'role': request.args.get('role'),
            'search': request.args.get('search')
        }
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}
        
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.list_users(admin_did, filters)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ List site users failed: {e}")
        return jsonify({'error': str(e)}), 500

# ================================================================================
# PERMISSION MANAGEMENT ENDPOINTS - Complete Client Control
# ================================================================================

@iam_client_api.route('/api/v1/sites/<site_id>/permissions', methods=['POST'])
@cross_origin()
@require_site_admin
def create_site_permission(site_id):
    """
    Create custom permission for site (client defines their own permissions)
    
    POST /api/v1/sites/{site_id}/permissions
    {
        "permission_id": "manage_products",
        "display_name": "Manage Products",
        "description": "Can create, edit, and delete products",
        "scope": [
            "products:create",
            "products:edit",
            "products:delete",
            "products:view"
        ],
        "conditions": [
            "ip_range:192.168.1.0/24",
            "time_range:09:00-17:00"
        ],
        "delegation_allowed": false,
        "priority": 10
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.create_permission(admin_did, data)
        
        return jsonify(result), 201 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Create site permission failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions', methods=['POST'])
@cross_origin()
@require_site_admin
def grant_user_permission(site_id, user_did):
    """
    Grant permission to user (client has complete control)
    
    POST /api/v1/sites/{site_id}/users/{user_did}/permissions
    {
        "permission_id": "manage_products",
        "expires_days": 90,
        "conditions": {
            "ip_whitelist": ["192.168.1.100"],
            "require_2fa": true
        }
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.grant_permission(
            admin_did,
            user_did,
            data['permission_id'],
            data.get('conditions'),
            data.get('expires_days', 90)
        )
        
        return jsonify(result), 201 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Grant user permission failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions/<permission_id>', methods=['DELETE'])
@cross_origin()
@require_site_admin
def revoke_user_permission(site_id, user_did, permission_id):
    """
    Revoke permission from user (client has complete control)
    
    DELETE /api/v1/sites/{site_id}/users/{user_did}/permissions/{permission_id}?reason=policy_violation
    """
    try:
        reason = request.args.get('reason', 'Revoked by admin')
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.revoke_permission(admin_did, user_did, permission_id, reason)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Revoke user permission failed: {e}")
        return jsonify({'error': str(e)}), 500

# ================================================================================
# ROLE MANAGEMENT ENDPOINTS - Simplified Permission Bundles
# ================================================================================

@iam_client_api.route('/api/v1/sites/<site_id>/roles', methods=['POST'])
@cross_origin()
@require_site_admin
def create_site_role(site_id):
    """
    Create permission role for easier management (client defines roles)
    
    POST /api/v1/sites/{site_id}/roles
    {
        "role_id": "product_manager",
        "role_name": "Product Manager",
        "description": "Can manage products and view analytics",
        "permissions": [
            "manage_products",
            "view_analytics",
            "manage_categories"
        ],
        "is_default": false
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.create_role(admin_did, data)
        
        return jsonify(result), 201 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Create site role failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/users/<user_did>/role', methods=['PUT'])
@cross_origin()
@require_site_admin
def assign_user_role(site_id, user_did):
    """
    Assign role to user (grants all role permissions)
    
    PUT /api/v1/sites/{site_id}/users/{user_did}/role
    {
        "role_id": "product_manager"
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.assign_role(admin_did, user_did, data['role_id'])
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Assign user role failed: {e}")
        return jsonify({'error': str(e)}), 500

# ================================================================================
# SITE CONFIGURATION ENDPOINTS - Complete Client Control
# ================================================================================

@iam_client_api.route('/api/v1/sites/<site_id>/config', methods=['PUT'])
@cross_origin()
@require_site_admin
def update_site_configuration(site_id):
    """
    Update site IAM configuration (client has complete control)
    
    PUT /api/v1/sites/{site_id}/config
    {
        "allow_self_registration": false,
        "require_email_verification": true,
        "default_user_role": "user",
        "session_timeout_minutes": 480,
        "permission_inheritance": true,
        "require_2fa_for_admin": true,
        "oauth_enabled": true,
        "oauth_scopes": ["profile", "permissions"],
        "oauth_redirect_uris": ["https://yoursite.com/callback"],
        "site_name": "Your Company",
        "site_logo_url": "https://yoursite.com/logo.png",
        "webhook_url": "https://yoursite.com/webhooks/lemma",
        "webhook_events": ["user.created", "permission.granted", "permission.revoked"],
        "ip_whitelist": ["192.168.1.0/24"],
        "rate_limit_per_minute": 60
    }
    """
    try:
        data = request.get_json()
        admin_did = request.headers.get('X-Admin-DID')
        
        manager = get_subnet_manager(site_id)
        result = manager.update_site_config(admin_did, data)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        logger.error(f"❌ Update site config failed: {e}")
        return jsonify({'error': str(e)}), 500

# ================================================================================
# ANALYTICS & REPORTING ENDPOINTS - Complete Visibility
# ================================================================================

@iam_client_api.route('/api/v1/sites/<site_id>/analytics/users', methods=['GET'])
@cross_origin()
@require_site_admin
def get_user_analytics(site_id):
    """
    Get user analytics for the site
    
    GET /api/v1/sites/{site_id}/analytics/users?period=30d
    """
    try:
        # This would integrate with NetworkActivity table for analytics
        return jsonify({
            'success': True,
            'site_id': site_id,
            'analytics': {
                'total_users': 0,
                'active_users_30d': 0,
                'new_users_30d': 0,
                'user_growth_rate': 0.0,
                'top_permissions': [],
                'login_frequency': {},
                'user_status_breakdown': {
                    'active': 0,
                    'suspended': 0,
                    'pending': 0
                }
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Get user analytics failed: {e}")
        return jsonify({'error': str(e)}), 500

@iam_client_api.route('/api/v1/sites/<site_id>/analytics/permissions', methods=['GET'])
@cross_origin()
@require_site_admin
def get_permission_analytics(site_id):
    """
    Get permission usage analytics
    
    GET /api/v1/sites/{site_id}/analytics/permissions?period=30d
    """
    try:
        return jsonify({
            'success': True,
            'site_id': site_id,
            'analytics': {
                'total_permissions': 0,
                'most_used_permissions': [],
                'permission_grants_30d': 0,
                'permission_revocations_30d': 0,
                'average_permissions_per_user': 0.0,
                'role_distribution': {}
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Get permission analytics failed: {e}")
        return jsonify({'error': str(e)}), 500
