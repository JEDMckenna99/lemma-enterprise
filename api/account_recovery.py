"""
Account Recovery API
Allows developers to recover access using their API key + site_id
"""

import logging
import secrets
import hashlib
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_cors import cross_origin
from api.admin_issuance_notifications import notify_admin_lemma_issued

logger = logging.getLogger(__name__)

account_recovery_bp = Blueprint('account_recovery', __name__)

# Redis client for distributed token storage (shared factory)
redis_client = None
try:
    from api.redis_client import get_shared_redis

    redis_client = get_shared_redis(decode_responses=True)
    if redis_client:
        logger.info("✅ Redis recovery token storage initialized")
    else:
        logger.warning("⚠️ REDIS_URL not set - using in-memory fallback")
except Exception as e:
    redis_client = None
    logger.warning(f"⚠️ Redis connection failed for recovery: {e}")

# In-memory fallback (for local dev only)
recovery_tokens_memory = {}
_recovery_memory_lock = threading.Lock()

RECOVERY_TOKEN_PREFIX = "lemma:recovery:"
RECOVERY_TOKEN_TTL = 900  # 15 minutes in seconds


def recovery_token_store_required() -> bool:
    """Production recovery completion requires durable Redis token storage."""
    try:
        from api.config import is_production

        return is_production()
    except ImportError:
        return False


def consume_recovery_token(token_hash: str) -> dict | None:
    """Atomically consume a one-time recovery token (GETDEL / pop)."""
    token_data = None
    redis_key = f"{RECOVERY_TOKEN_PREFIX}{token_hash}"

    if redis_client:
        try:
            raw = redis_client.getdel(redis_key)
            if raw:
                token_data = json.loads(raw)
        except Exception as exc:
            logger.error("Redis recovery token consume failed: %s", exc)
            return None
    else:
        with _recovery_memory_lock:
            token_data = recovery_tokens_memory.pop(token_hash, None)

    if not token_data:
        return None

    expires_at = token_data.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if not expires_at or expires_at < datetime.now(timezone.utc):
        return None
    if token_data.get("used"):
        return None
    return token_data


def store_recovery_token(token_hash: str, data: dict):
    """Store recovery token in Redis (or memory fallback)"""
    if redis_client:
        try:
            redis_client.setex(
                f"{RECOVERY_TOKEN_PREFIX}{token_hash}",
                RECOVERY_TOKEN_TTL,
                json.dumps(data, default=str)
            )
            return True
        except Exception as e:
            logger.error(f"Redis store failed: {e}")
    
    # Memory fallback
    recovery_tokens_memory[token_hash] = data
    return True


def get_recovery_token(token_hash: str) -> dict:
    """Get recovery token from Redis (or memory fallback)"""
    if redis_client:
        try:
            data = redis_client.get(f"{RECOVERY_TOKEN_PREFIX}{token_hash}")
            if data:
                token_data = json.loads(data)
                # Parse datetime string back to datetime
                if isinstance(token_data.get('expires_at'), str):
                    token_data['expires_at'] = datetime.fromisoformat(token_data['expires_at'].replace('Z', '+00:00'))
                return token_data
        except Exception as e:
            logger.error(f"Redis get failed: {e}")
    
    # Memory fallback
    return recovery_tokens_memory.get(token_hash)


def mark_token_used(token_hash: str):
    """Deprecated: prefer consume_recovery_token() for atomic single-use semantics."""
    token_data = get_recovery_token(token_hash)
    if token_data:
        token_data['used'] = True
        if redis_client:
            try:
                # Get remaining TTL
                ttl = redis_client.ttl(f"{RECOVERY_TOKEN_PREFIX}{token_hash}")
                if ttl > 0:
                    redis_client.setex(
                        f"{RECOVERY_TOKEN_PREFIX}{token_hash}",
                        ttl,
                        json.dumps(token_data, default=str)
                    )
            except Exception as e:
                logger.error(f"Redis mark used failed: {e}")
        else:
            with _recovery_memory_lock:
                recovery_tokens_memory[token_hash] = token_data


def _validate_replacement_passkey_proof(data: dict) -> tuple[bool, str, str, str]:
    """Require replacement wallet PPID + passkey credential id before issuing authority."""
    ppid = str(data.get("ppid") or "").strip()
    passkey_credential_id = str(
        data.get("passkey_credential_id") or data.get("passkeyCredentialId") or ""
    ).strip()
    if not ppid.startswith("did:lemma:ppid_"):
        return False, "replacement_ppid_required", ppid, passkey_credential_id
    if not passkey_credential_id:
        return False, "replacement_passkey_required", ppid, passkey_credential_id
    return True, "ok", ppid, passkey_credential_id


def clean_expired_tokens():
    """Remove expired tokens (only needed for memory fallback)"""
    if not redis_client:
        now = datetime.now(timezone.utc)
        expired = [k for k, v in recovery_tokens_memory.items() if v['expires_at'] < now]
        for k in expired:
            del recovery_tokens_memory[k]


@account_recovery_bp.route('/api/recovery/initiate', methods=['POST'])
@cross_origin()
def initiate_recovery():
    """
    Initiate account recovery using API key + site_id
    
    This is secure because:
    1. API key proves ownership of the site
    2. Recovery link is sent to admin_email on file (second factor)
    3. Token is time-limited and single-use
    """
    try:
        from api.database import SessionLocal, Site
        from api.rate_limiter import check_rate_limit
        
        data = request.get_json() or {}
        
        api_key = data.get('api_key', '').strip()
        site_id = data.get('site_id', '').strip()
        
        if not api_key or not site_id:
            return jsonify({
                'success': False,
                'error': 'API key and site ID are required'
            }), 400
        
        # Rate limit by IP
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        # Allow 5 attempts per hour per IP
        rate_key = f"recovery:{client_ip}"
        if not check_rate_limit(rate_key, max_requests=5, window_seconds=3600):
            logger.warning(f"Recovery rate limit exceeded for IP {client_ip}")
            return jsonify({
                'success': False,
                'error': 'Too many recovery attempts. Please try again later.'
            }), 429
        
        db = SessionLocal()
        
        try:
            # Look up site
            site = db.query(Site).filter(Site.site_id == site_id).first()
            
            if not site:
                # Don't reveal if site exists
                logger.warning(f"Recovery attempt for non-existent site: {site_id}")
                return jsonify({
                    'success': True,
                    'message': 'If the API key is valid, a recovery link has been sent to the admin email.'
                })
            
            from api.site_access import validate_site_api_key

            validation = validate_site_api_key(api_key)
            api_key_valid = (
                validation.get('valid')
                and validation.get('type') == 'customer'
                and validation.get('site_id') == site_id
            )
            
            if not api_key_valid:
                logger.warning(f"Recovery attempt with invalid API key for site: {site_id}")
                # Don't reveal that the key was wrong
                return jsonify({
                    'success': True,
                    'message': 'If the API key is valid, a recovery link has been sent to the admin email.'
                })
            
            # API key is valid - look up the admin email for this site
            # Priority: customer email (from customer who owns the site) > site.admin_email
            admin_email = None
            
            # Method 1: Look up customer via customer_id in sites table
            try:
                from api.database import get_db_connection, Customer
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.email FROM customers c
                    JOIN sites s ON s.customer_id = c.customer_id
                    WHERE s.site_id = %s AND c.email IS NOT NULL AND c.email != ''
                    LIMIT 1
                """, (site_id,))
                row = cursor.fetchone()
                if row and row[0] and '@' in row[0]:
                    admin_email = row[0]
                    logger.info(f"Found admin email via customer join for site {site_id}")
                cursor.close()
                conn.close()
            except Exception as e:
                logger.debug(f"Customer email lookup via join failed: {e}")
            
            # Method 2: Check if site.admin_email is a real email (not a PPID)
            if not admin_email and site.admin_email and '@' in site.admin_email:
                admin_email = site.admin_email
            
            # Method 3: Search customers whose sites JSON contains this site_id
            if not admin_email:
                try:
                    customers_with_site = db.query(Customer).filter(
                        Customer.email.isnot(None),
                        Customer.email != ''
                    ).all()
                    for c in customers_with_site:
                        if c.sites:
                            for s in (c.sites or []):
                                if isinstance(s, dict) and s.get('site_id') == site_id:
                                    if c.email and '@' in c.email:
                                        admin_email = c.email
                                        logger.info(f"Found admin email via customer sites JSON for site {site_id}")
                                        break
                        if admin_email:
                            break
                except Exception as e:
                    logger.debug(f"Customer email lookup via JSON failed: {e}")
            
            if not admin_email:
                logger.error(f"No admin email found for site {site_id}")
                return jsonify({
                    'success': False,
                    'error': 'No admin email found for this site. Contact support.'
                }), 400
            
            # Generate secure token
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Clean up old tokens (memory fallback only)
            clean_expired_tokens()
            
            # Store token in Redis (expires in 15 minutes)
            store_recovery_token(token_hash, {
                'site_id': site_id,
                'admin_email': admin_email,
                'expires_at': datetime.now(timezone.utc) + timedelta(minutes=15),
                'used': False,
                'created_ip': client_ip
            })
            
            # Send recovery email
            recovery_url = f"https://lemma.id/recover/complete?token={token}"
            
            try:
                from api.email_service import send_email
                
                send_email(
                    to=admin_email,
                    subject="Lemma.id Account Recovery",
                    html=f"""
                    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                        <div style="text-align: center; margin-bottom: 32px;">
                            <h1 style="color: #1e293b; font-size: 24px; margin: 0;">Account Recovery</h1>
                        </div>
                        
                        <p style="color: #334155; font-size: 16px; line-height: 1.6;">
                            A recovery request was made for site <strong>{site_id}</strong>.
                        </p>
                        
                        <p style="color: #334155; font-size: 16px; line-height: 1.6;">
                            Click the button below to reset your passkey and regain access to your account:
                        </p>
                        
                        <div style="text-align: center; margin: 32px 0;">
                            <a href="{recovery_url}" style="display: inline-block; background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                                Recover Account
                            </a>
                        </div>
                        
                        <p style="color: #64748b; font-size: 14px; line-height: 1.6;">
                            This link expires in 15 minutes and can only be used once.
                        </p>
                        
                        <p style="color: #64748b; font-size: 14px; line-height: 1.6;">
                            If you didn't request this recovery, someone may have access to your API key. 
                            You should rotate your API keys immediately.
                        </p>
                        
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 32px 0;">
                        
                        <p style="color: #94a3b8; font-size: 12px;">
                            Request IP: {client_ip}<br>
                            Site ID: {site_id}
                        </p>
                    </div>
                    """,
                    text=f"""
Account Recovery for {site_id}

A recovery request was made for your Lemma.id account.

Click here to recover your account: {recovery_url}

This link expires in 15 minutes.

If you didn't request this, rotate your API keys immediately.

Request IP: {client_ip}
                    """
                )
                
                logger.info(f"Recovery email sent for site {site_id} to {admin_email[:3]}***")
                
            except Exception as e:
                logger.error(f"Failed to send recovery email: {e}")
                # Still return success to not reveal info
            
            return jsonify({
                'success': True,
                'message': 'If the API key is valid, a recovery link has been sent to the admin email.'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Recovery initiation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Recovery failed. Please try again later.'
        }), 500


@account_recovery_bp.route('/api/recovery/validate', methods=['POST'])
@cross_origin()
def validate_recovery_token():
    """Validate a recovery token (used by frontend before showing passkey registration)"""
    try:
        data = request.get_json() or {}
        token = data.get('token', '').strip()
        
        if not token:
            return jsonify({'success': False, 'error': 'Token required'}), 400
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Get token from Redis (or memory fallback)
        token_data = get_recovery_token(token_hash)
        
        if not token_data:
            logger.warning(f"Recovery token not found: {token_hash[:12]}...")
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 400
        
        if token_data.get('used'):
            return jsonify({'success': False, 'error': 'Token already used'}), 400
        
        expires_at = token_data['expires_at']
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        
        if expires_at < datetime.now(timezone.utc):
            return jsonify({'success': False, 'error': 'Token expired'}), 400
        
        # Return site info (masked email)
        email = token_data['admin_email']
        masked_email = email[:3] + '***' + email[email.index('@'):] if '@' in email else '***'
        
        logger.info(f"Recovery token validated for site {token_data['site_id']}")
        
        return jsonify({
            'success': True,
            'site_id': token_data['site_id'],
            'email': masked_email
        })
        
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        return jsonify({'success': False, 'error': 'Validation failed'}), 500


@account_recovery_bp.route('/api/recovery/complete', methods=['POST'])
@cross_origin()
def complete_recovery():
    """
    Complete account recovery after email token + replacement passkey ceremony.

    Requires:
      1. API key + email token (initiate step)
      2. Atomically consumed one-time recovery token
      3. Replacement passkey credential id + wallet-derived PPID from the new device
    """
    try:
        data = request.get_json() or {}
        token = data.get('token', '').strip()

        if not token:
            return jsonify({'success': False, 'error': 'Token required'}), 400

        if recovery_token_store_required() and not redis_client:
            return jsonify({'success': False, 'error': 'recovery_unavailable'}), 503

        ok_proof, proof_err, ppid, passkey_credential_id = _validate_replacement_passkey_proof(data)
        if not ok_proof:
            return jsonify({'success': False, 'error': proof_err}), 400

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        token_data = consume_recovery_token(token_hash)
        if not token_data:
            return jsonify({'success': False, 'error': 'Invalid, expired, or already used token'}), 400

        site_id = token_data['site_id']
        admin_email = token_data['admin_email']

        from api.platform_owner import enforce_platform_admin_ppid, is_platform_site

        site_id_norm = str(site_id or '').strip().lower()
        if is_platform_site(site_id_norm):
            denied = enforce_platform_admin_ppid(ppid, site_id_norm)
            if denied:
                return jsonify(denied[0]), denied[1]

        from api.database import SessionLocal, Site
        db = SessionLocal()
        try:
            site = db.query(Site).filter(Site.site_id == site_id).first()
            if not site:
                return jsonify({'success': False, 'error': 'Site not found'}), 404
            site_domain = site.site_domain or site_id
        finally:
            db.close()

        recovery_method = 'passkey_signin' if data.get('passkey_signin') else 'passkey_register'
        credential = _issue_site_admin_proof(
            site_id=site_id,
            site_domain=site_domain,
            admin_email=admin_email,
            user_ppid=ppid,
            recovery_method=recovery_method,
        )

        if not credential:
            return jsonify({
                'success': False,
                'error': 'Failed to issue admin proof'
            }), 500

        if not _update_site_admin_ppid(site_id, admin_email, ppid):
            return jsonify({'success': False, 'error': 'admin_record_not_found'}), 403

        other_sites_updated = _update_all_admin_sites(admin_email, ppid, exclude_site_id=site_id)

        from flask import session as flask_session
        flask_session['recovery_complete'] = True
        flask_session['recovery_site_id'] = site_id
        flask_session['recovery_email'] = admin_email
        flask_session['customer_email'] = admin_email
        flask_session['user_email'] = admin_email

        logger.info(
            "Recovery complete - admin lemma issued for site %s to %s (passkey=%s...)",
            site_id,
            admin_email[:3] + "***",
            passkey_credential_id[:12],
        )

        return jsonify({
            'success': True,
            'message': 'Admin access restored',
            'site_id': site_id,
            'site_domain': site_domain,
            'credential': credential,
            'credential_id': credential.get('id'),
            'other_sites_updated': other_sites_updated,
            'redirect': '/developer'
        })

    except Exception as e:
        logger.error(f"Recovery completion failed: {e}")
        return jsonify({'success': False, 'error': 'Recovery failed'}), 500


def _issue_site_admin_proof(site_id: str, site_domain: str, admin_email: str, 
                            user_ppid: str = None, recovery_method: str = 'recovery'):
    """
    Issue a proper admin permission lemma for a site during recovery.
    
    This creates the same type of credential that developers get during normal
    site creation or admin self-issue, ensuring the recovered developer has
    full access to their platform.
    
    Args:
        site_id: The site's unique identifier
        site_domain: The site's domain
        admin_email: The admin email on file
        user_ppid: Optional wallet-derived PPID to issue to
        recovery_method: How recovery was completed (passkey_signin, passkey_register, wallet_session)
    
    Returns:
        dict: The permission lemma credential, or None on failure
    """
    try:
        from api.real_iam_manager import get_or_create_site_manager
        from api.ppid import derive_ppid_did
        
        manager = get_or_create_site_manager(site_id, site_domain)
        if not manager:
            logger.error(f"Failed to get IAM manager for site {site_id}")
            return None
        
        # Ensure admin permission type exists
        if 'admin' not in manager.permissions:
            manager.add_permission({
                'permission_id': 'admin',
                'display_name': 'Administrator',
                'scope': ['read', 'write', 'admin'],
                'conditions': [],
                'priority': 100
            })
        
        # Use wallet PPID if available, otherwise derive from email
        if user_ppid and user_ppid.startswith('did:lemma:ppid_'):
            subject_did = user_ppid
        else:
            subject_did = derive_ppid_did(admin_email, site_domain)
        
        # Issue the permission lemma with Ed25519 signature
        permission_lemma = manager.issue_permission_lemma(
            subject_did,
            'admin',
            expiry_days=365,
            custom_claims={
                'siteId': site_id,
                'siteDomain': site_domain,
                'accountType': 'admin',
                # Canonical admin compatibility identifier expected by clients.
                'permissionId': 'admin_access',
                # Preserve selected admin level separately.
                'permission_level': 'admin',
                'email': admin_email,
                'issuedVia': f'account_recovery_{recovery_method}',
                'recoveredAt': datetime.now(timezone.utc).isoformat()
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
            permission_lemma['claims']['permissionId'] = 'admin_access'
            permission_lemma['claims']['permission_level'] = 'admin'
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['permissionId'] = 'admin_access'
            permission_lemma['credentialSubject']['permission_level'] = 'admin'
        
        logger.info(f"Issued admin proof for recovery: site={site_id}, subject={subject_did[:40]}...")

        notify_admin_lemma_issued(
            site_id=site_id,
            site_domain=site_domain,
            user_did=subject_did,
            permission_level='admin',
            issued_via=f'account_recovery_{recovery_method}',
            credential_id=permission_lemma.get('id'),
            fallback_email=admin_email,
        )
        return permission_lemma
        
    except Exception as e:
        logger.error(f"Failed to issue admin proof during recovery: {e}")
        return None


def _update_site_admin_ppid(site_id: str, admin_email: str, new_ppid: str) -> bool:
    """
    Update the exact site_admins row for this recovery token's admin email.

    Returns True when an existing row was updated or a new row was created for a
    site whose admin_email matches the token. Never falls back to owner role.
    """
    try:
        from api.database import SessionLocal, Site, SiteAdmin

        db = SessionLocal()
        try:
            existing = db.query(SiteAdmin).filter(
                SiteAdmin.site_id == site_id,
                SiteAdmin.admin_did == new_ppid,
                SiteAdmin.is_active == True
            ).first()

            if existing:
                if admin_email and not existing.admin_email:
                    existing.admin_email = admin_email
                    db.commit()
                logger.info("Site admin record already exists for PPID %s... on site %s", new_ppid[:30], site_id)
                return True

            existing_admin = None
            if admin_email:
                existing_admin = db.query(SiteAdmin).filter(
                    SiteAdmin.site_id == site_id,
                    SiteAdmin.admin_email == admin_email,
                    SiteAdmin.is_active == True
                ).first()

            if existing_admin:
                old_ppid = existing_admin.admin_did
                existing_admin.admin_did = new_ppid
                existing_admin.last_activity = datetime.utcnow()
                db.commit()
                logger.info(
                    "Updated site admin PPID on site %s: %s... -> %s...",
                    site_id,
                    (old_ppid or "")[:20],
                    new_ppid[:20],
                )
                return True

            site_row = db.query(Site).filter(Site.site_id == site_id).first()
            if site_row and admin_email and site_row.admin_email == admin_email:
                db.add(SiteAdmin(
                    site_id=site_id,
                    admin_did=new_ppid,
                    admin_email=admin_email,
                    admin_role='owner',
                    is_active=True,
                    added_by='account_recovery'
                ))
                db.commit()
                logger.info("Created site admin record for %s on site %s (recovery)", admin_email, site_id)
                return True

            logger.warning(
                "Recovery admin update refused: no matching admin record for %s on site %s",
                admin_email,
                site_id,
            )
            return False

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to update site admin PPID: {e}")
        return False


def _update_all_admin_sites(admin_email: str, new_ppid: str, exclude_site_id: str = None) -> list:
    """
    Update ALL sites owned by this admin with the new PPID.
    
    When a developer recovers with a different wallet, their other sites still
    have the old PPID in site_admins. This finds all sites where the admin_email
    matches (in the sites table) and updates site_admins for each one.
    
    Returns list of other site_ids that were updated.
    """
    updated_sites = []
    
    if not admin_email:
        return updated_sites
    
    try:
        from api.database import SessionLocal, Site, SiteAdmin
        
        db = SessionLocal()
        try:
            # Find all sites where this email is the admin
            owned_sites = db.query(Site).filter(
                Site.admin_email == admin_email
            ).all()
            
            for site in owned_sites:
                if site.site_id == exclude_site_id:
                    continue  # Already handled
                
                # Check if this site already has a record with the new PPID
                existing = db.query(SiteAdmin).filter(
                    SiteAdmin.site_id == site.site_id,
                    SiteAdmin.admin_did == new_ppid,
                    SiteAdmin.is_active == True
                ).first()
                
                if existing:
                    continue

                old_admin = db.query(SiteAdmin).filter(
                    SiteAdmin.site_id == site.site_id,
                    SiteAdmin.admin_email == admin_email,
                    SiteAdmin.is_active == True
                ).first()

                if old_admin:
                    old_admin.admin_did = new_ppid
                    old_admin.last_activity = datetime.utcnow()
                    updated_sites.append(site.site_id)
                    logger.info("Updated PPID for additional site %s during recovery", site.site_id)
                elif site.admin_email == admin_email:
                    db.add(SiteAdmin(
                        site_id=site.site_id,
                        admin_did=new_ppid,
                        admin_email=admin_email,
                        admin_role='owner',
                        is_active=True,
                        added_by='account_recovery'
                    ))
                    updated_sites.append(site.site_id)
                    logger.info("Created admin record for additional site %s during recovery", site.site_id)
            
            if updated_sites:
                db.commit()
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Failed to update other admin sites: {e}")
    
    return updated_sites


@account_recovery_bp.route('/api/recovery/issue-admin-proof', methods=['POST'])
@cross_origin()
def issue_recovery_admin_proof():
    """
    Issue admin proof (permission lemma) after recovery authentication.
    
    This endpoint is called by the frontend AFTER the developer has:
    1. Validated their recovery token (API key + email verification)
    2. Authenticated via passkey (sign-in or register new)
    
    The recovery context is stored in the Flask session by complete_recovery().
    The wallet PPID comes from the now-unlocked wallet.
    
    POST /api/recovery/issue-admin-proof
    Body: {
        "site_id": "site_xxx",       // From recovery context
        "ppid": "did:lemma:ppid_xxx"  // From wallet.derivePPID()
    }
    """
    try:
        from flask import session as flask_session
        from api.database import SessionLocal, Site
        
        data = request.get_json() or {}
        site_id = data.get('site_id', '').strip()
        ppid = data.get('ppid', '').strip()
        
        if not site_id:
            return jsonify({'success': False, 'error': 'site_id required'}), 400
        
        if not ppid or not ppid.startswith('did:lemma:ppid_'):
            return jsonify({
                'success': False, 
                'error': 'Valid wallet PPID required',
                'message': 'Derive PPID from unlocked wallet: await wallet.derivePPID(siteDomain)'
            }), 400
        
        # Verify recovery context in session
        recovery_complete = flask_session.get('recovery_complete')
        recovery_site_id = flask_session.get('recovery_site_id')
        recovery_email = flask_session.get('recovery_email')
        
        if not recovery_complete:
            return jsonify({
                'success': False,
                'error': 'No active recovery session. Complete recovery first.'
            }), 403
        
        if recovery_site_id and recovery_site_id != site_id:
            return jsonify({
                'success': False,
                'error': 'Site ID does not match recovery session.'
            }), 403
        
        # Look up site
        db = SessionLocal()
        try:
            site = db.query(Site).filter(Site.site_id == site_id).first()
            if not site:
                return jsonify({'success': False, 'error': 'Site not found'}), 404
            
            site_domain = site.site_domain or site_id
            admin_email = recovery_email or site.admin_email
        finally:
            db.close()
        
        # Issue the admin proof
        credential = _issue_site_admin_proof(
            site_id=site_id,
            site_domain=site_domain,
            admin_email=admin_email,
            user_ppid=ppid,
            recovery_method='passkey_recovery'
        )
        
        if not credential:
            return jsonify({
                'success': False,
                'error': 'Failed to issue admin proof'
            }), 500
        
        # Update site_admins table with the new PPID for the recovered site
        _update_site_admin_ppid(site_id, admin_email, ppid)
        
        # Also update any OTHER sites this admin owns
        # (their old PPID won't match after wallet change)
        other_sites_updated = _update_all_admin_sites(admin_email, ppid, exclude_site_id=site_id)
        
        # Clear one-time recovery flag (but keep session active)
        flask_session.pop('recovery_complete', None)
        flask_session.pop('recovery_site_id', None)
        
        logger.info(f"Recovery admin proof issued for site {site_id} to PPID {ppid[:30]}...")
        if other_sites_updated:
            logger.info(f"Also updated {len(other_sites_updated)} other site(s): {other_sites_updated}")
        
        return jsonify({
            'success': True,
            'credential': credential,
            'credential_id': credential.get('id'),
            'site_id': site_id,
            'site_domain': site_domain,
            'other_sites_updated': other_sites_updated,
            'message': 'Admin proof issued. Store in your wallet.'
        })
        
    except Exception as e:
        logger.error(f"Recovery admin proof issuance failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to issue admin proof'}), 500


@account_recovery_bp.route('/api/recovery/complete-wallet', methods=['POST'])
@cross_origin()
def complete_recovery_wallet():
    """
    Deprecated: wallet-session recovery without replacement passkey is disabled.
    Use /api/recovery/complete with passkey + PPID after email token validation.
    """
    return jsonify({
        'success': False,
        'error': 'recovery_wallet_path_disabled',
        'message': 'Register or unlock a replacement passkey, then call /api/recovery/complete.',
    }), 403
