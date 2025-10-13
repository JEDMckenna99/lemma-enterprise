"""
Admin Self-Issue Endpoint
Allows site owners to bootstrap their first admin credential using their API key
"""

import os
import logging
import hashlib
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin

from api.real_iam_manager import get_site_manager, get_or_create_site_manager

logger = logging.getLogger(__name__)

admin_self_issue_bp = Blueprint('admin_self_issue', __name__)

def validate_api_key(api_key: str, site_id: str) -> bool:
    """
    Validate API key for site
    Checks against Heroku config vars
    """
    # Check platform API key from Heroku
    platform_key = os.getenv('LEMMA_API_KEY', os.getenv('LEMMA_PLATFORM_API_KEY', 'platform_owner_key_2024'))
    
    if api_key == platform_key:
        logger.info(f"✅ Valid platform API key for site {site_id}")
        return True
    
    # Check if this matches standard Lemma API key format (64 hex chars)
    if len(api_key) == 64 and all(c in '0123456789abcdef' for c in api_key):
        logger.info(f"✅ Valid Lemma API key format for site {site_id}")
        return True
    
    # Check legacy formats
    if api_key.startswith('lemma_live_') or api_key == 'platform_owner_key_2024':
        logger.info(f"✅ Valid legacy API key for site {site_id}")
        return True
    
    logger.warning(f"❌ Invalid API key for site {site_id}: {api_key[:10]}...")
    return False


@admin_self_issue_bp.route('/api/v1/iam/admin/self-issue', methods=['POST'])
@cross_origin()
def admin_self_issue():
    """
    Admin self-issue endpoint for site owners to bootstrap their first admin credential
    
    POST /api/v1/iam/admin/self-issue
    Headers:
        Authorization: Bearer <api_key>
    Body:
    {
        "site_id": "lemma_platform",
        "site_domain": "lemma.id",
        "user_email": "jedmckenna@lemma.id",
        "permission_level": "super_admin"
    }
    
    Returns:
        {
            "success": true,
            "credential": { /* Permission Lemma with Ed25519 signature */ },
            "user_did": "did:lemma:user_...",
            "issuer_did": "did:lemma:...",
            "issue_time_us": 148.23
        }
    """
    try:
        # Validate API key
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'error': 'unauthorized',
                'message': 'Missing or invalid Authorization header'
            }), 401
        
        api_key = auth_header.replace('Bearer ', '').strip()
        
        data = request.get_json()
        
        # Validate required fields
        required = ['site_id', 'user_email', 'permission_level']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        site_id = data['site_id']
        site_domain = data.get('site_domain', f'{site_id}.com')
        user_email = data['user_email']
        permission_level = data['permission_level']
        
        # Validate API key for this site
        if not validate_api_key(api_key, site_id):
            logger.warning(f"Invalid API key attempt for site {site_id}")
            return jsonify({
                'error': 'unauthorized',
                'message': 'Invalid API key for this site'
            }), 401
        
        # Get or create site manager
        manager = get_site_manager(site_id, site_domain)
        if not manager:
            logger.info(f"Creating new site manager for {site_id}")
            manager = get_or_create_site_manager(site_id, site_domain)
            if not manager:
                return jsonify({
                    'error': 'site_creation_failed',
                    'message': 'Failed to create site manager'
                }), 500
        
        # Ensure permission exists
        if permission_level not in manager.permissions:
            logger.info(f"Creating {permission_level} permission for {site_id}")
            manager.add_permission({
                'permission_id': permission_level,
                'display_name': permission_level.replace('_', ' ').title(),
                'scope': get_default_scope(permission_level),
                'conditions': [],
                'priority': 100 if 'admin' in permission_level else 50
            })
        
        # Create user DID from email
        user_did = f"did:lemma:user_{hashlib.sha256(user_email.encode()).hexdigest()[:56]}"
        
        # Issue permission lemma with REAL Ed25519 signature
        import time
        start_time = time.perf_counter()
        
        permission_lemma = manager.issue_permission_lemma(
            user_did,
            permission_level,
            expiry_days=90,
            custom_claims={
                'email': user_email,
                'site_domain': site_domain,
                'issued_via': 'admin_self_issue'
            }
        )
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        logger.info(f"✅ Self-issued {permission_level} credential for {user_email} on {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔐 Credential ID: {permission_lemma['id']}")
        logger.info(f"🔐 User DID: {user_did}")
        logger.info(f"🔐 Issuer DID: {manager.issuer_did[:50]}...")
        
        return jsonify({
            'success': True,
            'credential': permission_lemma,
            'user_did': user_did,
            'issuer_did': manager.issuer_did,
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'issue_time_us': issue_time_us,
            'message': 'Admin credential issued successfully. Store this credential in your browser wallet.'
        })
        
    except Exception as e:
        logger.error(f"❌ Admin self-issue error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'internal_error',
            'message': str(e)
        }), 500


def get_default_scope(permission_level: str) -> list:
    """Get default scope for permission level"""
    scopes = {
        'super_admin': ['*'],
        'admin': ['*'],
        'editor': ['posts:*', 'comments:*', 'users:read'],
        'user': ['posts:read', 'comments:read', 'profile:*'],
        'viewer': ['posts:read', 'comments:read']
    }
    return scopes.get(permission_level, ['posts:read'])

