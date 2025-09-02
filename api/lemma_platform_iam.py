"""
Lemma Platform IAM Setup
Sets up lemma.id to use the same IAM system provided to customers
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from datetime import datetime, timedelta
import logging
import secrets

from .database import get_db, Site, Permission, SitePermissionGrant, UserLemma
from .iam_subnet_manager import IAMSubnetManager

logger = logging.getLogger(__name__)

lemma_platform_iam_bp = Blueprint('lemma_platform_iam', __name__)

def initialize_lemma_platform_iam():
    """Initialize lemma.id as a site in the IAM system (same as customers)"""
    try:
        db = get_db()
        
        # Check if lemma.id site already exists
        existing_site = db.query(Site).filter(Site.site_domain == 'lemma.id').first()
        
        if not existing_site:
            # Create lemma.id as a site (same as customer sites)
            site_id = 'lemma_platform'
            api_key = f"lemma_platform_{secrets.token_hex(16)}"
            oauth_client_id = f"lemma_oauth_{site_id}"
            oauth_client_secret = secrets.token_hex(32)
            
            site = Site(
                site_id=site_id,
                site_domain='lemma.id',
                company_name='Lemma Platform',
                admin_email='admin@lemma.id',
                plan='enterprise',
                api_key=api_key,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                created_at=datetime.utcnow()
            )
            
            db.add(site)
            db.commit()
            
            logger.info(f"✅ Initialized lemma.id as IAM site: {site_id}")
            
            # Create default permissions
            default_permissions = [
                {
                    'permission_id': 'admin_access',
                    'display_name': 'Administrator Access',
                    'scope': ['users:*', 'sites:*', 'permissions:*', 'billing:*', 'analytics:*'],
                    'description': 'Full platform administration access'
                },
                {
                    'permission_id': 'customer_access',
                    'display_name': 'Customer Access', 
                    'scope': ['profile:read', 'profile:write', 'billing:read', 'usage:read'],
                    'description': 'Standard customer dashboard access'
                },
                {
                    'permission_id': 'content_editor',
                    'display_name': 'Content Editor',
                    'scope': ['content:read', 'content:write', 'content:publish'],
                    'description': 'Edit and publish platform content'
                },
                {
                    'permission_id': 'analytics_viewer',
                    'display_name': 'Analytics Viewer',
                    'scope': ['analytics:read', 'reports:read'],
                    'description': 'View platform analytics and reports'
                }
            ]
            
            for perm_data in default_permissions:
                permission = Permission(
                    site_id=site_id,
                    permission_id=perm_data['permission_id'],
                    display_name=perm_data['display_name'],
                    scope=perm_data['scope'],
                    conditions=[],
                    delegation_allowed=False,
                    priority=0,
                    created_at=datetime.utcnow(),
                    created_by='system_init'
                )
                db.add(permission)
            
            db.commit()
            logger.info(f"✅ Created {len(default_permissions)} default permissions for lemma.id")
            
            db.close()
            return {
                'success': True,
                'site_id': site_id,
                'api_key': api_key,
                'permissions_created': len(default_permissions)
            }
        else:
            logger.info("✅ lemma.id site already exists in IAM system")
            db.close()
            return {
                'success': True,
                'site_id': existing_site.site_id,
                'message': 'Site already initialized'
            }
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize lemma.id IAM: {e}")
        return {
            'success': False,
            'error': str(e)
        }

@lemma_platform_iam_bp.route('/api/admin/init-platform-iam', methods=['POST'])
@cross_origin()
def init_platform_iam():
    """Initialize lemma.id platform IAM (admin endpoint)"""
    try:
        # Verify admin access (simple check for now)
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Admin '):
            return jsonify({
                'success': False,
                'error': 'Admin authorization required'
            }), 401
        
        # Initialize the platform IAM
        result = initialize_lemma_platform_iam()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Lemma platform IAM initialized successfully',
                'site_id': result.get('site_id'),
                'api_key': result.get('api_key'),
                'permissions_created': result.get('permissions_created', 0)
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Initialization failed')
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Platform IAM init error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@lemma_platform_iam_bp.route('/api/admin/platform-permissions', methods=['GET'])
@cross_origin()
def get_platform_permissions():
    """Get all permissions for lemma.id platform"""
    try:
        db = get_db()
        
        # Get lemma.id site
        site = db.query(Site).filter(Site.site_domain == 'lemma.id').first()
        if not site:
            return jsonify({
                'success': False,
                'error': 'Platform site not found - run init first'
            }), 404
        
        # Get all permissions for the site
        permissions = db.query(Permission).filter(Permission.site_id == site.site_id).all()
        
        permission_data = []
        for perm in permissions:
            permission_data.append({
                'permission_id': perm.permission_id,
                'display_name': perm.display_name,
                'description': perm.description,
                'scope': perm.scope,
                'conditions': perm.conditions,
                'delegation_allowed': perm.delegation_allowed,
                'priority': perm.priority,
                'created_at': perm.created_at.isoformat(),
                'created_by': perm.created_by
            })
        
        db.close()
        
        return jsonify({
            'success': True,
            'site_id': site.site_id,
            'permissions': permission_data
        })
        
    except Exception as e:
        logger.error(f"❌ Get platform permissions error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
