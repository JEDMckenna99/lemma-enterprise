"""
Developer Self-Issue API
Allows developers to issue permission credentials to their own wallet for their registered sites.

Authentication: Requires wallet credential (PPID) or API key
"""

import time
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from flask_cors import cross_origin
from auth.decorators import require_customer_or_admin
from api.admin_issuance_notifications import notify_admin_lemma_issued

logger = logging.getLogger(__name__)

developer_self_issue_bp = Blueprint('developer_self_issue', __name__)


def _site_has_existing_owner(site_id: str, site_domain: str, caller_ppid: str) -> bool:
    """True when the site is already claimed by an account other than the caller.

    Self-issue is a bootstrap/registration path: it may claim a site that has no
    existing owner, but must NEVER mint credentials for a site already owned by a
    different account. A site counts as claimed when it has an active SiteAdmin
    (or its domain is registered under a different site_id with active admins),
    and none of those admins belong to the caller. Unregistered sites return
    False so first-time registration still works. Fails closed on error.
    """
    try:
        from api.database import SessionLocal, SiteAdmin, Site

        db = SessionLocal()
        try:
            admins = db.query(SiteAdmin).filter(
                SiteAdmin.site_id == site_id,
                SiteAdmin.is_active == True,  # noqa: E712
            ).all()
            if admins:
                return not any(a.admin_did == caller_ppid for a in admins)

            # No admins on this exact site_id. Guard against domain takeover where
            # the domain is already registered under a different site_id.
            if site_domain:
                dom_site = db.query(Site).filter(Site.site_domain == site_domain).first()
                if dom_site and dom_site.site_id and dom_site.site_id != site_id:
                    other_admins = db.query(SiteAdmin).filter(
                        SiteAdmin.site_id == dom_site.site_id,
                        SiteAdmin.is_active == True,  # noqa: E712
                    ).all()
                    if other_admins and not any(a.admin_did == caller_ppid for a in other_admins):
                        return True
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"site ownership pre-check failed (failing closed): {exc}")
        return True


def _authenticate_developer():
    """Resolve developer identity only from verified request principal (g.*).

    ``@require_customer_or_admin`` already verified the credential. Do not
    re-parse unsigned Authorization / X-Lemma-Credential bodies here — that
    previously allowed a format-only credential to select a different customer.
    """
    ppid = getattr(g, 'ppid', None)
    if not ppid or not str(ppid).startswith('did:lemma:ppid_'):
        return None, None

    from api.customer_accounts import customer_manager

    customer = customer_manager.get_customer_by_ppid(str(ppid))
    if customer:
        return customer.customer_id, str(ppid)
    return None, None


def _require_domain_proof_for_bootstrap(data: dict, site_domain: str) -> tuple[bool, str]:
    """First-time site claim must prove control of the hostname."""
    token = str(
        data.get('domain_verification_token')
        or data.get('verification_token')
        or ''
    ).strip()
    method = str(
        data.get('domain_verification_method')
        or data.get('verification_method')
        or 'dns'
    ).strip() or 'dns'
    if not token:
        return False, 'domain_verification_required'
    from api.domain_ownership import consume_verified_domain_proof

    if not consume_verified_domain_proof(site_domain, token, method):
        return False, 'domain_verification_failed'
    return True, 'ok'


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
        
        # SECURITY: Enforce site ownership. Self-issue may bootstrap a site that
        # has no existing owner (first-time registration), but must never mint a
        # credential (especially admin) for a site already owned by another
        # account. See _site_has_existing_owner (fails closed).
        from api.customer_accounts import customer_manager
        from api.site_access import verify_site_ownership

        customer = customer_manager.get_customer(customer_id)
        owned_sites = [s.get('site_id') for s in (customer.sites or [])] if customer else []
        owned_domains = [s.get('site_domain') for s in (customer.sites or [])] if customer else []
        caller_owns_site = (
            site_id in owned_sites
            or site_domain in owned_domains
            or verify_site_ownership(site_id, developer_did)
        )

        if not caller_owns_site and _site_has_existing_owner(site_id, site_domain, developer_did):
            logger.warning(
                f"SECURITY: developer {customer_id} attempted self-issue of "
                f"'{permission_level}' for site {site_id} ({site_domain}) owned by another account"
            )
            return jsonify({
                'success': False,
                'error': 'You do not have access to this site',
                'code': 'UNAUTHORIZED_SITE_ACCESS',
            }), 403

        if not caller_owns_site:
            ok_proof, proof_err = _require_domain_proof_for_bootstrap(data, site_domain)
            if not ok_proof:
                return jsonify({
                    'success': False,
                    'error': proof_err,
                    'code': proof_err.upper(),
                    'message': (
                        'First-time site bootstrap requires a verified domain proof. '
                        'Start verification via /api/customer/domain-verification/start.'
                    ),
                }), 403

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
