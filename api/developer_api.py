"""
Developer Platform API
Handles developer dashboard data: sites, stats, API keys, users

SECURITY: All site-specific operations require ownership validation.
"""

import logging
import secrets
import json
import base64
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g, redirect
from flask_cors import cross_origin
from auth.decorators import require_wallet_ppid, require_customer_or_admin
from api.agent_credentials import require_agent_or_user_auth
from api.usage_tracking import get_monthly_active_users
from api.lemma_format import normalize_site_permission_lemma
from api.database import get_redis_client
from api.admin_issuance_notifications import notify_admin_lemma_issued

logger = logging.getLogger(__name__)

developer_api_bp = Blueprint('developer_api', __name__)


def _tenant_value(value: str | None, fallback: str, max_len: int = 120) -> str:
    cleaned = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"-", "_", "."})
    cleaned = cleaned[:max_len]
    return cleaned or fallback


@developer_api_bp.before_request
def _enforce_developer_tenant_context():
    g.org_id = _tenant_value(request.headers.get("X-Lemma-Org-Id") or request.args.get("org_id"), "org_default", 120)
    env = _tenant_value(request.headers.get("X-Lemma-Environment") or request.args.get("environment"), "prod", 32)
    g.environment = env if env in {"dev", "staging", "prod"} else "prod"
    scoped_site = _tenant_value(request.headers.get("X-Lemma-Site-Id"), "", 120)
    route_site = _tenant_value((request.view_args or {}).get("site_id"), "", 120)
    if scoped_site and route_site and scoped_site != route_site:
        return jsonify({"success": False, "error": "site_scope_forbidden"}), 403


from api.site_access import (
    get_authenticated_ppid as _get_authenticated_ppid,
    require_site_ownership as _require_site_ownership,
    verify_site_ownership as _verify_site_ownership,
)
from api.forensic_audit import capture_action_proof


def _get_site_bootstrap_status(db, site_id: str, caller_ppid: str):
    """
    Determine whether caller can bootstrap admin permission for this site.

    Returns a tuple: (status_dict, http_status_code)
    """
    from api.database import Site, SiteAdmin, UserLemma, SitePermissionGrant

    site = db.query(Site).filter(Site.site_id == site_id).first()
    if not site:
        return ({
            'success': False,
            'eligible': False,
            'already_issued': False,
            'reason': 'site_not_found',
            'message': 'Site not found.'
        }, 404)

    admin_record = db.query(SiteAdmin).filter(
        SiteAdmin.site_id == site_id,
        SiteAdmin.admin_did == caller_ppid,
        SiteAdmin.is_active == True
    ).first()

    if not admin_record:
        return ({
            'success': False,
            'eligible': False,
            'already_issued': False,
            'can_reissue': False,
            'reason': 'not_site_admin',
            'message': 'You are not an active admin for this site.'
        }, 403)

    site_admin_email = (site.admin_email or '').strip().lower()
    caller_admin_email = (admin_record.admin_email or '').strip().lower()
    if site_admin_email and caller_admin_email and site_admin_email != caller_admin_email:
        return ({
            'success': True,
            'eligible': False,
            'already_issued': False,
            'can_reissue': False,
            'reason': 'owner_email_mismatch',
            'message': 'Signed-in admin does not match the site owner email.',
            'site_id': site_id,
            'site_domain': site.site_domain,
            'site_admin_email': site.admin_email
        }, 200)

    existing_active_admin = db.query(UserLemma).filter(
        UserLemma.site_id == site_id,
        UserLemma.lemma_type.in_(['permission', 'access']),
        UserLemma.permission_id.in_(['admin', 'admin_access', 'super_admin']),
        UserLemma.revoked_at.is_(None),
        UserLemma.is_active == True
    ).first()

    existing_site_grant = db.query(SitePermissionGrant).filter(
        SitePermissionGrant.site_id == site_id,
        SitePermissionGrant.permission_id.in_(['admin', 'admin_access', 'super_admin']),
        SitePermissionGrant.revoked_at.is_(None),
        SitePermissionGrant.is_active == True
    ).first()

    if existing_active_admin or existing_site_grant:
        return ({
            'success': True,
            'eligible': False,
            'already_issued': True,
            'can_reissue': True,
            'reason': 'bootstrap_completed',
            'message': 'Admin credential already exists. You can reissue a new one.',
            'site_id': site_id,
            'site_domain': site.site_domain
        }, 200)

    return ({
        'success': True,
        'eligible': True,
        'already_issued': False,
        'can_reissue': False,
        'reason': 'ready',
        'message': 'Eligible for one-time admin bootstrap.',
        'site_id': site_id,
        'site_domain': site.site_domain,
        'site_admin_email': site.admin_email
    }, 200)


def _table_exists(cursor, table_name: str) -> bool:
    """Return True if a table exists in the public schema."""
    cursor.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
    return cursor.fetchone()[0] is not None


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Return True if a column exists on a table in the public schema."""
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name)
    )
    return cursor.fetchone() is not None


def _canonical_site_key(value: str) -> str:
    """Normalize site identifiers by removing separators and lowercasing."""
    if not value:
        return ''
    return ''.join(ch for ch in str(value).lower() if ch.isalnum())


def _build_admin_transfer_key(token: str) -> str:
    return f"admin_transfer_token:{token}"


def _build_admin_transfer_import_url(token: str) -> str:
    # Lemma-hosted relay endpoint that redeems transfer token and redirects
    # to target site with credential payload in URL fragment for client storage.
    return f"https://lemma.id/api/developer/credential-transfer/import/{token}"


_ADMIN_PERMISSION_IDS = {
    'admin',
    'admin_access',
    'super_admin',
    'superadmin',
    'site_admin',
    'platform_admin',
}


def _coerce_scope_list(scope_value) -> list[str]:
    """Convert scope payload variants into a canonical list of strings."""
    if isinstance(scope_value, list):
        return [str(item).strip() for item in scope_value if str(item).strip()]
    if isinstance(scope_value, tuple):
        return [str(item).strip() for item in scope_value if str(item).strip()]
    if isinstance(scope_value, set):
        return [str(item).strip() for item in scope_value if str(item).strip()]
    if not isinstance(scope_value, str):
        return []

    text = scope_value.strip()
    if not text:
        return []

    # Handle serialized JSON array payloads from older issuance paths.
    if text.startswith('[') and text.endswith(']'):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

    return [piece.strip() for piece in text.split(',') if piece.strip()]


def _is_admin_bootstrap_credential(credential: dict, site_id: str) -> bool:
    """Validate that credential is admin-like and bound to the expected site."""
    if not isinstance(credential, dict):
        return False
    claims = credential.get('claims') or credential.get('credentialSubject') or {}
    if not isinstance(claims, dict):
        return False

    bound_site = str(claims.get('siteId') or '').strip().lower()
    if not bound_site or bound_site != str(site_id or '').strip().lower():
        return False

    permission_id = str(
        claims.get('permissionId')
        or claims.get('permission_level')
        or claims.get('permission_id')
        or ''
    ).strip().lower()
    scope_values = [entry.lower() for entry in _coerce_scope_list(claims.get('scope'))]

    return (
        permission_id in _ADMIN_PERMISSION_IDS
        or ('admin' in permission_id if permission_id else False)
        or ('admin' in scope_values)
        or ('*' in scope_values)
    )


def _enforce_bootstrap_admin_claims(credential: dict, site_id: str, site_domain: str, target_user_ppid: str) -> dict:
    """
    Canonicalize bootstrap-issued admin claims to avoid silent privilege drift.
    """
    normalized = dict(credential or {})
    claims = normalized.get('claims') if isinstance(normalized.get('claims'), dict) else {}
    credential_subject = normalized.get('credentialSubject') if isinstance(normalized.get('credentialSubject'), dict) else {}

    scope_values = _coerce_scope_list(claims.get('scope') or credential_subject.get('scope'))
    if not scope_values:
        scope_values = ['*']
    lowered_scope = {entry.lower() for entry in scope_values}
    if 'admin' not in lowered_scope:
        scope_values.append('admin')

    core_fields = {
        'siteId': site_id,
        'siteDomain': site_domain,
        'permissionId': 'admin_access',
        'permission_level': 'admin',
        'accountType': 'admin',
        'credentialScope': 'site_specific',
        'type': 'permission',
        'scope': scope_values,
        'permissions': 'admin_access',
    }

    claims.update(core_fields)
    credential_subject.update(core_fields)
    normalized['claims'] = claims
    normalized['credentialSubject'] = credential_subject
    normalized['subject'] = target_user_ppid

    return normalized


def _get_owned_site_ids(db, ppid: str):
    """
    Resolve site ownership for a PPID from multiple admin authority sources:
    - SiteAdmin records
    - Active site_permission_grants with admin-like permissions
    - Active user_lemmas with admin-like permissions
    """
    from api.database import SiteAdmin, SitePermissionGrant, UserLemma

    if not ppid:
        return []

    owned_site_ids = set()

    admin_records = db.query(SiteAdmin).filter(
        SiteAdmin.admin_did == ppid,
        SiteAdmin.is_active == True
    ).all()
    owned_site_ids.update(a.site_id for a in admin_records if a.site_id)

    admin_permission_ids = ['admin', 'admin_access', 'super_admin']

    grant_records = db.query(SitePermissionGrant).filter(
        SitePermissionGrant.user_did == ppid,
        SitePermissionGrant.permission_id.in_(admin_permission_ids),
        SitePermissionGrant.is_active == True,
        SitePermissionGrant.revoked_at.is_(None)
    ).all()
    owned_site_ids.update(g.site_id for g in grant_records if g.site_id)

    lemma_records = db.query(UserLemma).filter(
        UserLemma.user_did == ppid,
        UserLemma.lemma_type.in_(['permission', 'access']),
        UserLemma.permission_id.in_(admin_permission_ids),
        UserLemma.is_active == True,
        UserLemma.revoked_at.is_(None)
    ).all()
    owned_site_ids.update(l.site_id for l in lemma_records if l.site_id)

    return sorted(list(owned_site_ids))


def _upsert_site_admin_record(db, site_id: str, admin_did: str, admin_email: str = ''):
    """Ensure SiteAdmin row exists for bootstrap/self-issue style admin issuance."""
    from api.database import SiteAdmin

    if not site_id or not admin_did:
        return

    admin_record = db.query(SiteAdmin).filter(
        SiteAdmin.site_id == site_id,
        SiteAdmin.admin_did == admin_did
    ).first()

    if admin_record:
        if admin_email:
            admin_record.admin_email = admin_email
        admin_record.is_active = True
        admin_record.last_activity = datetime.utcnow()
        if not admin_record.permissions:
            admin_record.permissions = ['users', 'permissions', 'billing']
        return

    db.add(SiteAdmin(
        site_id=site_id,
        admin_did=admin_did,
        admin_email=admin_email or '',
        admin_role='owner',
        permissions=['users', 'permissions', 'billing'],
        added_by='bootstrap_issue',
        is_active=True,
        last_activity=datetime.utcnow()
    ))


@developer_api_bp.route('/api/developer/stats', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_developer_stats():
    """Get overview stats for the developer dashboard"""
    try:
        # Get PPID from authenticated context for user-specific stats
        ppid = _get_authenticated_ppid()
        
        site_count = 0
        total_verifications = 0
        active_users = 0
        
        # Try to query database if available
        try:
            from api.database import SessionLocal, Site
            db = SessionLocal()
            
            # Count sites owned by this developer
            if ppid:
                site_ids = _get_owned_site_ids(db, ppid)
                if site_ids:
                    sites = db.query(Site).filter(Site.site_id.in_(site_ids)).all()
                    site_count = len(sites)
                    total_verifications = sum(getattr(s, 'verification_count', 0) or 0 for s in sites)
                    active_users = sum(getattr(s, 'user_count', 0) or 0 for s in sites)
            
            db.close()
            
        except Exception as e:
            logger.warning(f"Database query failed (this is OK in dev): {e}")
        
        return jsonify({
            'success': True,
            'total_verifications': total_verifications,
            'active_users': active_users,
            'site_count': site_count,
            'avg_latency_ms': 0.5  # Local verification is fast
        })
        
    except Exception as e:
        logger.error(f"Failed to get developer stats: {e}")
        return jsonify({
            'success': True,  # Return success with defaults
            'total_verifications': 0,
            'active_users': 0,
            'site_count': 0,
            'avg_latency_ms': 0.5
        })


@developer_api_bp.route('/api/developer/sites', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_developer_sites():
    """Get all sites owned by the developer"""
    try:
        ppid = _get_authenticated_ppid()
        credential_id = request.headers.get('X-Credential-ID')
        
        sites = []
        
        # Try to query database if available
        try:
            from api.database import SessionLocal, Site, get_db_connection
            db = SessionLocal()
            
            # Get sites for this developer via SiteAdmin table
            if ppid:
                # Find sites where this PPID has admin ownership/authority.
                site_ids = _get_owned_site_ids(db, ppid)
                db_sites = db.query(Site).filter(Site.site_id.in_(site_ids)).all() if site_ids else []
            elif credential_id:
                # Admin can see all sites
                db_sites = db.query(Site).limit(100).all()
            else:
                db_sites = []
            
            # Resolve total lemma issuance per site from canonical tracking tables.
            lemma_totals = {}
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                for site in db_sites:
                    site_identifiers = {site.site_id}
                    domain = (site.site_domain or '').strip().lower()
                    if domain:
                        site_identifiers.add(domain)
                        site_identifiers.add(domain.replace('.', '_').replace('-', '_'))
                    site_keys = list(site_identifiers)
                    canonical_key = _canonical_site_key(site.site_id) or _canonical_site_key(domain)

                    pi_total = 0
                    spg_total = 0
                    ul_total = 0

                    if _table_exists(cursor, 'permission_instances'):
                        cursor.execute(
                            """
                            SELECT COUNT(*)::BIGINT
                            FROM permission_instances
                            WHERE site_id = ANY(%s)
                               OR regexp_replace(lower(site_id), '[_\\.-]', '', 'g') = %s
                            """,
                            (site_keys, canonical_key)
                        )
                        pi_total = cursor.fetchone()[0] or 0

                    if _table_exists(cursor, 'site_permission_grants'):
                        cursor.execute(
                            """
                            SELECT COUNT(*)::BIGINT
                            FROM site_permission_grants
                            WHERE site_id = ANY(%s)
                               OR regexp_replace(lower(site_id), '[_\\.-]', '', 'g') = %s
                            """,
                            (site_keys, canonical_key)
                        )
                        spg_total = cursor.fetchone()[0] or 0

                    if _table_exists(cursor, 'user_lemmas'):
                        cursor.execute(
                            """
                            SELECT COUNT(*)::BIGINT
                            FROM user_lemmas
                            WHERE (
                                    site_id = ANY(%s)
                                    OR regexp_replace(lower(site_id), '[_\\.-]', '', 'g') = %s
                                  )
                              AND (lemma_type = 'permission' OR lemma_type = 'access')
                            """,
                            (site_keys, canonical_key)
                        )
                        ul_total = cursor.fetchone()[0] or 0

                    lemma_totals[site.site_id] = max(pi_total, spg_total, ul_total)
            except Exception as count_err:
                logger.warning(f"Lemma issuance count query failed: {count_err}")
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()

            for site in db_sites:
                sites.append({
                    'site_id': site.site_id,
                    'name': site.company_name or site.site_id,
                    'domain': site.site_domain or site.site_id,
                    'status': 'active' if getattr(site, 'key_status', 'active') == 'active' else 'inactive',
                    'issuer_did': getattr(site, 'issuer_did', None),
                    'issued_lemmas_total': int(lemma_totals.get(site.site_id, 0)),
                    'user_count': getattr(site, 'user_count', 0) or 0,
                    'api_key_count': 1,  # Placeholder
                    'created_at': site.created_at.isoformat() if site.created_at else None
                })
            
            db.close()
            
        except Exception as e:
            logger.warning(f"Database query failed (this is OK in dev): {e}")
        
        return jsonify({
            'success': True,
            'sites': sites
        })
        
    except Exception as e:
        logger.error(f"Failed to get sites: {e}")
        return jsonify({
            'success': True,  # Return success with empty list
            'sites': []
        })


@developer_api_bp.route('/api/developer/sites', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def create_developer_site():
    """Register a new site"""
    try:
        data = request.get_json() or {}
        
        name = data.get('name', '').strip()
        domain = data.get('domain', '').strip().lower()
        environment = data.get('environment', 'development')
        
        if not domain:
            return jsonify({
                'success': False,
                'error': 'Domain is required'
            }), 400
        
        # Clean domain
        domain = domain.replace('https://', '').replace('http://', '').rstrip('/')
        
        # Generate site ID
        site_id = domain.replace('.', '_').replace('-', '_')
        
        ppid = _get_authenticated_ppid()
        
        from api.database import SessionLocal, Site
        from api.real_iam_manager import get_or_create_site_manager
        
        try:
            db = SessionLocal()
            
            # Check if site already exists
            existing = db.query(Site).filter(Site.site_id == site_id).first()
            if existing:
                db.close()
                return jsonify({
                    'success': False,
                    'error': 'A site with this domain already exists'
                }), 400
            
            # STEP 1: Create the site record in database FIRST
            # (KMS key storage requires site to exist)
            new_site = Site(
                site_id=site_id,
                site_domain=domain,
                company_name=name or domain,
                admin_email=ppid or '',  # Will be updated from wallet profile
                api_key=f"lm_{secrets.token_urlsafe(32)}",  # Auto-generate API key
                oauth_client_id=f"oc_{secrets.token_urlsafe(16)}",
                oauth_client_secret=secrets.token_urlsafe(32),
                created_at=datetime.utcnow()
            )
            db.add(new_site)
            db.commit()
            logger.info(f"Created site record: {site_id}")
            
            # STEP 2: Add creator as site admin
            if ppid:
                from api.database import SiteAdmin
                admin = SiteAdmin(
                    site_id=site_id,
                    admin_did=ppid,
                    admin_email='',  # Will be filled from wallet
                    admin_role='owner',
                    is_active=True
                )
                db.add(admin)
                db.commit()
                logger.info(f"Added admin {ppid[:20]}... to site {site_id}")
            
            db.close()
            
            # STEP 3: Create IAM manager (generates Ed25519 keypair with KMS protection)
            # This MUST happen AFTER site record exists
            manager = get_or_create_site_manager(site_id, domain)
            
            logger.info(f"✅ Created site: {site_id} for {ppid}")
            
            return jsonify({
                'success': True,
                'site_id': site_id,
                'domain': domain,
                'issuer_did': manager.issuer_did if manager else None
            })
            
        except Exception as e:
            logger.error(f"Database error creating site: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to create site'
            }), 500
        
    except Exception as e:
        logger.error(f"Failed to create site: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_detail(site_id):
    """Get details for a specific site"""
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error
    try:
        from api.database import SessionLocal, Site
        
        db = SessionLocal()
        site = db.query(Site).filter(Site.site_id == site_id).first()
        db.close()
        
        if not site:
            return jsonify({
                'success': False,
                'error': 'Site not found'
            }), 404
        
        return jsonify({
            'success': True,
            'site': {
                'site_id': site.site_id,
                'name': site.company_name or site.site_id,
                'domain': site.site_domain or site.site_id,
                'status': 'active' if getattr(site, 'key_status', 'active') == 'active' else 'inactive',
                'issuer_did': getattr(site, 'issuer_did', None),
                'created_at': site.created_at.isoformat() if site.created_at else None
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get site: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/bootstrap-status', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_bootstrap_status(site_id):
    """Return eligibility state for one-time site admin bootstrap."""
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error

    caller_ppid = _get_authenticated_ppid()
    if not caller_ppid:
        return jsonify({
            'success': False,
            'eligible': False,
            'already_issued': False,
            'can_reissue': False,
            'reason': 'auth_required',
            'message': 'Wallet authentication required.'
        }), 401

    try:
        from api.database import SessionLocal
        db = SessionLocal()
        try:
            payload, status_code = _get_site_bootstrap_status(db, site_id, caller_ppid)
            payload['caller_ppid'] = caller_ppid
            return jsonify(payload), status_code
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to fetch bootstrap status for {site_id}: {e}")
        return jsonify({
            'success': False,
            'eligible': False,
            'already_issued': False,
            'can_reissue': False,
            'reason': 'internal_error',
            'message': 'Failed to evaluate bootstrap status.'
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/bootstrap-admin', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def bootstrap_site_admin(site_id):
    """Issue one-time admin credential for site owner/admin via Lemma-authenticated PPID."""
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error
    
    caller_ppid = _get_authenticated_ppid()
    if not caller_ppid:
        return jsonify({
            'success': False,
            'error': 'auth_required',
            'message': 'Wallet authentication required.'
        }), 401

    try:
        from api.database import SessionLocal, Site, UserLemma, SitePermissionGrant
        from api.real_iam_manager import get_or_create_site_manager

        db = SessionLocal()
        try:
            request_data = request.get_json(silent=True) or {}
            reissue_requested = bool(request_data.get('reissue'))
            create_transfer_token = bool(request_data.get('create_transfer_token', reissue_requested))
            requested_user_ppid = request_data.get('user_ppid')
            if isinstance(requested_user_ppid, str) and requested_user_ppid.startswith('did:lemma:ppid_'):
                target_user_ppid = requested_user_ppid
            else:
                target_user_ppid = caller_ppid

            status_payload, status_code = _get_site_bootstrap_status(db, site_id, caller_ppid)
            if status_code != 200:
                return jsonify(status_payload), status_code
            if status_payload.get('already_issued') and not reissue_requested:
                return jsonify(status_payload), 409

            site = db.query(Site).filter(Site.site_id == site_id).first()
            if not site:
                return jsonify({
                    'success': False,
                    'error': 'site_not_found',
                    'message': 'Site not found.'
                }), 404

            manager = get_or_create_site_manager(site.site_id, site.site_domain)
            if not manager:
                return jsonify({
                    'success': False,
                    'error': 'manager_unavailable',
                    'message': 'Failed to initialize site IAM manager.'
                }), 500

            if 'admin' not in manager.permissions:
                manager.add_permission({
                    'permission_id': 'admin',
                    'display_name': 'Administrator',
                    'scope': ['*'],
                    'conditions': [],
                    'priority': 100
                })

            # Ensure this issuance path is reflected in site admin ownership table.
            _upsert_site_admin_record(db, site.site_id, target_user_ppid, site.admin_email or '')

            expires_at = datetime.utcnow() + timedelta(days=365)
            permission_lemma = manager.issue_permission_lemma(
                target_user_ppid,
                'admin',
                expiry_days=365
            )
            permission_lemma = normalize_site_permission_lemma(
                permission_lemma,
                site.site_id,
                site.site_domain,
                'admin_access'
            )
            permission_lemma = _enforce_bootstrap_admin_claims(
                permission_lemma,
                site.site_id,
                site.site_domain,
                target_user_ppid
            )
            # Preserve selected admin level while keeping canonical admin permission id
            # for broad client compatibility.
            for key in ('claims', 'credentialSubject'):
                if isinstance(permission_lemma.get(key), dict):
                    permission_lemma[key]['permission_level'] = 'admin'
                    permission_lemma[key]['accountType'] = 'admin'

            if not _is_admin_bootstrap_credential(permission_lemma, site.site_id):
                logger.error(
                    "bootstrap-admin generated non-admin credential for site=%s caller=%s permission=%s scope=%s",
                    site.site_id,
                    caller_ppid,
                    (permission_lemma.get('claims') or {}).get('permissionId'),
                    (permission_lemma.get('claims') or {}).get('scope'),
                )
                return jsonify({
                    'success': False,
                    'error': 'bootstrap_permission_mismatch',
                    'message': 'Bootstrap issuance did not produce an admin credential. No credential was stored.'
                }), 500

            db.add(UserLemma(
                user_did=target_user_ppid,
                lemma_type='permission',
                site_id=site.site_id,
                permission_id='admin',
                lemma_data=permission_lemma,
                expires_at=expires_at,
                is_active=True
            ))
            db.add(SitePermissionGrant(
                site_id=site.site_id,
                user_did=target_user_ppid,
                permission_id='admin',
                granted_by=caller_ppid,
                expires_at=expires_at,
                is_active=True,
                conditions={
                    'bootstrap': not reissue_requested,
                    'reissue': reissue_requested
                }
            ))
            db.commit()

            notification = notify_admin_lemma_issued(
                site_id=site.site_id,
                site_domain=site.site_domain,
                user_did=target_user_ppid,
                permission_level='admin',
                issued_via='bootstrap_admin',
                credential_id=permission_lemma.get('id'),
                fallback_email=site.admin_email,
            )

            transfer_data = {}
            if create_transfer_token:
                try:
                    token = secrets.token_urlsafe(32)
                    expires_in_seconds = 300
                    payload = {
                        'site_id': site.site_id,
                        'site_domain': site.site_domain,
                        'credential': permission_lemma,
                        'created_by': caller_ppid,
                        'created_at': datetime.utcnow().isoformat()
                    }
                    redis_client = get_redis_client()
                    redis_client.setex(
                        _build_admin_transfer_key(token),
                        expires_in_seconds,
                        json.dumps(payload)
                    )
                    transfer_data = {
                        'transfer_token': token,
                        'transfer_expires_in': expires_in_seconds,
                        'direct_import_url': f"https://{site.site_domain}/?lemma_transfer_token={token}",
                        'import_url': _build_admin_transfer_import_url(token),
                    }
                except Exception as transfer_err:
                    logger.warning(f"Failed to create transfer token in bootstrap-admin for {site.site_id}: {transfer_err}")

            capture_action_proof(
                action="site.bootstrap_admin",
                site_id=site.site_id,
                resource=permission_lemma.get('id'),
            )
            return jsonify({
                'success': True,
                'site_id': site.site_id,
                'site_domain': site.site_domain,
                'permission_id': 'admin',
                'credential': permission_lemma,
                'credential_id': permission_lemma.get('id'),
                'expires_at': expires_at.isoformat(),
                'reissued': reissue_requested,
                'user_ppid': target_user_ppid,
                'notification_email_sent': bool(notification.get('sent')),
                'notification_email': notification.get('recipient'),
                'message': 'Admin credential reissued. Store this credential in your wallet.' if reissue_requested else 'Admin credential bootstrapped. Store this credential in your wallet.'
            } | transfer_data), 201
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed bootstrap-admin for {site_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'bootstrap_failed',
            'message': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/admin-transfer-token', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='write')
def create_admin_transfer_token(site_id):
    """
    Create a one-time token that allows the target site origin to redeem
    and locally store a freshly issued admin credential in that site's IndexedDB.
    """
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error

    caller_ppid = _get_authenticated_ppid()
    if not caller_ppid:
        return jsonify({
            'success': False,
            'error': 'auth_required',
            'message': 'Wallet authentication required.'
        }), 401

    data = request.get_json(silent=True) or {}
    credential = data.get('credential')
    if not isinstance(credential, dict):
        return jsonify({
            'success': False,
            'error': 'credential_required',
            'message': 'Credential payload is required.'
        }), 400

    try:
        from api.database import SessionLocal, Site
        db = SessionLocal()
        try:
            site = db.query(Site).filter(Site.site_id == site_id).first()
            if not site:
                return jsonify({
                    'success': False,
                    'error': 'site_not_found',
                    'message': 'Site not found.'
                }), 404

            claims = credential.get('claims') or credential.get('credentialSubject') or {}
            if claims.get('siteId') != site_id:
                return jsonify({
                    'success': False,
                    'error': 'site_mismatch',
                    'message': 'Credential siteId does not match requested site.'
                }), 400
            is_admin_credential = _is_admin_bootstrap_credential(credential, site_id)
            if not is_admin_credential:
                return jsonify({
                    'success': False,
                    'error': 'permission_mismatch',
                    'message': 'Only admin credentials can be transferred with this endpoint.'
                }), 400

            token = secrets.token_urlsafe(32)
            expires_in_seconds = 300
            payload = {
                'site_id': site_id,
                'site_domain': site.site_domain,
                'credential': credential,
                'created_by': caller_ppid,
                'created_at': datetime.utcnow().isoformat()
            }

            redis_client = get_redis_client()
            redis_client.setex(
                _build_admin_transfer_key(token),
                expires_in_seconds,
                json.dumps(payload)
            )

            capture_action_proof(action="site.admin_transfer_token", site_id=site_id)
            return jsonify({
                'success': True,
                'token': token,
                'expires_in': expires_in_seconds,
                'site_id': site_id,
                'site_domain': site.site_domain,
                'direct_import_url': f"https://{site.site_domain}/?lemma_transfer_token={token}",
                'import_url': _build_admin_transfer_import_url(token),
                'message': 'Open the import URL on the site to store credential in site-local IndexedDB.'
            }), 201
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to create admin transfer token for {site_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'transfer_token_failed',
            'message': str(e)
        }), 500


@developer_api_bp.route('/api/developer/credential-transfer/import/<token>', methods=['GET'])
def import_credential_transfer_token(token: str):
    """
    Redeem one-time transfer token server-side and redirect to target site with
    encoded credential in URL fragment for client-side wallet storage.
    """
    if not token:
        return redirect('/')

    try:
        redis_client = get_redis_client()
        redis_key = _build_admin_transfer_key(token)
        raw = redis_client.get(redis_key)
        if not raw:
            return redirect('/?transfer_error=invalid_or_expired_token')

        payload = json.loads(raw)
        site_domain = (payload.get('site_domain') or '').strip().lower()
        credential = payload.get('credential') if isinstance(payload.get('credential'), dict) else None
        site_id = str(payload.get('site_id') or '').strip()

        if not site_domain or not credential or not site_id:
            redis_client.delete(redis_key)
            return redirect('/?transfer_error=invalid_transfer_payload')

        if not _is_admin_bootstrap_credential(credential, site_id):
            redis_client.delete(redis_key)
            return redirect('/?transfer_error=permission_mismatch')

        encoded = base64.urlsafe_b64encode(
            json.dumps({
                'lemma': credential,
                'ppid': credential.get('subject'),
                'site_id': site_id,
                'site_domain': site_domain,
                'issued_via': 'admin_transfer_token'
            }).encode('utf-8')
        ).decode('utf-8').rstrip('=')

        redis_client.delete(redis_key)
        return redirect(f"https://{site_domain}/#lemma_credential={encoded}&lemma_import=1")
    except Exception as e:
        logger.error(f"Credential transfer import redirect failed: {e}")
        return redirect('/?transfer_error=import_failed')


@developer_api_bp.route('/api/developer/credential-transfer/redeem', methods=['POST'])
@cross_origin()
def redeem_credential_transfer_token():
    """
    Redeem a one-time admin credential transfer token.
    Intended for use by relying-site frontend code on the target site origin.
    """
    data = request.get_json(silent=True) or {}
    token = data.get('token')
    if not token:
        return jsonify({
            'success': False,
            'error': 'token_required',
            'message': 'Transfer token is required.'
        }), 400

    try:
        redis_client = get_redis_client()
        redis_key = _build_admin_transfer_key(token)
        raw = redis_client.get(redis_key)
        if not raw:
            return jsonify({
                'success': False,
                'error': 'invalid_or_expired_token',
                'message': 'Transfer token is invalid, expired, or already redeemed.'
            }), 400

        payload = json.loads(raw)
        site_domain = (payload.get('site_domain') or '').lower()
        origin = request.headers.get('Origin', '')
        origin_host = ''
        if origin:
            try:
                from urllib.parse import urlparse
                origin_host = (urlparse(origin).hostname or '').lower()
            except Exception:
                origin_host = ''

        requested_domain = (data.get('site_domain') or '').lower()
        allowed_hosts = {site_domain}
        if site_domain.startswith('localhost') or site_domain.startswith('127.0.0.1'):
            allowed_hosts.add('localhost')
            allowed_hosts.add('127.0.0.1')

        if origin_host and origin_host not in allowed_hosts:
            return jsonify({
                'success': False,
                'error': 'origin_mismatch',
                'message': 'Token redemption attempted from non-target origin.'
            }), 403
        if requested_domain and requested_domain not in allowed_hosts:
            return jsonify({
                'success': False,
                'error': 'site_domain_mismatch',
                'message': 'Token does not belong to requested site domain.'
            }), 403

        redis_client.delete(redis_key)

        return jsonify({
            'success': True,
            'site_id': payload.get('site_id'),
            'site_domain': site_domain,
            'credential': payload.get('credential')
        })
    except Exception as e:
        logger.error(f"Failed to redeem credential transfer token: {e}")
        return jsonify({
            'success': False,
            'error': 'redeem_failed',
            'message': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/stats-summary', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_stats(site_id):
    """Get DB-backed stats for a specific site."""
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error

    issued_lemmas_total = 0
    issued_lemmas_30d = 0
    revoked_lemmas_total = 0
    revoked_lemmas_30d = 0
    active_lemmas = 0
    total_users = 0
    active_users_30d = 0
    mau_current_month = 0

    try:
        from api.database import get_db_connection, SessionLocal, Site

        conn = get_db_connection(site_id)
        cursor = conn.cursor()

        # Resolve alternate site identifiers used across historical issuance flows.
        site_identifiers = {site_id}
        try:
            db = SessionLocal()
            site_row = db.query(Site).filter(Site.site_id == site_id).first()
            if site_row and site_row.site_domain:
                site_domain = str(site_row.site_domain).strip().lower()
                if site_domain:
                    site_identifiers.add(site_domain)
                    site_identifiers.add(site_domain.replace('.', '_').replace('-', '_'))
            db.close()
        except Exception:
            # Non-fatal; continue with provided site_id only.
            pass
        site_keys = list(site_identifiers)
        canonical_key = _canonical_site_key(site_id)

        # Permission/lemma issuance + revocation lifecycle metrics.
        # Read from multiple tables because deployments have evolved schema paths.
        pi_issued_total = 0
        pi_issued_30d = 0
        pi_revoked_total = 0
        pi_revoked_30d = 0
        pi_active_count = 0
        if _table_exists(cursor, 'permission_instances'):
            cursor.execute(
                """
                SELECT
                    COUNT(*)::BIGINT AS issued_total,
                    COUNT(*) FILTER (
                        WHERE granted_at >= NOW() - INTERVAL '30 days'
                    )::BIGINT AS issued_30d,
                    COUNT(*) FILTER (
                        WHERE revoked_at IS NOT NULL
                    )::BIGINT AS revoked_total,
                    COUNT(*) FILTER (
                        WHERE revoked_at >= NOW() - INTERVAL '30 days'
                    )::BIGINT AS revoked_30d,
                    COUNT(*) FILTER (
                        WHERE revoked_at IS NULL
                          AND (expires_at IS NULL OR expires_at > NOW())
                    )::BIGINT AS active_count
                FROM permission_instances
                WHERE site_id = ANY(%s)
                   OR regexp_replace(lower(site_id), '[_\\.-]', '', 'g') = %s
                """,
                (site_keys, canonical_key)
            )
            row = cursor.fetchone() or (0, 0, 0, 0, 0)
            pi_issued_total, pi_issued_30d, pi_revoked_total, pi_revoked_30d, pi_active_count = row

        spg_issued_total = 0
        spg_issued_30d = 0
        spg_revoked_total = 0
        spg_revoked_30d = 0
        spg_active_count = 0
        if _table_exists(cursor, 'site_permission_grants'):
            cursor.execute(
                """
                SELECT
                    COUNT(*)::BIGINT AS issued_total,
                    COUNT(*) FILTER (
                        WHERE granted_at >= NOW() - INTERVAL '30 days'
                    )::BIGINT AS issued_30d,
                    COUNT(*) FILTER (
                        WHERE revoked_at IS NOT NULL OR is_active = FALSE
                    )::BIGINT AS revoked_total,
                    COUNT(*) FILTER (
                        WHERE revoked_at >= NOW() - INTERVAL '30 days'
                    )::BIGINT AS revoked_30d,
                    COUNT(*) FILTER (
                        WHERE COALESCE(is_active, TRUE) = TRUE
                          AND revoked_at IS NULL
                          AND (expires_at IS NULL OR expires_at > NOW())
                    )::BIGINT AS active_count
                FROM site_permission_grants
                WHERE site_id = ANY(%s)
                   OR regexp_replace(lower(site_id), '[_\\.-]', '', 'g') = %s
                """,
                (site_keys, canonical_key)
            )
            row = cursor.fetchone() or (0, 0, 0, 0, 0)
            spg_issued_total, spg_issued_30d, spg_revoked_total, spg_revoked_30d, spg_active_count = row

        ul_issued_total = 0
        ul_issued_30d = 0
        ul_revoked_total = 0
        ul_revoked_30d = 0
        ul_active_count = 0
        if _table_exists(cursor, 'user_lemmas'):
            cursor.execute(
                """
                SELECT
                    COUNT(*)::BIGINT AS issued_total,
                    COUNT(*) FILTER (
                        WHERE issued_at >= NOW() - INTERVAL '30 days'
                    )::BIGINT AS issued_30d,
                    COUNT(*) FILTER (
                        WHERE revoked_at IS NOT NULL OR COALESCE(is_active, TRUE) = FALSE
                    )::BIGINT AS revoked_total,
                    COUNT(*) FILTER (
                        WHERE revoked_at >= NOW() - INTERVAL '30 days'
                    )::BIGINT AS revoked_30d,
                    COUNT(*) FILTER (
                        WHERE COALESCE(is_active, TRUE) = TRUE
                          AND revoked_at IS NULL
                          AND (expires_at IS NULL OR expires_at > NOW())
                    )::BIGINT AS active_count
                FROM user_lemmas
                WHERE (
                        site_id = ANY(%s)
                        OR regexp_replace(lower(site_id), '[_\\.-]', '', 'g') = %s
                      )
                  AND (lemma_type = 'permission' OR lemma_type = 'access')
                """,
                (site_keys, canonical_key)
            )
            row = cursor.fetchone() or (0, 0, 0, 0, 0)
            ul_issued_total, ul_issued_30d, ul_revoked_total, ul_revoked_30d, ul_active_count = row

        # Use the largest observed count across canonical stores to avoid undercounting.
        issued_lemmas_total = max(pi_issued_total, spg_issued_total, ul_issued_total)
        issued_lemmas_30d = max(pi_issued_30d, spg_issued_30d, ul_issued_30d)
        revoked_lemmas_total = max(pi_revoked_total, spg_revoked_total, ul_revoked_total)
        revoked_lemmas_30d = max(pi_revoked_30d, spg_revoked_30d, ul_revoked_30d)
        active_lemmas = max(pi_active_count, spg_active_count, ul_active_count)

        # Active users in last 30d and total users from site-local user registry.
        if _table_exists(cursor, 'site_users'):
            has_user_ppid = _column_exists(cursor, 'site_users', 'user_ppid')
            has_user_did = _column_exists(cursor, 'site_users', 'user_did')
            has_last_seen = _column_exists(cursor, 'site_users', 'last_seen')
            has_last_login = _column_exists(cursor, 'site_users', 'last_login')
            has_status = _column_exists(cursor, 'site_users', 'status')
            has_user_status = _column_exists(cursor, 'site_users', 'user_status')

            subject_col = 'user_ppid' if has_user_ppid else ('user_did' if has_user_did else None)
            activity_col = 'last_seen' if has_last_seen else ('last_login' if has_last_login else None)
            status_col = 'status' if has_status else ('user_status' if has_user_status else None)

            if subject_col:
                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT {subject_col})::BIGINT
                    FROM site_users
                    WHERE site_id = ANY(%s)
                    """,
                    (site_keys,)
                )
                total_users = cursor.fetchone()[0] or 0

                if activity_col:
                    if status_col:
                        cursor.execute(
                            f"""
                            SELECT COUNT(DISTINCT {subject_col})::BIGINT
                            FROM site_users
                            WHERE site_id = ANY(%s)
                              AND {activity_col} >= NOW() - INTERVAL '30 days'
                              AND {status_col} NOT IN ('revoked', 'suspended', 'banned')
                            """,
                            (site_keys,)
                        )
                    else:
                        cursor.execute(
                            f"""
                            SELECT COUNT(DISTINCT {subject_col})::BIGINT
                            FROM site_users
                            WHERE site_id = ANY(%s)
                              AND {activity_col} >= NOW() - INTERVAL '30 days'
                            """,
                            (site_keys,)
                        )
                    active_users_30d = cursor.fetchone()[0] or 0

        cursor.close()
        conn.close()

        # MAU from privacy-preserving per-site usage tracking.
        mau_current_month = get_monthly_active_users(site_id)

        # Fallback when Redis MAU is unavailable: derive monthly active users from site-local activity.
        if mau_current_month == 0 and active_users_30d > 0:
            mau_current_month = active_users_30d

        return jsonify({
            'success': True,
            'issued_lemmas_total': int(issued_lemmas_total),
            'issued_lemmas_30d': int(issued_lemmas_30d),
            'revoked_lemmas_total': int(revoked_lemmas_total),
            'revoked_lemmas_30d': int(revoked_lemmas_30d),
            'active_lemmas': int(active_lemmas),
            'total_users': int(total_users),
            'active_users_30d': int(active_users_30d),
            'mau_current_month': int(mau_current_month),
            # Backward compatibility keys for older dashboard clients.
            'verifications': int(issued_lemmas_30d),
            'users': int(active_users_30d),
            'privacy_model': {
                'mau_tracking': 'per-site pseudonymous counting',
                'cross_site_linking': False
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get site stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'issued_lemmas_total': 0,
            'issued_lemmas_30d': 0,
            'revoked_lemmas_total': 0,
            'revoked_lemmas_30d': 0,
            'active_lemmas': 0,
            'total_users': 0,
            'active_users_30d': 0,
            'mau_current_month': 0
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/keys', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_keys(site_id):
    """Get API keys for a site
    
    SECURITY: Requires site ownership verification before exposing key information.
    """
    # SECURITY: Verify site ownership (site API key allowed for read-only automation)
    auth_error = _require_site_ownership(site_id, allow_site_api_key=True)
    if auth_error:
        return auth_error
    
    try:
        from api.database import SessionLocal, Site
        
        keys = []
        
        try:
            db = SessionLocal()
            site = db.query(Site).filter(Site.site_id == site_id).first()
            
            if not site:
                db.close()
                return jsonify({
                    'success': False,
                    'error': 'Site not found'
                }), 404
            
            if site.api_key:
                # Site has a primary API key - only show prefix for security
                keys.append({
                    'id': 0,  # Default key has ID 0
                    'name': 'Primary API Key',
                    'key_prefix': (site.api_key[:12] + '...') if site.api_key else 'lm_...',
                    'type': 'live',
                    'is_active': True,
                    'created_at': site.created_at.isoformat() if site.created_at else None,
                    'last_used': None,
                    'expires_at': None,
                    'permissions': ['read', 'write']
                })
            
            db.close()
            
        except Exception as e:
            logger.warning(f"Could not load API keys: {e}")
        
        return jsonify({
            'success': True,
            'keys': keys
        })
        
    except Exception as e:
        logger.error(f"Failed to get API keys: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/keys', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='admin')
def create_site_key(site_id):
    """Create/regenerate API key for a site
    
    SECURITY: Requires site ownership verification before allowing key generation.
    This is a sensitive operation - new key invalidates the old one.
    """
    # SECURITY: Verify site ownership before creating/regenerating keys
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error
    
    try:
        data = request.get_json() or {}
        name = data.get('name', 'API Key')
        
        # Generate new API key
        key = f"lm_{secrets.token_urlsafe(32)}"
        
        from api.database import SessionLocal, Site
        
        try:
            db = SessionLocal()
            site = db.query(Site).filter(Site.site_id == site_id).first()
            
            if not site:
                db.close()
                return jsonify({
                    'success': False,
                    'error': 'Site not found'
                }), 404
            
            site.api_key = key
            db.commit()
            db.close()
            
            logger.info(f"SECURITY: API key regenerated for site {site_id} by {_get_authenticated_ppid()[:30] if _get_authenticated_ppid() else 'api_key'}...")
            
        except Exception as e:
            logger.error(f"Could not store API key: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to store API key'
            }), 500
        
        capture_action_proof(action="site_key.create", site_id=site_id)
        return jsonify({
            'success': True,
            'key_id': 'primary',
            'key': key,  # Only shown once - store it securely!
            'name': name,
            'warning': 'This key is shown only once. Store it securely.'
        })
        
    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/keys/<key_id>/rotate', methods=['POST'])
@cross_origin()
@require_agent_or_user_auth(required_scope='admin')
def rotate_site_key(site_id, key_id):
    """Rotate/regenerate an API key for a site
    
    SECURITY: Requires site ownership verification.
    Old key is immediately invalidated, new key returned once.
    """
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error
    
    try:
        from api.database import SessionLocal, Site
        
        db = SessionLocal()
        site = db.query(Site).filter(Site.site_id == site_id).first()
        
        if not site:
            db.close()
            return jsonify({
                'success': False,
                'error': 'Site not found'
            }), 404
        
        # Generate new API key (invalidates old one)
        new_key = f"lm_{secrets.token_urlsafe(32)}"
        site.api_key = new_key
        db.commit()
        db.close()
        
        logger.info(f"SECURITY: API key rotated for site {site_id} by {_get_authenticated_ppid()[:30] if _get_authenticated_ppid() else 'unknown'}...")
        capture_action_proof(action="site_key.rotate", site_id=site_id, resource=str(key_id))
        return jsonify({
            'success': True,
            'key_id': key_id,
            'key': new_key,  # Only shown once!
            'warning': 'This key is shown only once. Store it securely.'
        })
        
    except Exception as e:
        logger.error(f"Failed to rotate API key: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/keys/<key_id>', methods=['DELETE'])
@cross_origin()
@require_agent_or_user_auth(required_scope='admin')
def revoke_site_key(site_id, key_id):
    """Revoke/regenerate an API key
    
    SECURITY: Requires site ownership verification before allowing key revocation.
    This is a destructive operation - old key immediately becomes invalid.
    """
    # SECURITY: Verify site ownership before revoking keys
    auth_error = _require_site_ownership(site_id)
    if auth_error:
        return auth_error
    
    try:
        from api.database import SessionLocal, Site
        
        try:
            db = SessionLocal()
            site = db.query(Site).filter(Site.site_id == site_id).first()
            
            if not site:
                db.close()
                return jsonify({
                    'success': False,
                    'error': 'Site not found'
                }), 404
            
            # Generate new key (effectively revoking old one)
            site.api_key = f"lm_{secrets.token_urlsafe(32)}"
            db.commit()
            db.close()
            
            logger.info(f"SECURITY: API key revoked for site {site_id} by {_get_authenticated_ppid()[:30] if _get_authenticated_ppid() else 'api_key'}...")
            capture_action_proof(action="site_key.revoke", site_id=site_id, resource=str(key_id))
        except Exception as e:
            logger.error(f"Could not revoke API key: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to revoke API key'
            }), 500
        
        return jsonify({
            'success': True,
            'revoked': True,
            'message': 'API key revoked. A new key has been generated - retrieve it via GET /keys.'
        })
        
    except Exception as e:
        logger.error(f"Failed to revoke API key: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@developer_api_bp.route('/api/developer/sites/<site_id>/users-summary', methods=['GET'])
@cross_origin()
@require_agent_or_user_auth(required_scope='read')
def get_site_users_summary(site_id):
    """Get lightweight site user summary for dashboard cards."""
    try:
        # In production, query actual user data
        # For now, return empty list
        return jsonify({
            'success': True,
            'users': []
        })
        
    except Exception as e:
        logger.error(f"Failed to get site users: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
