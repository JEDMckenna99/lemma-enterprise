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
import hashlib
import secrets
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from auth.decorators import require_api_key, extract_authenticated_ppid_from_request

from api.real_iam_manager import get_site_manager, get_or_create_site_manager
from api.email_service import send_email

logger = logging.getLogger(__name__)

admin_self_issue_bp = Blueprint('admin_self_issue', __name__)


def _lookup_api_key_binding(api_key: str, requested_site_id: str | None = None) -> dict | None:
    """
    Resolve API key binding from normalized PostgreSQL tables first.

    Returns:
        {
            "site_id": str,
            "site_domain": str | None,
            "customer_id": str | None,
            "authority_emails": set[str]
        }
        or None if no binding found.
    """
    if not api_key:
        return None

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    requested = str(requested_site_id or "").strip().lower()

    try:
        from api.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Path A (canonical): customer api_keys table.
            cursor.execute(
                """
                SELECT ak.customer_id, ak.site_id, s.site_domain, c.email, c.billing_email, s.admin_email
                FROM api_keys ak
                LEFT JOIN sites s ON s.site_id = ak.site_id
                LEFT JOIN customers c ON c.customer_id = ak.customer_id
                WHERE ak.key_hash = %s
                  AND ak.status = 'active'
                LIMIT 1
                """,
                (key_hash,)
            )
            row = cursor.fetchone()

            # Path B: site_api_keys table (site-managed keys).
            if not row:
                cursor.execute(
                    """
                    SELECT s.customer_id, sak.site_id, s.site_domain, c.email, c.billing_email, s.admin_email
                    FROM site_api_keys sak
                    JOIN sites s ON s.site_id = sak.site_id
                    LEFT JOIN customers c ON c.customer_id = s.customer_id
                    WHERE sak.key_hash = %s
                      AND sak.is_active = TRUE
                    LIMIT 1
                    """,
                    (key_hash,)
                )
                row = cursor.fetchone()

            # Path C (legacy): sites.api_key may contain raw key or hash.
            if not row:
                cursor.execute(
                    """
                    SELECT s.customer_id, s.site_id, s.site_domain, c.email, c.billing_email, s.admin_email
                    FROM sites s
                    LEFT JOIN customers c ON c.customer_id = s.customer_id
                    WHERE s.api_key = %s OR s.api_key = %s
                    LIMIT 1
                    """,
                    (api_key, key_hash)
                )
                row = cursor.fetchone()

            if not row:
                return None

            customer_id, bound_site_id, site_domain, customer_email, billing_email, site_admin_email = row
            bound_site_norm = str(bound_site_id or "").strip().lower()
            bound_domain_norm = str(site_domain or "").strip().lower()

            if requested and requested not in {bound_site_norm, bound_domain_norm}:
                return None

            authority_emails = set()
            for val in (customer_email, billing_email, site_admin_email):
                norm = str(val or "").strip().lower()
                if norm:
                    authority_emails.add(norm)

            # Add active site-admin emails as authority sources.
            cursor.execute(
                """
                SELECT admin_email
                FROM site_admins
                WHERE site_id = %s AND is_active = TRUE
                """,
                (bound_site_id,)
            )
            for admin_row in cursor.fetchall() or []:
                admin_email = str((admin_row[0] if admin_row else "") or "").strip().lower()
                if admin_email:
                    authority_emails.add(admin_email)

            return {
                "site_id": bound_site_id,
                "site_domain": site_domain,
                "customer_id": customer_id,
                "authority_emails": authority_emails,
            }
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Normalized API key binding lookup failed: {e}")

    return None


def resolve_site_from_api_key(api_key: str):
    """
    Resolve a default site for an API key when site_id/site_domain are omitted.

    Returns:
        (site_id, site_domain) tuple when resolvable, else (None, None).
    """
    if not api_key:
        return None, None

    # Platform recovery path: allow canonical platform site resolution even when
    # customer/site bindings are absent from normalized tables.
    platform_key = os.getenv('LEMMA_API_KEY', os.getenv('LEMMA_PLATFORM_API_KEY'))
    if platform_key and secrets.compare_digest(api_key, platform_key):
        return 'lemma.id', 'lemma.id'

    # Prefer normalized table resolution first.
    normalized = _lookup_api_key_binding(api_key)
    if normalized and normalized.get("site_id"):
        return normalized.get("site_id"), (normalized.get("site_domain") or normalized.get("site_id"))

    # Legacy fallback: direct api_keys table with plaintext key (older schema variants).
    try:
        from api.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT site_id, site_domain
            FROM api_keys
            WHERE api_key = %s AND active = TRUE
            LIMIT 1
            """,
            (api_key,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and row[0]:
            return row[0], (row[1] or row[0])
    except Exception as e:
        logger.warning(f"Could not resolve site via api_keys table: {e}")

    # Fallback: customer profile sites from customer manager.
    try:
        from api.customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_api_key(api_key)
        if customer and getattr(customer, "sites", None):
            first_site = customer.sites[0]
            site_id = first_site.get("site_id") or first_site.get("site_domain")
            site_domain = first_site.get("site_domain") or site_id
            if site_id:
                return site_id, site_domain
    except Exception as e:
        logger.warning(f"Could not resolve site via customer profile: {e}")

    return None, None


def resolve_expected_admin_email(api_key: str, site_id: str) -> str | None:
    """
    Resolve the expected admin email for self-issue validation.

    Priority:
    1) Customer email owning the API key
    2) Site.admin_email for the requested site
    """
    try:
        from api.customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_api_key(api_key)
        if customer and getattr(customer, "email", None):
            return str(customer.email).strip().lower()
    except Exception as e:
        logger.warning(f"Could not resolve expected email from customer manager: {e}")

    try:
        from api.database import SessionLocal, Site
        db = SessionLocal()
        try:
            site = db.query(Site).filter(Site.site_id == site_id).first()
            if site and getattr(site, "admin_email", None):
                return str(site.admin_email).strip().lower()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not resolve expected email from site record: {e}")

    return None


def validate_customer_binding_for_self_issue(api_key: str, site_id: str, submitted_email: str):
    """
    Strict binding check for admin self-issue.

    Enforces all three conditions against customer DB:
    1) API key belongs to a customer record
    2) Requested site_id belongs to that same customer's registered sites
    3) Submitted admin email matches that same customer email
    """
    normalized_email = str(submitted_email or '').strip().lower()
    site_id_norm = str(site_id or '').strip().lower()

    # Platform recovery path: configured platform API key may bootstrap/recover
    # lemma.id without requiring customer-site binding rows.
    platform_key = os.getenv('LEMMA_API_KEY', os.getenv('LEMMA_PLATFORM_API_KEY'))
    if (
        platform_key
        and secrets.compare_digest(api_key, platform_key)
        and site_id_norm in {'lemma.id', 'lemma_platform'}
    ):
        # If an admin email env exists, require exact match; otherwise accept submitted.
        configured_admin = str(
            os.getenv('LEMMA_ADMIN_EMAIL', os.getenv('PLATFORM_ADMIN_EMAIL', '')) or ''
        ).strip().lower()
        if configured_admin and normalized_email != configured_admin:
            return (
                False,
                'email_mismatch',
                'Submitted email does not match platform admin email on record.',
                None
            )
        return True, None, None, (configured_admin or normalized_email)

    # First, use normalized DB tables (authoritative in production).
    binding = _lookup_api_key_binding(api_key=api_key, requested_site_id=site_id_norm)
    if binding:
        candidates = {e for e in (binding.get("authority_emails") or set()) if e}
        if not candidates:
            return (
                False,
                'customer_email_missing',
                'No authority email is configured for this customer/site in the customer database.',
                None
            )
        if normalized_email not in candidates:
            return (
                False,
                'email_mismatch',
                'Submitted email does not match the customer/site email on record.',
                None
            )
        return True, None, None, normalized_email

    # Fallback to legacy customer manager cache/json path.
    try:
        from api.customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_api_key(api_key)
    except Exception as e:
        logger.warning(f"Customer DB lookup failed for API key binding check: {e}")
        return False, 'customer_lookup_failed', 'Could not validate customer record for API key.', None

    if not customer:
        return False, 'customer_not_found', 'API key is not bound to a customer record.', None

    owned_sites = [str(s.get('site_id') or '').strip().lower() for s in (customer.sites or []) if isinstance(s, dict)]
    owned_domains = [str(s.get('site_domain') or '').strip().lower() for s in (customer.sites or []) if isinstance(s, dict)]

    if site_id_norm not in owned_sites and site_id_norm not in owned_domains:
        return False, 'site_mismatch', 'Requested site is not registered under this customer account.', None

    # Email authority sources in customer DB for this API-key owner.
    # Keep strictness: submitted email must match at least one DB-backed authority email.
    candidate_emails = set()
    primary_email = str(getattr(customer, 'email', '') or '').strip().lower()
    if primary_email:
        candidate_emails.add(primary_email)
    billing_email = str(getattr(customer, 'billing_email', '') or '').strip().lower()
    if billing_email:
        candidate_emails.add(billing_email)

    for site in (customer.sites or []):
        if not isinstance(site, dict):
            continue
        sid = str(site.get('site_id') or '').strip().lower()
        sdomain = str(site.get('site_domain') or '').strip().lower()
        if site_id_norm in {sid, sdomain}:
            site_admin_email = str(site.get('admin_email') or '').strip().lower()
            if site_admin_email:
                candidate_emails.add(site_admin_email)
            site_contact_email = str(site.get('email') or '').strip().lower()
            if site_contact_email:
                candidate_emails.add(site_contact_email)

    if not candidate_emails:
        return (
            False,
            'customer_email_missing',
            'No authority email is configured for this customer/site in the customer database.',
            None
        )

    if normalized_email not in candidate_emails:
        return (
            False,
            'email_mismatch',
            'Submitted email does not match the customer/site email on record.',
            None
        )

    return True, None, None, normalized_email


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

    # Canonical production path: normalized key binding tables.
    normalized = _lookup_api_key_binding(api_key=api_key, requested_site_id=site_id)
    if normalized:
        logger.info(f"Valid normalized API key binding for site {site_id}")
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
        
        # For platform-level sites, allow if customer is a platform admin account
        if site_id in ('lemma.id', 'lemma_platform'):
            from api.platform_account import is_admin_account_type, resolve_account_type_for_customer

            if is_admin_account_type(resolve_account_type_for_customer(customer)):
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
        X-Lemma-Credential: <base64url(full permission lemma)> (optional - wallet-derived PPID source)
    Body:
    {
        "site_id": "lemma_platform",  // optional if API key maps to exactly one site
        "site_domain": "lemma.id",    // optional
        "user_email": "admin@example.com",
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
        required = ['user_email', 'permission_level']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400

        site_id = data.get('site_id')
        site_domain = data.get('site_domain')
        if not site_id:
            resolved_site_id, resolved_site_domain = resolve_site_from_api_key(api_key)
            if not resolved_site_id:
                return jsonify({
                    'error': 'site_resolution_failed',
                    'message': 'site_id is required when API key cannot be resolved to a site'
                }), 400
            site_id = resolved_site_id
            site_domain = site_domain or resolved_site_domain
        site_domain = site_domain or f'{site_id}.com'
        user_email = data['user_email']
        permission_level = data['permission_level']
        normalized_user_email = str(user_email).strip().lower()
        
        # Strict customer DB match: api_key + site_id + user_email must all belong together.
        bound_ok, bound_error, bound_message, bound_authority_email = validate_customer_binding_for_self_issue(
            api_key=api_key,
            site_id=site_id,
            submitted_email=normalized_user_email
        )
        if not bound_ok:
            return jsonify({
                'error': bound_error,
                'message': bound_message
            }), 403

        # Validate API key for this site
        if not validate_api_key(api_key, site_id):
            logger.warning(f"Invalid API key attempt for site {site_id}")
            return jsonify({
                'error': 'unauthorized',
                'message': 'Invalid API key for this site'
            }), 401

        expected_email = bound_authority_email or resolve_expected_admin_email(api_key, site_id) or normalized_user_email
        
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
        
        # Get user DID from wallet-derived PPID only (legacy email-derived DID disabled)
        # Priority: 1) Header 2) Body
        user_did = extract_authenticated_ppid_from_request()
        
        if not user_did or not user_did.startswith('did:lemma:ppid_'):
            user_did = data.get('user_ppid')
        
        if not user_did or not user_did.startswith('did:lemma:ppid_'):
            return jsonify({
                'error': 'invalid_ppid',
                'message': 'Valid wallet PPID is required (did:lemma:ppid_...). Email-derived DID is disabled.'
            }), 400

        from api.platform_owner import enforce_platform_admin_ppid, is_platform_site

        site_id_norm = str(site_id or '').strip().lower()
        if is_platform_site(site_id_norm) and 'admin' in str(permission_level or '').lower():
            denied = enforce_platform_admin_ppid(user_did, site_id_norm)
            if denied:
                return jsonify(denied[0]), denied[1]

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
                # Canonical compatibility permission ID for broad client checks.
                'permissionId': 'admin_access',
                # Preserve selected level separately.
                'permission_level': permission_level,
                'permissionAliases': ['admin_access', permission_level],
                'isAdmin': True,
                'networkShared': False,
            }
        )
        
        # CRITICAL: Add W3C type field for credential classification
        # Rust issuer doesn't include this, so we add it in Python
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'  # For wallet filtering
        
        # IMPORTANT: Do not mutate claims/credentialSubject after signing.
        # Any post-signature claim edits invalidate Ed25519 verification.
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        logger.info(f"✅ Self-issued {permission_level} PERMISSION credential for {user_email} on {site_domain}")
        logger.info(f"⚡ Issue time: {issue_time_us:.2f}µs")
        logger.info(f"🔐 Credential ID: {permission_lemma['id']}")
        logger.info(f"🔐 Type: {permission_lemma['type']}")
        logger.info(f"🔐 Package Type: {permission_lemma.get('packageType', 'MISSING!')}")
        logger.info(f"🔐 User DID: {user_did}")
        logger.info(f"🔐 Issuer DID: {manager.issuer_did[:50]}...")

        # Notification to customer/site email of admin credential issuance.
        try:
            notify_to = expected_email or normalized_user_email
            subject = f"Admin credential issued for {site_id}"
            html = (
                "<p>An admin credential was issued.</p>"
                f"<p><strong>Site ID:</strong> {site_id}<br>"
                f"<strong>Site domain:</strong> {site_domain}<br>"
                f"<strong>Permission:</strong> {permission_level}<br>"
                f"<strong>User PPID:</strong> {user_did}</p>"
                "<p>If this was not expected, rotate your API key and review admin access immediately.</p>"
            )
            send_result = send_email(to=notify_to, subject=subject, html=html)
            logger.info(f"Admin self-issue notification email status: {send_result.get('success')} provider={send_result.get('provider')}")
        except Exception as email_err:
            logger.warning(f"Failed to send admin self-issue notification email: {email_err}")
        
        return jsonify({
            'success': True,
            'credential': permission_lemma,
            'user_did': user_did,
            'issuer_did': manager.issuer_did,
            'site_id': site_id,
            'site_domain': site_domain,
            'permission_level': permission_level,
            'issue_time_us': issue_time_us,
            'notification_email': expected_email or normalized_user_email,
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


def _upsert_site_admin_record(site_id: str, user_did: str, user_email: str, *, added_by: str) -> None:
    from api.database import SessionLocal, SiteAdmin

    db = SessionLocal()
    try:
        admin_record = db.query(SiteAdmin).filter(
            SiteAdmin.site_id == site_id,
            SiteAdmin.admin_did == user_did,
        ).first()
        if admin_record:
            admin_record.admin_email = user_email
            admin_record.admin_role = 'owner'
            admin_record.is_active = True
            admin_record.last_activity = datetime.utcnow()
        else:
            db.add(
                SiteAdmin(
                    site_id=site_id,
                    admin_did=user_did,
                    admin_email=user_email,
                    admin_role='owner',
                    permissions=['users', 'permissions', 'billing'],
                    added_by=added_by,
                    is_active=True,
                    last_activity=datetime.utcnow(),
                )
            )
        db.commit()
    finally:
        db.close()


def _issue_admin_credential_core(
    *,
    site_id: str,
    site_domain: str,
    user_did: str,
    user_email: str,
    permission_level: str,
    issued_via: str,
    added_by: str,
) -> dict:
    import time

    site_id_norm = str(site_id or '').strip().lower()
    site_domain = (site_domain or site_id_norm or 'lemma.id').strip().lower()

    manager = get_site_manager(site_id_norm, site_domain)
    if not manager:
        manager = get_or_create_site_manager(site_id_norm, site_domain)
    if not manager:
        raise RuntimeError('Failed to create site manager')

    if permission_level not in manager.permissions:
        manager.add_permission(
            {
                'permission_id': permission_level,
                'display_name': permission_level.replace('_', ' ').title(),
                'scope': get_default_scope(permission_level),
                'conditions': [],
                'priority': 100 if 'admin' in permission_level else 50,
            }
        )

    _upsert_site_admin_record(site_id_norm, user_did, user_email, added_by=added_by)

    start_time = time.perf_counter()
    permission_lemma = manager.issue_permission_lemma(
        user_did,
        permission_level,
        expiry_days=90,
        custom_claims={
            'email': user_email,
            'site_domain': site_domain,
            'issued_via': issued_via,
            'accountType': 'admin',
            'permissionId': 'admin_access',
            'permission_level': permission_level,
            'permissionAliases': ['admin_access', permission_level],
            'isAdmin': True,
            'networkShared': False,
        },
    )
    permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
    permission_lemma['packageType'] = 'permission'

    issue_time_us = (time.perf_counter() - start_time) * 1_000_000
    return {
        'success': True,
        'credential': permission_lemma,
        'user_did': user_did,
        'issuer_did': manager.issuer_did,
        'site_id': site_id_norm,
        'site_domain': site_domain,
        'permission_level': permission_level,
        'issue_time_us': issue_time_us,
        'notification_email': user_email,
        'message': 'Admin credential issued successfully. Store this credential in your browser wallet.',
    }


@admin_self_issue_bp.route('/api/v1/iam/admin/platform-bootstrap/status', methods=['POST'])
@cross_origin()
def platform_bootstrap_status():
    """Evaluate whether the unlocked wallet qualifies for lemma.id owner auto-bootstrap."""
    data = request.get_json(silent=True) or {}
    client_ppid = (data.get('ppid') or '').strip()
    wallet_id = (data.get('wallet_id') or '').strip()

    from api.platform_owner import evaluate_platform_owner_bootstrap, normalize_ppid
    from api.database import SessionLocal, SiteAdmin

    status = evaluate_platform_owner_bootstrap(
        client_ppid=client_ppid or None,
        wallet_id=wallet_id or None,
    )

    has_site_admin = False
    effective_ppid = normalize_ppid(status.get('ppid'))
    if effective_ppid:
        db = SessionLocal()
        try:
            has_site_admin = (
                db.query(SiteAdmin)
                .filter(
                    SiteAdmin.site_id.in_(['lemma.id', 'lemma_platform']),
                    SiteAdmin.admin_did == effective_ppid,
                    SiteAdmin.is_active == True,  # noqa: E712
                )
                .first()
                is not None
            )
        finally:
            db.close()

    status['has_site_admin'] = has_site_admin
    status['should_auto_issue'] = bool(status.get('can_auto_issue') and not has_site_admin)
    return jsonify({'success': True, **status})


@admin_self_issue_bp.route('/api/v1/iam/admin/platform-bootstrap/auto-issue', methods=['POST'])
@cross_origin()
def platform_bootstrap_auto_issue():
    """Issue lemma.id admin proof to the configured platform owner wallet."""
    data = request.get_json(silent=True) or {}
    client_ppid = (data.get('ppid') or '').strip()
    wallet_id = (data.get('wallet_id') or '').strip()

    from api.platform_owner import platform_owner_admin_email, verify_platform_owner_wallet

    user_did, denied = verify_platform_owner_wallet(
        client_ppid=client_ppid or None,
        wallet_id=wallet_id or None,
    )
    if denied:
        return jsonify(denied[0]), denied[1]

    user_email = platform_owner_admin_email()
    try:
        payload = _issue_admin_credential_core(
            site_id='lemma.id',
            site_domain='lemma.id',
            user_did=user_did,
            user_email=user_email,
            permission_level='super_admin',
            issued_via='platform_owner_auto_bootstrap',
            added_by='platform_owner_auto_bootstrap',
        )
        logger.info(
            "Platform owner auto-bootstrap issued admin credential for %s",
            user_did[:24],
        )
        return jsonify(payload)
    except Exception as exc:
        logger.error("Platform owner auto-bootstrap failed: %s", exc)
        return jsonify({'success': False, 'error': 'issue_failed', 'message': str(exc)}), 500


def _canonicalize_admin_permission_lemma(permission_lemma: dict, permission_level: str, site_domain: str, user_email: str) -> dict:
    """
    Normalize admin lemmas to a strict, compatibility-safe claim shape.
    - Canonical admin permission id remains `admin_access` for broad client compatibility.
    - Exact selected level is preserved in `permission_level`.
    - Timestamps are numeric, booleans are real booleans, and site identifiers are normalized.
    """
    claims = dict(permission_lemma.get('claims') or permission_lemma.get('credentialSubject') or {})
    site_key = str(site_domain or claims.get('siteId') or claims.get('site_domain') or '').strip().lower()
    if not site_key:
        site_key = str(permission_lemma.get('site_id') or '').strip().lower()

    def _to_int(value, default_value: int) -> int:
        try:
            return int(float(value))
        except Exception:
            return int(default_value)

    now_epoch = int(datetime.utcnow().timestamp())
    issued_at = _to_int(permission_lemma.get('issuanceDate') or claims.get('issuedAt') or claims.get('issuanceDate'), now_epoch)
    expires_at = _to_int(permission_lemma.get('expirationDate') or claims.get('expiresAt') or claims.get('expirationDate'), issued_at + (90 * 86400))

    raw_scope = claims.get('scope')
    if isinstance(raw_scope, list):
        scope = [str(item).strip() for item in raw_scope if str(item).strip()]
    elif isinstance(raw_scope, str) and raw_scope.strip():
        scope = [part.strip() for part in raw_scope.split(',') if part.strip()]
    else:
        scope = get_default_scope(permission_level)

    canonical_permission_id = 'admin_access'
    permission_aliases = [canonical_permission_id]
    if permission_level and permission_level not in permission_aliases:
        permission_aliases.append(permission_level)

    canonical_claims = {
        **claims,
        'email': user_email,
        'siteId': site_key,
        'siteDomain': site_key,
        'site_domain': site_key,
        'accountType': 'admin',
        'permissionId': canonical_permission_id,
        'permission_level': permission_level,
        'permissionAliases': permission_aliases,
        'isAdmin': True,
        'networkShared': False,
        'issuedAt': issued_at,
        'expiresAt': expires_at,
        'packageType': 'permission',
        'scope': scope,
    }

    permission_lemma['issuanceDate'] = issued_at
    permission_lemma['expirationDate'] = expires_at
    permission_lemma['claims'] = dict(canonical_claims)
    permission_lemma['credentialSubject'] = dict(canonical_claims)
    return permission_lemma

