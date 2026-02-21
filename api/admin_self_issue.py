"""
Admin Self-Issue Endpoint

BOOTSTRAP ENDPOINT for issuing the first admin credential to a new site.

Authentication: API key (Bearer token) - this is intentionally different from
lemma-based auth since this is used to CREATE the first lemma.

Use cases:
1. Platform admin bootstrapping their admin credential
2. New customer setting up their first site admin
3. Server-side automation for site provisioning

For all other admin operations, use @require_site_admin protected endpoints.
"""

import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from auth.decorators import require_api_key

from api.real_iam_manager import get_site_manager, get_or_create_site_manager
from api.ppid import derive_ppid_did

logger = logging.getLogger(__name__)

admin_self_issue_bp = Blueprint('admin_self_issue', __name__)


def validate_api_key(api_key: str, site_id: str) -> bool:
    """
    Validate API key for site.
    
    Checks:
    1. Platform API key (LEMMA_API_KEY env var)
    2. Standard Lemma API key format (from customer registration)
    3. Legacy formats for backward compatibility
    """
    # Check platform API key from environment
    platform_key = os.getenv('LEMMA_API_KEY', os.getenv('LEMMA_PLATFORM_API_KEY'))
    
    if platform_key and api_key == platform_key:
        logger.info(f"Valid platform API key for site {site_id}")
        return True
    
    # Check against customer's registered API keys
    from api.customer_accounts import customer_manager
    customer = customer_manager.get_customer_by_api_key(api_key)
    if customer:
        # Verify customer has registered this site
        owned_sites = [s.get('site_id') for s in (customer.sites or [])]
        owned_domains = [s.get('site_domain') for s in (customer.sites or [])]
        
        if site_id in owned_sites or site_id in owned_domains:
            logger.info(f"Valid customer API key for site {site_id}")
            return True
        
        # For platform-level sites, allow if customer is admin
        if site_id in ('lemma.id', 'lemma_platform') and customer.role == 'admin':
            logger.info(f"Valid admin API key for platform site {site_id}")
            return True
    
    # Check if this matches standard Lemma API key format (lemma_ prefix + 32 chars)
    if api_key.startswith('lemma_') and len(api_key) >= 38:
        # Validate against customer database
        customer = customer_manager.get_customer_by_api_key(api_key)
        if customer:
            logger.info(f"Valid Lemma API key for site {site_id}")
            return True
    
    logger.warning(f"Invalid API key for site {site_id}")
    return False


@admin_self_issue_bp.route('/api/v1/iam/admin/self-issue', methods=['POST'])
@cross_origin()
@require_api_key
def admin_self_issue():
    """
    Admin self-issue endpoint for site owners to bootstrap their first admin credential
    
    POST /api/v1/iam/admin/self-issue
    Headers:
        Authorization: Bearer <api_key>
        X-Lemma-PPID: did:lemma:ppid_xxx (optional - wallet-derived PPID)
    Body:
    {
        "site_id": "lemma_platform",
        "site_domain": "lemma.id",
        "user_email": "jedmckenna@lemma.id",
        "permission_level": "super_admin",
        "user_ppid": "did:lemma:ppid_xxx" (optional - wallet-derived PPID)
    }
    
    Returns:
        {
            "success": true,
            "credential": { /* Permission Lemma with Ed25519 signature */ },
            "user_did": "did:lemma:ppid_...",
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
        
        data = request.get_json(silent=True) or {}
        
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
        
        # Get user DID - prefer wallet-derived PPID if provided
        # Priority: 1) Header 2) Body 3) Derive from email (legacy)
        user_did = request.headers.get('X-Lemma-PPID')
        
        if not user_did or not user_did.startswith('did:lemma:ppid_'):
            user_did = data.get('user_ppid')
        
        if not user_did or not user_did.startswith('did:lemma:ppid_'):
            # Fall back to email-based derivation (legacy)
            logger.warning(f"No wallet PPID provided, falling back to email-derived DID")
            user_did = derive_ppid_did(user_email, site_domain)

        # Ensure SiteAdmin ownership record exists/updated for this admin DID.
        try:
            from api.database import SessionLocal, SiteAdmin
            db = SessionLocal()
            try:
                admin_record = db.query(SiteAdmin).filter(
                    SiteAdmin.site_id == site_id,
                    SiteAdmin.admin_did == user_did
                ).first()

                if admin_record:
                    admin_record.admin_email = user_email
                    admin_record.admin_role = 'owner' if admin_record.admin_role == 'owner' else 'admin'
                    admin_record.is_active = True
                    admin_record.last_activity = datetime.utcnow()
                else:
                    db.add(SiteAdmin(
                        site_id=site_id,
                        admin_did=user_did,
                        admin_email=user_email,
                        admin_role='owner',
                        permissions=['users', 'permissions', 'billing'],
                        added_by='self_issue',
                        is_active=True,
                        last_activity=datetime.utcnow()
                    ))
                db.commit()
            finally:
                db.close()
        except Exception as upsert_err:
            logger.warning(f"SiteAdmin upsert failed (non-fatal) for {site_id}: {upsert_err}")
        
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
                'issued_via': 'admin_self_issue',
                'accountType': 'admin',  # CRITICAL for session-free auth
                'permissionId': permission_level  # Use actual permission level (super_admin, admin, etc)
            }
        )
        
        # CRITICAL: Add W3C type field for credential classification
        # Rust issuer doesn't include this, so we add it in Python
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'  # For wallet filtering
        
        # Ensure claims/credentialSubject has packageType
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        logger.info(f"✅ Self-issued {permission_level} PERMISSION credential for {user_email} on {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔐 Credential ID: {permission_lemma['id']}")
        logger.info(f"🔐 Type: {permission_lemma['type']}")
        logger.info(f"🔐 Package Type: {permission_lemma.get('packageType', 'MISSING!')}")
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

