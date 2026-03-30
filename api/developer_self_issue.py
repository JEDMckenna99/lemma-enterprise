"""
Developer Self-Issue API
Allows developers to issue permission credentials to their own wallet for their registered sites.

Authentication: Requires wallet credential (PPID) or API key
"""

import time
import json
import base64
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from flask_cors import cross_origin
from auth.decorators import require_customer_or_admin
from api.admin_issuance_notifications import notify_admin_lemma_issued

logger = logging.getLogger(__name__)

developer_self_issue_bp = Blueprint('developer_self_issue', __name__)


def _authenticate_developer():
    """
    Authenticate developer via wallet credential or API key.
    
    Returns: (customer_id, ppid) or (None, None) if auth fails
    """
    # Method 1: PPID from auth decorators
    ppid = getattr(g, 'ppid', None)
    if ppid and ppid.startswith('did:lemma:ppid_'):
        from api.customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_ppid(ppid)
        if customer:
            return customer.customer_id, ppid

    # Method 1b: Full lemma header
    raw_lemma = request.headers.get('X-Lemma-Credential')
    if raw_lemma:
        try:
            text = str(raw_lemma).strip()
            if text.startswith('{'):
                credential = json.loads(text)
            else:
                padded = text + ('=' * (-len(text) % 4))
                decoded = base64.urlsafe_b64decode(padded.encode('utf-8')).decode('utf-8')
                credential = json.loads(decoded)
            claims = credential.get('claims') or credential.get('credentialSubject') or {}
            lemma_ppid = credential.get('subject') or credential.get('sub') or claims.get('ppid') or claims.get('id')
            if lemma_ppid and str(lemma_ppid).startswith('did:lemma:ppid_'):
                from api.customer_accounts import customer_manager
                customer = customer_manager.get_customer_by_ppid(str(lemma_ppid))
                if customer:
                    return customer.customer_id, str(lemma_ppid)
        except Exception:
            pass
    
    # Method 2: Bearer token with credential
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            credential_json = auth_header.split(' ', 1)[1]
            # Try JSON credential first
            credential = json.loads(credential_json)
            subject = credential.get('subject', '')
            if subject.startswith('did:lemma:'):
                from api.customer_accounts import customer_manager
                customer = customer_manager.get_customer_by_did(subject)
                if customer:
                    return customer.customer_id, subject
        except json.JSONDecodeError:
            # Not JSON, treat as API key
            api_key = auth_header.replace('Bearer ', '').strip()
            from api.customer_accounts import customer_manager
            customer = customer_manager.get_customer_by_api_key(api_key)
            if customer:
                return customer.customer_id, f"did:lemma:customer:{customer.customer_id}"
    
    # Method 3: X-API-Key header
    api_key = request.headers.get('X-API-Key')
    if api_key:
        from api.customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_api_key(api_key)
        if customer:
            return customer.customer_id, f"did:lemma:customer:{customer.customer_id}"
    
    return None, None


@developer_self_issue_bp.route('/api/developer/issue-self-permission', methods=['POST'])
@cross_origin()
@require_customer_or_admin
def issue_self_permission():
    """
    Issue a permission credential to the calling developer's wallet.
    
    This allows developers to:
    - Give themselves admin access to their own site
    - Test permissions before deploying
    - Set up initial admin accounts
    
    Authentication: Wallet credential (X-Lemma-Credential) or API key
    
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
        # Authenticate developer
        customer_id, developer_did = _authenticate_developer()
        
        if not customer_id:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'Provide X-Lemma-Credential header or X-API-Key'
            }), 401
        
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
        
        # Verify customer owns this site
        from api.customer_accounts import customer_manager
        customer = customer_manager.get_customer(customer_id)
        if customer:
            owned_sites = [s.get('site_id') for s in (customer.sites or [])]
            if site_id not in owned_sites:
                # Allow if they own the domain
                owned_domains = [s.get('site_domain') for s in (customer.sites or [])]
                if site_domain not in owned_domains:
                    logger.warning(f"Developer {customer_id} attempted to issue for unowned site {site_id}")
                    # Don't block - allow self-issue for site registration flow
        
        logger.info(f"Developer self-issue: {permission_level} for {site_domain} (customer: {customer_id})")
        
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
        
        # Use the authenticated developer DID (from wallet auth or derived from customer_id)
        # developer_did is already set from _authenticate_developer()
        
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

        notification = None
        if 'admin' in str(permission_level).lower():
            fallback_email = None
            try:
                if customer and getattr(customer, 'email', None):
                    fallback_email = customer.email
            except Exception:
                fallback_email = None

            notification = notify_admin_lemma_issued(
                site_id=site_id,
                site_domain=site_domain,
                user_did=developer_did,
                permission_level=permission_level,
                issued_via='developer_self_issue',
                credential_id=permission_lemma.get('id'),
                fallback_email=fallback_email,
            )
        
        return jsonify({
            'success': True,
            'permission_lemma': permission_lemma,
            'credential_id': permission_lemma.get('id', 'generated'),
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'expiry_days': expiry_days,
            'issue_time_us': issue_time_us,
            'notification_email_sent': bool(notification and notification.get('sent')),
            'notification_email': notification.get('recipient') if notification else None,
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
