"""
Developer Self-Issue API
Allows developers to issue permission credentials to their own wallet for their registered sites.
"""

import time
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

developer_self_issue_bp = Blueprint('developer_self_issue', __name__)


@developer_self_issue_bp.route('/api/developer/issue-self-permission', methods=['POST'])
@cross_origin()
def issue_self_permission():
    """
    Issue a permission credential to the calling developer's wallet.
    
    This allows developers to:
    - Give themselves admin access to their own site
    - Test permissions before deploying
    - Set up initial admin accounts
    
    POST /api/developer/issue-self-permission
    {
        "site_id": "mysite.com",
        "site_domain": "mysite.com",
        "permission_level": "admin",
        "expiry_days": 365
    }
    
    Returns:
        - permission_lemma: The signed credential (store in wallet)
        - credential_id: Unique ID
        - issue_time_us: How long issuance took
    """
    try:
        data = request.get_json()
        site_id = data.get('site_id')
        site_domain = data.get('site_domain') or site_id
        permission_level = data.get('permission_level', 'admin')
        expiry_days = data.get('expiry_days', 365)
        
        if not site_id:
            return jsonify({
                'success': False,
                'error': 'site_id is required'
            }), 400
        
        logger.info(f"🎫 Developer self-issue: {permission_level} for {site_domain}")
        
        # Get or create site manager
        from api.real_iam_manager import get_or_create_site_manager
        
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Ensure permission type exists
        if permission_level not in manager.permissions:
            manager.add_permission({
                'permission_id': permission_level,
                'display_name': permission_level.replace('_', ' ').title(),
                'scope': ['read', 'write', 'admin'] if permission_level in ['admin', 'super_admin'] else ['read', 'write'] if permission_level == 'editor' else ['read'],
                'conditions': [],
                'priority': 100
            })
        
        # Generate a developer DID
        # In production, this would be derived from the developer's passkey/wallet
        developer_did = f"did:lemma:developer_{site_id}_{int(time.time())}"
        
        # If we have session info, use it for better DID
        if session.get('customer_id'):
            from api.ppid import derive_ppid_did
            # Use session customer_id for consistent DID
            developer_did = derive_ppid_did(session['customer_id'], site_domain)
        
        # Issue the permission lemma
        start_time = time.perf_counter()
        
        permission_lemma = manager.issue_permission_lemma(
            developer_did,
            permission_level,
            expiry_days=expiry_days,
            custom_claims={
                'site_domain': site_domain,
                'accountType': permission_level,
                'permissionId': f'{permission_level}_access',
                'issuedBy': 'developer_self_issue',
                'issuedAt': datetime.utcnow().isoformat() + 'Z'
            }
        )
        
        # Add W3C type fields for proper wallet filtering
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'
        
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
            permission_lemma['credentialSubject']['siteId'] = site_id
            permission_lemma['credentialSubject']['siteDomain'] = site_domain
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'
            permission_lemma['claims']['siteId'] = site_id
            permission_lemma['claims']['siteDomain'] = site_domain
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Track in database
        try:
            from api.database import get_db_connection
            
            conn = get_db_connection(site_id=site_id)
            cursor = conn.cursor()
            
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
                'developer@self-issued',  # Placeholder for self-issued
                developer_did,
                datetime.utcnow(),
                'developer_self_issue',
                expires_at,
                json.dumps({
                    'credential_id': permission_lemma.get('id', ''),
                    'issue_time_us': issue_time_us,
                    'issued_via': 'developer_platform_direct'
                })
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"✅ Tracked self-issued permission in database")
            
        except Exception as db_err:
            logger.warning(f"⚠️ Database tracking failed (credential still issued): {db_err}")
        
        logger.info(f"✅ Developer self-issued: {permission_level} for {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        
        return jsonify({
            'success': True,
            'permission_lemma': permission_lemma,
            'credential_id': permission_lemma.get('id', 'generated'),
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'expiry_days': expiry_days,
            'issue_time_us': issue_time_us,
            'message': f'Permission credential issued. Store in your wallet to activate.'
        })
        
    except Exception as e:
        logger.error(f"❌ Developer self-issue failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
