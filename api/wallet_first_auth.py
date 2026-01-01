"""
Wallet-First Authentication API
Direct issuance to browser wallet with passkey unlock - no email required
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

logger = logging.getLogger(__name__)

wallet_first_bp = Blueprint('wallet_first', __name__)


def get_or_create_user(email: str = None, passkey_credential_id: str = None) -> dict:
    """
    Get or create a user based on email or passkey credential
    Returns user info for lemma issuance
    """
    db = get_db()
    try:
        # Try to find by passkey first (preferred for wallet-first flow)
        if passkey_credential_id:
            passkey = db.query(Passkey).filter(
                Passkey.credential_id == passkey_credential_id,
                Passkey.is_active == True
            ).first()
            
            if passkey:
                customer = db.query(Customer).filter(
                    Customer.customer_did == passkey.user_id
                ).first()
                if customer:
                    return {
                        'user_id': customer.customer_did,
                        'email': customer.email,
                        'role': 'admin' if customer.email and 'jedmckenna' in customer.email else 'customer',
                        'existing': True
                    }
        
        # Try to find by email
        if email:
            customer = db.query(Customer).filter(Customer.email == email.lower()).first()
            if customer:
                return {
                    'user_id': customer.customer_did,
                    'email': customer.email,
                    'role': 'admin' if 'jedmckenna' in email else 'customer',
                    'existing': True
                }
        
        # Create new user
        user_id = f"did:lemma:user_{secrets.token_hex(8)}"
        
        if email:
            result = customer_manager.create_customer(
                email=email,
                name=f"Wallet User",
                company="Personal"
            )
            if result.get('success'):
                user_id = result['customer']['customer_did']
        
        return {
            'user_id': user_id,
            'email': email,
            'role': 'customer',
            'existing': False
        }
        
    finally:
        db.close()


def issue_permission_lemma(user_id: str, site_id: str = 'lemma.id', permissions: list = None, 
                          granted_by: str = 'system', track_in_db: bool = True) -> dict:
    """
    Issue a permission lemma for direct wallet storage.
    Also tracks the grant in the database for admin management and revocation.
    
    Args:
        user_id: User's DID
        site_id: Site issuing the permission
        permissions: List of permission strings
        granted_by: Who granted this (for audit)
        track_in_db: Whether to store in user_permissions table (default True)
    """
    try:
        # Import the IAM issuer (same issuer used across the platform)
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        iam_issuer = issuer_manager.get_iam_issuer(site_id)
        
        # Build claims - Rust expects all values to be strings
        perm_list = permissions or ['read', 'write']
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(days=30)
        
        claims = {
            'type': 'permission',
            'siteId': site_id,
            'permissions': ','.join(perm_list),  # Convert list to comma-separated string
            'issuedAt': issued_at.isoformat() + 'Z',
            'expiresAt': expires_at.isoformat() + 'Z'
        }
        
        # Issue the credential
        credential_json = iam_issuer.issue_credential(user_id, claims)
        credential = json.loads(credential_json)
        
        # Add metadata for wallet storage
        credential['packageType'] = 'permission'
        credential['issuerInfo'] = {
            'did': iam_issuer.get_did(),
            'publicKey': iam_issuer.get_public_key_hex(),
            'name': 'Lemma IAM',
            'verified': True
        }
        
        # Track the grant in database for admin management and revocation
        if track_in_db:
            try:
                _track_permission_grant(
                    site_id=site_id,
                    user_did=user_id,
                    permission_id=','.join(perm_list),
                    credential_id=credential.get('id', ''),
                    granted_by=granted_by,
                    expires_at=expires_at
                )
            except Exception as db_err:
                logger.warning(f"⚠️ Failed to track permission in DB (credential still issued): {db_err}")
        
        logger.info(f"✅ Permission lemma issued for {user_id} on {site_id}")
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
    Issue a permission lemma directly to the user's wallet
    
    POST /api/wallet-auth/issue
    {
        "site_id": "lemma.id",  // Site requesting permission
        "wallet_id": "...",     // User's wallet ID
        "passkey_credential_id": "...",  // Optional: link to existing user
        "email": "user@example.com"  // Optional: for new users
    }
    
    Returns the lemma for client-side wallet storage
    """
    try:
        data = request.get_json() or {}
        site_id = data.get('site_id', 'lemma.id')
        wallet_id = data.get('wallet_id')
        passkey_credential_id = data.get('passkey_credential_id')
        email = data.get('email')
        
        # Get or create user
        user = get_or_create_user(
            email=email,
            passkey_credential_id=passkey_credential_id
        )
        
        # Issue permission lemma
        permission_lemma = issue_permission_lemma(
            user_id=user['user_id'],
            site_id=site_id,
            permissions=['read', 'write', 'dashboard']
        )
        
        # Set session for backwards compatibility
        session['customer_id'] = user['user_id']
        session['auth_method'] = 'wallet_passkey'
        session['wallet_id'] = wallet_id
        
        logger.info(f"✅ Issued permission to wallet for {user['user_id']}")
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['user_id'],
                'email': user.get('email'),
                'isNew': not user['existing']
            },
            'permission_lemma': permission_lemma,
            'message': 'Permission issued successfully. Store in your wallet.'
        })
        
    except Exception as e:
        logger.error(f"❌ Wallet issue failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@wallet_first_bp.route('/api/wallet-auth/register-and-issue', methods=['POST'])
@cross_origin()
def register_and_issue():
    """
    Combined endpoint: Register passkey + Issue permission in one step
    For new users who don't have a wallet yet
    
    POST /api/wallet-auth/register-and-issue
    {
        "site_id": "lemma.id",
        "passkey_credential": {...},  // WebAuthn registration response
        "wallet_id": "..."
    }
    """
    try:
        data = request.get_json() or {}
        site_id = data.get('site_id', 'lemma.id')
        wallet_id = data.get('wallet_id')
        passkey_credential = data.get('passkey_credential')
        
        # Verify we have a passkey credential
        if not passkey_credential:
            return jsonify({
                'success': False,
                'error': 'Passkey credential required'
            }), 400
        
        # Create user
        user_id = f"did:lemma:user_{secrets.token_hex(8)}"
        
        # Issue permission
        permission_lemma = issue_permission_lemma(
            user_id=user_id,
            site_id=site_id,
            permissions=['read', 'write', 'dashboard']
        )
        
        # Set session
        session['customer_id'] = user_id
        session['auth_method'] = 'wallet_passkey'
        session['wallet_id'] = wallet_id
        
        return jsonify({
            'success': True,
            'user': {
                'id': user_id,
                'isNew': True
            },
            'permission_lemma': permission_lemma,
            'message': 'Account created and permission issued!'
        })
        
    except Exception as e:
        logger.error(f"❌ Register and issue failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@wallet_first_bp.route('/api/wallet-auth/verify-session', methods=['POST'])
@cross_origin()
def verify_wallet_session():
    """
    Verify a wallet auth proof and establish session
    Called when wallet is unlocked to authenticate
    
    POST /api/wallet-auth/verify-session
    {
        "wallet_id": "...",
        "passkey_credential_id": "...",
        "unlocked_at": 1234567890,
        "permissions": ["lemma.id:read", "lemma.id:write"]
    }
    """
    try:
        data = request.get_json() or {}
        wallet_id = data.get('wallet_id')
        passkey_credential_id = data.get('passkey_credential_id')
        permissions = data.get('permissions', [])
        
        if not wallet_id:
            return jsonify({
                'success': False,
                'error': 'Wallet ID required'
            }), 400
        
        # Find user by passkey
        user = get_or_create_user(passkey_credential_id=passkey_credential_id)
        
        # Check for lemma.id permission
        has_lemma_permission = any('lemma.id' in p for p in permissions)
        
        # Set session
        session['customer_id'] = user['user_id']
        session['auth_method'] = 'wallet_passkey'
        session['wallet_id'] = wallet_id
        session['authenticated'] = True
        
        return jsonify({
            'success': True,
            'authenticated': True,
            'user': {
                'id': user['user_id'],
                'email': user.get('email'),
                'hasLemmaPermission': has_lemma_permission
            },
            'needsPermission': not has_lemma_permission
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
