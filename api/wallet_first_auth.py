"""
Wallet-First Authentication API
================================

Issues permission lemmas directly to passkey-unlocked wallets.

IDENTITY MODEL (from whitepaper):
- User identified by PPID (Pairwise Pseudonymous Identifier)
- PPID = HMAC(wallet_secret, site_id) - DIFFERENT per site
- Sites CANNOT correlate users across sites (privacy)
- Same user at same site = same PPID (account continuity)

NO EMAIL REQUIRED - passkey/wallet is the root of trust.
"""

import os
import json
import secrets
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin

from .database import get_db, Customer, Passkey
from .customer_accounts import customer_manager
from .ppid import derive_ppid_from_passkey, derive_ppid_from_wallet_secret, canonicalize_rp_id

logger = logging.getLogger(__name__)

wallet_first_bp = Blueprint('wallet_first', __name__)


def derive_user_ppid(site_id: str, wallet_secret: str = None, passkey_credential_id: str = None) -> str:
    """
    Derive the user's PPID (Pairwise Pseudonymous Identifier) for a specific site.
    
    PPID = did:lemma:ppid_<HMAC(master_secret, site_id)>
    
    Each site gets a DIFFERENT identifier for the same user.
    This prevents cross-site tracking while maintaining account continuity.
    
    Args:
        site_id: The site domain/identifier
        wallet_secret: Wallet's master secret (preferred)
        passkey_credential_id: Passkey credential ID (fallback)
        
    Returns:
        Pairwise subject DID: did:lemma:ppid_<hash>
    """
    site = canonicalize_rp_id(site_id)
    
    # Prefer wallet secret (client-side derived)
    if wallet_secret:
        return derive_ppid_from_wallet_secret(wallet_secret, site)
    
    # Fallback to passkey-based derivation (server-side)
    if passkey_credential_id:
        return derive_ppid_from_passkey(passkey_credential_id, site)
    
    # Last resort: generate random (not recommended - loses continuity)
    logger.warning("⚠️ No wallet_secret or passkey - generating random PPID")
    random_secret = secrets.token_hex(32)
    return derive_ppid_from_wallet_secret(random_secret, site)


def get_or_create_user_for_site(site_id: str, wallet_secret: str = None, 
                                passkey_credential_id: str = None) -> dict:
    """
    Get or create a user record for permission tracking at a specific site.
    
    The user is identified by their PPID (site-specific, derived from wallet).
    
    Args:
        site_id: The site requesting the permission
        wallet_secret: Wallet's master secret
        passkey_credential_id: Passkey credential ID
        
    Returns:
        User info with site-specific PPID
    """
    # Derive the PPID for this site
    ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
    
    db = get_db()
    try:
        # Check if we have a record for this PPID
        # Note: PPIDs are site-specific, so we track per (site_id, ppid)
        # For now, we just track by ppid since it's already site-specific
        
        # Try to find existing user with this passkey
        if passkey_credential_id:
            passkey = db.query(Passkey).filter(
                Passkey.credential_id == passkey_credential_id,
                Passkey.is_active == True
            ).first()
            
            if passkey:
                return {
                    'ppid': ppid,
                    'passkey_user_id': passkey.user_id,
                    'existing': True
                }
        
        # New user for this site
        return {
            'ppid': ppid,
            'passkey_user_id': None,
            'existing': False
        }
        
    finally:
        db.close()


def issue_permission_lemma(subject_ppid: str, site_id: str = 'lemma.id', permissions: list = None, 
                          granted_by: str = 'system', track_in_db: bool = True) -> dict:
    """
    Issue a permission lemma for direct wallet storage.
    
    The lemma's SUBJECT is the user's PPID (site-specific identifier).
    The lemma's ISSUER is the site's DID (Ed25519 keypair).
    
    Args:
        subject_ppid: User's PPID for this site (did:lemma:ppid_xxx)
        site_id: Site issuing the permission
        permissions: List of permission strings
        granted_by: Who granted this (for audit)
        track_in_db: Whether to store in user_permissions table
    """
    try:
        # Import the IAM issuer (site's Ed25519 keypair)
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        site_issuer = issuer_manager.get_iam_issuer(site_id)
        
        # Build claims - Rust expects all values to be strings
        perm_list = permissions or ['read', 'write']
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(days=30)
        
        claims = {
            'type': 'permission',
            'siteId': site_id,
            'permissions': ','.join(perm_list),
            'issuedAt': issued_at.isoformat() + 'Z',
            'expiresAt': expires_at.isoformat() + 'Z'
        }
        
        # Issue the credential with PPID as subject
        # subject = user's PPID (site-specific)
        # issuer = site's DID
        credential_json = site_issuer.issue_credential(subject_ppid, claims)
        credential = json.loads(credential_json)
        
        # Add metadata for wallet storage
        credential['packageType'] = 'permission'
        credential['issuerInfo'] = {
            'did': site_issuer.get_did(),
            'publicKey': site_issuer.get_public_key_hex(),
            'name': f'{site_id} IAM',
            'verified': True
        }
        
        # Track the grant in database for admin management and revocation
        # Note: We track by PPID (site-specific) not a global user ID
        if track_in_db:
            try:
                _track_permission_grant(
                    site_id=site_id,
                    user_did=subject_ppid,  # PPID is the user identifier for this site
                    permission_id=','.join(perm_list),
                    credential_id=credential.get('id', ''),
                    granted_by=granted_by,
                    expires_at=expires_at
                )
            except Exception as db_err:
                logger.warning(f"⚠️ Failed to track permission in DB (credential still issued): {db_err}")
        
        logger.info(f"✅ Permission lemma issued: subject={subject_ppid[:40]}... site={site_id}")
        return credential
        
    except Exception as e:
        logger.error(f"❌ Failed to issue permission lemma: {e}")
        raise


def _track_permission_grant(site_id: str, user_did: str, permission_id: str, 
                           credential_id: str, granted_by: str, expires_at: datetime):
    """
    Track permission grant in database for admin management, revocation, and billing.
    This is separate from the credential itself (which is in the user's wallet).
    """
    from .database import get_db
    from sqlalchemy import text
    import hashlib
    
    db = get_db()
    try:
        # Create fingerprint from credential ID
        fingerprint = hashlib.sha256(credential_id.encode()).hexdigest()[:64]
        
        # Insert or update permission grant using PostgreSQL upsert
        db.execute(text("""
            INSERT INTO user_permissions 
            (site_id, user_did, permission_id, credential_fingerprint, granted_by, expires_at, granted_at)
            VALUES (:site_id, :user_did, :permission_id, :fingerprint, :granted_by, :expires_at, CURRENT_TIMESTAMP)
            ON CONFLICT ON CONSTRAINT unique_user_site_permission 
            DO UPDATE SET 
                credential_fingerprint = EXCLUDED.credential_fingerprint,
                granted_by = EXCLUDED.granted_by,
                expires_at = EXCLUDED.expires_at,
                granted_at = CURRENT_TIMESTAMP,
                revoked_at = NULL,
                revoked_by = NULL
        """), {
            'site_id': site_id,
            'user_did': user_did,
            'permission_id': permission_id,
            'fingerprint': fingerprint,
            'granted_by': granted_by,
            'expires_at': expires_at
        })
        db.commit()
        
        logger.debug(f"📝 Tracked permission grant: {user_did[:30]}... → {permission_id} on {site_id}")
        
    except Exception as e:
        logger.error(f"❌ Database tracking failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@wallet_first_bp.route('/api/wallet-auth/issue', methods=['POST'])
@cross_origin()
def issue_to_wallet():
    """
    Issue a permission lemma directly to the user's wallet.
    
    IDENTITY MODEL:
    - User identified by PPID (Pairwise Pseudonymous Identifier)
    - PPID = HMAC(wallet_secret, site_id) - DIFFERENT per site
    - This prevents cross-site user tracking
    
    POST /api/wallet-auth/issue
    {
        "site_id": "example.com",           // Site requesting permission
        "wallet_secret": "hex...",          // Wallet's master secret (for PPID derivation)
        "passkey_credential_id": "..."      // Passkey that unlocked the wallet (fallback)
    }
    
    Returns:
    - permission_lemma: Signed credential with subject=PPID
    - ppid: The user's PPID for this site
    """
    try:
        data = request.get_json() or {}
        
        # Validate site_id - allow lemma.id default for backwards compatibility
        from .validation import validate_site_id, ValidationError
        try:
            site_id = validate_site_id(data.get('site_id'), required=False, allow_lemma_default=True)
        except ValidationError as ve:
            return jsonify({
                'success': False,
                'error': 'validation_error',
                'message': str(ve)
            }), 400
        
        wallet_secret = data.get('wallet_secret')  # For PPID derivation
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({
                'success': False,
                'error': 'Either wallet_secret or passkey_credential_id required for PPID derivation'
            }), 400
        
        # Derive PPID for this site (site-specific user identifier)
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        # Check if this is an existing user for this site
        user_info = get_or_create_user_for_site(site_id, wallet_secret, passkey_credential_id)
        
        # Issue permission lemma with PPID as subject
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=['read', 'write', 'access'],
            granted_by='wallet_auth'
        )
        
        # Set session for backwards compatibility
        session['customer_id'] = ppid
        session['auth_method'] = 'wallet_passkey'
        session['site_id'] = site_id
        
        logger.info(f"✅ Issued permission to wallet: ppid={ppid[:40]}... site={site_id}")
        
        return jsonify({
            'success': True,
            'ppid': ppid,  # User's identifier for THIS site only
            'site_id': site_id,
            'is_new_user': not user_info['existing'],
            'permission_lemma': permission_lemma,
            'message': 'Permission lemma issued. Store in wallet.'
        })
        
    except Exception as e:
        logger.error(f"❌ Wallet issue failed: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@wallet_first_bp.route('/api/wallet-auth/register-and-issue', methods=['POST'])
@cross_origin()
def register_and_issue():
    """
    Combined endpoint: Register passkey + Issue permission in one step.
    
    POST /api/wallet-auth/register-and-issue
    {
        "site_id": "example.com",
        "wallet_secret": "hex...",          // Wallet's master secret
        "passkey_credential_id": "..."      // New passkey credential ID
    }
    """
    try:
        data = request.get_json() or {}
        site_id = data.get('site_id', 'lemma.id')
        wallet_secret = data.get('wallet_secret')
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({
                'success': False,
                'error': 'Either wallet_secret or passkey_credential_id required'
            }), 400
        
        # Derive PPID for this site
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        # Issue permission lemma with PPID as subject
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=['read', 'write', 'access']
        )
        
        # Set session
        session['customer_id'] = ppid
        session['auth_method'] = 'wallet_passkey'
        session['site_id'] = site_id
        
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'is_new_user': True,
            'permission_lemma': permission_lemma,
            'message': 'Wallet registered and permission issued!'
        })
        
    except Exception as e:
        logger.error(f"❌ Register and issue failed: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@wallet_first_bp.route('/api/wallet-auth/verify-session', methods=['POST'])
@cross_origin()
def verify_wallet_session():
    """
    Verify wallet unlock and check permissions for a site.
    
    POST /api/wallet-auth/verify-session
    {
        "site_id": "example.com",           // Site checking permission
        "wallet_secret": "hex...",          // For PPID derivation
        "passkey_credential_id": "...",     // Passkey that unlocked wallet
        "permissions": ["example.com:read"] // Permissions from wallet
    }
    """
    try:
        data = request.get_json() or {}
        site_id = data.get('site_id', 'lemma.id')
        wallet_secret = data.get('wallet_secret')
        passkey_credential_id = data.get('passkey_credential_id')
        permissions = data.get('permissions', [])
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({
                'success': False,
                'error': 'Either wallet_secret or passkey_credential_id required'
            }), 400
        
        # Derive PPID for this site
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        # Check if user has permission for this site
        site_canonical = canonicalize_rp_id(site_id)
        has_site_permission = any(site_canonical in p for p in permissions)
        
        # Set session (for backwards compatibility)
        session['customer_id'] = ppid
        session['auth_method'] = 'wallet_passkey'
        session['site_id'] = site_id
        session['authenticated'] = True
        
        return jsonify({
            'success': True,
            'authenticated': True,
            'ppid': ppid,
            'site_id': site_id,
            'has_permission': has_site_permission,
            'needs_permission': not has_site_permission
        })
        
    except Exception as e:
        logger.error(f"❌ Session verify failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@wallet_first_bp.route('/api/wallet-auth/debug-hash', methods=['POST'])
@cross_origin()
def debug_credential_hash():
    """
    Debug endpoint: returns the expected hash for a credential
    Use this to compare with client-side hash calculation
    """
    try:
        data = request.get_json() or {}
        credential = data.get('credential')
        
        if not credential:
            return jsonify({'success': False, 'error': 'No credential provided'}), 400
        
        from lemma_crypto import PyMinimalVerifier
        import hashlib
        import struct
        
        # Recreate the signing message the same way Rust does
        hasher = hashlib.sha256()
        
        # 1. ID
        hasher.update(credential['id'].encode('utf-8'))
        
        # 2. Issuer
        hasher.update(credential['issuer'].encode('utf-8'))
        
        # 3. Subject
        hasher.update(credential['subject'].encode('utf-8'))
        
        # 4. issued_at (little-endian u64)
        issued_at = credential.get('issuanceDate', 0)
        hasher.update(struct.pack('<Q', issued_at))
        
        # 5. expires_at (little-endian u64, if present)
        expires_at = credential.get('expirationDate')
        if expires_at is not None:
            hasher.update(struct.pack('<Q', expires_at))
        
        # 6. Claims in sorted order
        claims = credential.get('credentialSubject', credential.get('claims', {}))
        sorted_keys = sorted(claims.keys())
        
        claim_details = []
        for key in sorted_keys:
            value = claims[key]
            # Rust uses serde_json::to_string which wraps strings in quotes
            import json
            value_json = json.dumps(value)
            hasher.update(key.encode('utf-8'))
            hasher.update(value_json.encode('utf-8'))
            claim_details.append({
                'key': key,
                'value_json': value_json,
                'key_bytes': key.encode('utf-8').hex(),
                'value_bytes': value_json.encode('utf-8').hex()
            })
        
        expected_hash = hasher.hexdigest()
        
        return jsonify({
            'success': True,
            'expected_hash': expected_hash,
            'debug': {
                'id': credential['id'],
                'issuer': credential['issuer'],
                'subject': credential['subject'],
                'issuanceDate': issued_at,
                'issuanceDate_bytes': struct.pack('<Q', issued_at).hex(),
                'expirationDate': expires_at,
                'expirationDate_bytes': struct.pack('<Q', expires_at).hex() if expires_at else None,
                'claims_keys': sorted_keys,
                'claims_details': claim_details
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Debug hash failed: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
