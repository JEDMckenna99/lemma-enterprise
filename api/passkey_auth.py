"""
Passkey (WebAuthn) Authentication for Lemma
Enables hardware-backed authentication with embedded proofs in lemmas

SECURITY NOTES:
- All auth endpoints require cryptographic verification
- CORS is restricted to allowed origins only
- Challenge expiration is enforced
- User verification is required
"""

import os
import json
import base64
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, session, make_response
from flask_cors import cross_origin

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    PublicKeyCredentialDescriptor,
    AuthenticatorTransport,
    AuthenticationCredential,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from .database import get_db, Passkey, Customer
from auth.rate_limiter import rate_limit, auth_limit, registration_limit
from auth import redis_store

logger = logging.getLogger(__name__)

passkey_bp = Blueprint('passkey', __name__)

# Configuration
RP_ID = os.getenv('PASSKEY_RP_ID', 'lemma.id')
RP_NAME = os.getenv('PASSKEY_RP_NAME', 'Lemma')
ORIGIN = os.getenv('PASSKEY_ORIGIN', 'https://lemma.id')
EXPECTED_ORIGIN = os.getenv('PASSKEY_EXPECTED_ORIGIN', 'https://lemma.id')

# SECURITY: Allowed CORS origins for auth endpoints
ALLOWED_AUTH_ORIGINS = set(
    o.strip().lower() for o in 
    os.getenv('LEMMA_ALLOWED_ORIGINS', 'https://lemma.id,https://www.lemma.id').split(',')
    if o.strip()
)
ALLOWED_ORIGIN_SUFFIXES = [
    s.strip().lower() for s in
    os.getenv('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '.lemma.id').split(',')
    if s.strip()
]


def _is_origin_allowed(origin: str) -> bool:
    """Check if origin is allowed for CORS"""
    if not origin:
        return False
    
    origin_lower = origin.lower()
    
    # Check exact match
    if origin_lower in ALLOWED_AUTH_ORIGINS:
        return True
    
    # Check suffix match
    parsed = urlparse(origin)
    hostname = parsed.hostname or ''
    for suffix in ALLOWED_ORIGIN_SUFFIXES:
        if hostname.endswith(suffix.lstrip('.')):
            return True
    
    return False


def secure_cors(f):
    """
    CORS decorator that restricts to allowed origins only.
    
    SECURITY: This is stricter than @cross_origin() which allows all origins.
    Only origins in LEMMA_ALLOWED_ORIGINS or matching LEMMA_ALLOWED_ORIGIN_SUFFIXES
    are allowed.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        origin = request.headers.get('Origin')
        
        # Handle preflight
        if request.method == 'OPTIONS':
            response = make_response()
            if _is_origin_allowed(origin):
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-CSRF-Token'
            return response
        
        # Execute the function
        result = f(*args, **kwargs)
        
        # Add CORS headers to response if origin is allowed
        if _is_origin_allowed(origin):
            if isinstance(result, tuple):
                response = result[0] if hasattr(result[0], 'headers') else make_response(result[0])
                status = result[1] if len(result) > 1 else 200
            else:
                response = result if hasattr(result, 'headers') else make_response(result)
                status = 200
            
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            
            return (response, status) if isinstance(result, tuple) else response
        
        return result
    
    return decorated_function

# Challenge storage - uses Redis in production for multi-dyno support
# Falls back to thread-safe in-memory storage for local development
CHALLENGE_TTL_SECONDS = 300  # 5 minutes


def store_challenge(key: str, value: dict) -> None:
    """
    Store a challenge with automatic expiration.

    Uses Redis in production (supports multiple Heroku dynos).
    Falls back to in-memory for local development.
    """
    redis_store.store(f"challenge:{key}", value, ttl_seconds=CHALLENGE_TTL_SECONDS)


def get_challenge(key: str) -> dict | None:
    """
    Retrieve a stored challenge.

    Returns None if not found or expired.
    """
    return redis_store.get(f"challenge:{key}")


def delete_challenge(key: str) -> bool:
    """
    Delete a challenge after use.

    Returns True if the challenge existed.
    """
    return redis_store.delete(f"challenge:{key}")


def cleanup_expired_challenges() -> int:
    """
    Clean up expired challenges.

    Note: Redis handles expiration automatically, so this only
    affects the in-memory fallback store.
    """
    return redis_store.cleanup_expired()


def _extract_passkey_algorithm(credential: dict) -> int | None:
    """
    Extract COSE algorithm from client credential payload when available.

    Browser registration responses can expose this as
    `credential.response.publicKeyAlgorithm`.
    """
    if not isinstance(credential, dict):
        return None

    response = credential.get('response')
    if not isinstance(response, dict):
        return None

    alg = response.get('publicKeyAlgorithm')
    if isinstance(alg, int):
        return alg

    if isinstance(alg, str):
        try:
            return int(alg)
        except ValueError:
            return None

    return None


def get_user_passkeys(user_id: str) -> list:
    """Get all passkeys for a user"""
    db = get_db()
    try:
        passkeys = db.query(Passkey).filter(
            Passkey.user_id == user_id,
            Passkey.is_active == True
        ).all()
        return passkeys
    finally:
        db.close()


def save_passkey(user_id: str, credential_id: bytes, public_key: bytes, 
                 sign_count: int, device_name: str = None,
                 authenticator_type: str = None, transports: list = None,
                 attestation_format: str = None, attestation_data: bytes = None) -> Passkey:
    """Save a new passkey to the database"""
    db = get_db()
    try:
        passkey = Passkey(
            user_id=user_id,
            credential_id=base64.urlsafe_b64encode(credential_id).decode('utf-8'),
            public_key=base64.urlsafe_b64encode(public_key).decode('utf-8'),
            sign_count=sign_count,
            device_name=device_name or "Passkey",
            authenticator_type=authenticator_type,
            transports=transports or [],
            attestation_format=attestation_format,
            attestation_data=base64.urlsafe_b64encode(attestation_data).decode('utf-8') if attestation_data else None,
            created_at=datetime.utcnow()
        )
        db.add(passkey)
        db.commit()
        db.refresh(passkey)
        logger.info(f"✅ Passkey saved for user {user_id}")
        return passkey
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to save passkey: {e}")
        raise
    finally:
        db.close()


def get_passkey_by_credential_id(credential_id: str) -> Passkey:
    """Get passkey by credential ID"""
    db = get_db()
    try:
        return db.query(Passkey).filter(
            Passkey.credential_id == credential_id,
            Passkey.is_active == True
        ).first()
    finally:
        db.close()


def update_passkey_sign_count(passkey_id: int, new_sign_count: int):
    """Update the sign count after successful authentication"""
    db = get_db()
    try:
        passkey = db.query(Passkey).filter(Passkey.id == passkey_id).first()
        if passkey:
            passkey.sign_count = new_sign_count
            passkey.last_used_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


# ============================================
# REGISTRATION ENDPOINTS
# ============================================

@passkey_bp.route('/api/passkey/register/begin', methods=['POST', 'OPTIONS'])
@secure_cors
@rate_limit(registration_limit)
def passkey_register_begin():
    """
    Begin passkey registration - returns options for navigator.credentials.create()
    
    SECURITY: User ID and email MUST come from authenticated session.
    Request body can only provide device_name.
    This prevents attackers from registering passkeys to arbitrary users.
    
    POST /api/passkey/register/begin
    {
        "device_name": "My iPhone"  // optional
    }
    
    Requires: Authenticated session with customer_id and user_email
    """
    try:
        data = request.get_json() or {}
        
        # SECURITY: User identity MUST come from authenticated session only
        # Do NOT accept user_id or user_email from request body
        user_id = session.get('customer_id')
        user_email = session.get('user_email')
        device_name = data.get('device_name', 'Passkey')
        
        # SECURITY: Reject if user_id/user_email provided in request (prevent spoofing)
        if data.get('user_id') and data.get('user_id') != user_id:
            logger.warning(f"🚫 SECURITY: Attempt to register passkey for different user_id: {data.get('user_id')}")
            return jsonify({
                'success': False,
                'error': 'Cannot register passkey for different user - authentication required'
            }), 403
        
        if not user_id or not user_email:
            return jsonify({
                'success': False,
                'error': 'Authentication required - please sign in first'
            }), 401
        
        # Get existing passkeys to exclude them
        existing_passkeys = get_user_passkeys(user_id)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(pk.credential_id),
                transports=[AuthenticatorTransport(t) for t in (pk.transports or [])]
            )
            for pk in existing_passkeys
        ]
        
        # Generate registration options
        options = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=user_id.encode('utf-8'),
            user_name=user_email,
            user_display_name=user_email.split('@')[0],
            exclude_credentials=exclude_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
            timeout=60000,  # 60 seconds
        )
        
        # Store challenge for verification (thread-safe)
        challenge_key = f"passkey_reg_{user_id}"
        store_challenge(challenge_key, {
            'challenge': base64.urlsafe_b64encode(options.challenge).decode('utf-8'),
            'user_id': user_id,
            'user_email': user_email,
            'device_name': device_name,
            'expires': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        })
        
        logger.info(f"🔐 Passkey registration started for {user_email}")
        
        return jsonify({
            'success': True,
            'options': json.loads(options_to_json(options))
        })
        
    except Exception as e:
        logger.error(f"❌ Passkey registration begin failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@passkey_bp.route('/api/passkey/register/complete', methods=['POST', 'OPTIONS'])
@secure_cors
@rate_limit(registration_limit)
def passkey_register_complete():
    """
    Complete passkey registration - verify and store the credential
    
    SECURITY: User ID MUST come from authenticated session.
    This prevents attackers from completing registration for arbitrary users.
    
    POST /api/passkey/register/complete
    {
        "credential": { ... WebAuthn credential response ... }
    }
    
    Requires: Authenticated session with customer_id
    """
    try:
        data = request.get_json()
        
        # SECURITY: User identity MUST come from authenticated session only
        user_id = session.get('customer_id')
        credential = data.get('credential')
        
        # SECURITY: Reject if user_id provided in request and doesn't match session
        if data.get('user_id') and data.get('user_id') != user_id:
            logger.warning(f"🚫 SECURITY: Attempt to complete passkey reg for different user: {data.get('user_id')}")
            return jsonify({
                'success': False,
                'error': 'Cannot register passkey for different user'
            }), 403
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Authentication required - please sign in first'
            }), 401
            
        if not credential:
            return jsonify({
                'success': False,
                'error': 'WebAuthn credential response is required'
            }), 400
        
        # Retrieve stored challenge (thread-safe)
        challenge_key = f"passkey_reg_{user_id}"
        stored = get_challenge(challenge_key)

        if not stored:
            return jsonify({
                'success': False,
                'error': 'Registration session expired or not started'
            }), 400

        # SECURITY: Verify challenge hasn't expired
        expires_str = stored.get('expires')
        if expires_str:
            expires = datetime.fromisoformat(expires_str)
            if datetime.utcnow() > expires:
                delete_challenge(challenge_key)
                return jsonify({
                    'success': False,
                    'error': 'Registration challenge expired - please start again'
                }), 400
        
        # Verify the registration with user verification REQUIRED
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64.urlsafe_b64decode(stored['challenge']),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_user_verification=True,  # SECURITY: Require user verification
        )
        
        # Save the passkey
        passkey = save_passkey(
            user_id=user_id,
            credential_id=verification.credential_id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
            device_name=stored.get('device_name', 'Passkey'),
            authenticator_type=verification.credential_device_type,
            transports=credential.get('transports', []),
            attestation_format=verification.fmt if hasattr(verification, 'fmt') else None,
            attestation_data=verification.attestation_object if hasattr(verification, 'attestation_object') else None,
        )
        
        # Clean up challenge (thread-safe)
        delete_challenge(challenge_key)

        logger.info(f"✅ Passkey registered for {stored['user_email']}")
        
        passkey_algorithm = _extract_passkey_algorithm(credential)

        # Return public key for local wallet storage (wallet-centric architecture)
        return jsonify({
            'success': True,
            'passkey_id': passkey.id,
            'device_name': passkey.device_name,
            'credential_id': passkey.credential_id,
            'public_key': passkey.public_key,  # For local verification
            'message': 'Passkey registered successfully',
            'wallet_storage': {
                'credentialId': passkey.credential_id,
                'publicKey': passkey.public_key,
                'algorithm': passkey_algorithm
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Passkey registration complete failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

@passkey_bp.route('/api/passkey/authenticate/begin', methods=['POST', 'OPTIONS'])
@secure_cors
@rate_limit(auth_limit)
def passkey_authenticate_begin():
    """
    Begin passkey authentication - returns options for navigator.credentials.get()
    
    POST /api/passkey/authenticate/begin
    {
        "user_id": "customer_abc123"  // optional for discoverable credentials
    }
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        
        # Get allowed credentials if user_id provided
        allow_credentials = None
        if user_id:
            passkeys = get_user_passkeys(user_id)
            if passkeys:
                allow_credentials = [
                    PublicKeyCredentialDescriptor(
                        id=base64.urlsafe_b64decode(pk.credential_id),
                        transports=[AuthenticatorTransport(t) for t in (pk.transports or [])]
                    )
                    for pk in passkeys
                ]
        
        # Generate authentication options
        options = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
            timeout=60000,
        )
        
        # Store challenge (thread-safe)
        challenge_b64 = base64.urlsafe_b64encode(options.challenge).decode('utf-8')
        challenge_key = f"passkey_auth_{challenge_b64[:16]}"
        store_challenge(challenge_key, {
            'challenge': challenge_b64,
            'user_id': user_id,
            'expires': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        })
        
        logger.info(f"🔐 Passkey authentication started")
        
        return jsonify({
            'success': True,
            'options': json.loads(options_to_json(options)),
            'challenge_key': challenge_key
        })
        
    except Exception as e:
        logger.error(f"❌ Passkey authenticate begin failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@passkey_bp.route('/api/passkey/authenticate/complete', methods=['POST', 'OPTIONS'])
@secure_cors
@rate_limit(auth_limit)
def passkey_authenticate_complete():
    """
    Complete passkey authentication - verify and issue lemma with embedded proof
    
    POST /api/passkey/authenticate/complete
    {
        "credential": { ... WebAuthn credential response ... },
        "challenge_key": "passkey_auth_xxx"
    }
    """
    try:
        data = request.get_json()
        credential = data.get('credential')
        challenge_key = data.get('challenge_key')
        
        if not credential or not challenge_key:
            return jsonify({
                'success': False,
                'error': 'credential and challenge_key are required'
            }), 400
        
        # Get credential ID and find the passkey
        credential_id_b64 = credential.get('id')
        logger.info(f"🔐 Looking up passkey with credential_id: {credential_id_b64[:20] if credential_id_b64 else 'None'}...")
        passkey = get_passkey_by_credential_id(credential_id_b64)
        
        if not passkey:
            logger.warning(f"❌ Passkey NOT FOUND for credential_id: {credential_id_b64[:30] if credential_id_b64 else 'None'}...")
            # Debug: Check if passkey exists but is inactive
            from api.database import get_db, Passkey as PasskeyModel
            db = get_db()
            try:
                inactive = db.query(PasskeyModel).filter(PasskeyModel.credential_id == credential_id_b64).first()
                if inactive:
                    logger.warning(f"❌ Passkey EXISTS but is_active={inactive.is_active} for user {inactive.user_id}")
                else:
                    logger.warning(f"❌ No passkey with this credential_id exists in DB at all")
            finally:
                db.close()
            return jsonify({
                'success': False,
                'error': 'Passkey not found'
            }), 401
        
        # Retrieve stored challenge (thread-safe)
        stored = get_challenge(challenge_key)
        if not stored:
            return jsonify({
                'success': False,
                'error': 'Authentication session expired'
            }), 400

        # SECURITY: Verify challenge hasn't expired
        expires_str = stored.get('expires')
        if expires_str:
            expires = datetime.fromisoformat(expires_str)
            if datetime.utcnow() > expires:
                delete_challenge(challenge_key)
                return jsonify({
                    'success': False,
                    'error': 'Authentication challenge expired - please start again'
                }), 400
        
        # Verify the authentication
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64.urlsafe_b64decode(stored['challenge']),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64.urlsafe_b64decode(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
        
        # Update sign count
        update_passkey_sign_count(passkey.id, verification.new_sign_count)

        # Clean up challenge (thread-safe)
        delete_challenge(challenge_key)

        # Get user info and stored wallet_id
        db = get_db()
        wallet_id = None
        try:
            customer = db.query(Customer).filter(
                Customer.customer_id == passkey.user_id
            ).first()
            user_email = customer.email if customer else None
            user_role = customer.role if customer else 'user'
            wallet_id = customer.wallet_id if customer else None
            
            # Generate wallet_id if not set (for cross-device sync)
            if not wallet_id and customer:
                import secrets
                wallet_id = f"wallet_{secrets.token_hex(16)}"
                customer.wallet_id = wallet_id
                db.commit()
                logger.info(f"Generated wallet_id for user {passkey.user_id}")
        finally:
            db.close()
        
        # Issue lemma with EMBEDDED passkey proof
        lemma_with_proof = issue_lemma_with_passkey_proof(
            user_id=passkey.user_id,
            user_email=user_email,
            user_role=user_role,
            passkey_credential=credential,
            passkey_public_key=passkey.public_key,
            challenge=stored['challenge'],
        )
        
        # Set session
        session['customer_id'] = passkey.user_id
        session['user_email'] = user_email
        session['auth_method'] = 'passkey'
        session['passkey_verified'] = True
        session['wallet_id'] = wallet_id  # Store for global session sync
        
        logger.info(f"✅ Passkey authentication successful for {user_email}")
        
        # Create a server-verified wallet session cookie for cross-device SSO
        unlock_token = None
        session_token = None
        csrf_token = None
        expires_at = None
        unlocked_at_ms = int(datetime.utcnow().timestamp() * 1000)
        try:
            from auth.session_manager import (
                generate_session_token,
                generate_unlock_token,
                generate_csrf_token,
                SESSION_COOKIE_NAME,
                CSRF_COOKIE_NAME,
                get_session_expiry,
            )
            from api.wallet_session_sync import _store_global_session
            csrf_token = generate_csrf_token()
            session_token = generate_session_token(wallet_id, unlocked_at_ms)
            expires_at = get_session_expiry()
            global_stored = _store_global_session(
                wallet_id=wallet_id,
                unlocked_at=unlocked_at_ms,
                expires_at=expires_at,
                profile_id='default',
                profile_name='Personal'
            )
            logger.info(f"🔐 Global session stored={global_stored} for wallet {wallet_id[:8]}...")
            unlock_token = generate_unlock_token(
                wallet_id=wallet_id,
                unlocked_at=unlocked_at_ms,
                expires_at=expires_at
            )
        except Exception as e:
            logger.warning(f"Failed to set wallet session cookie: {e}")
        
        response = make_response(jsonify({
            'success': True,
            'user_id': passkey.user_id,
            'user_email': user_email,
            'auth_method': 'passkey',
            'wallet_id': wallet_id,  # Include for cross-device sync
            'lemma': lemma_with_proof,
            'wallet_session': {
                'unlocked_at': unlocked_at_ms,
                'expires_at': expires_at
            },
            'unlock_token': unlock_token,
            'message': 'Authentication successful'
        }))
        
        if session_token:
            response.set_cookie(
                SESSION_COOKIE_NAME,
                session_token,
                max_age=SESSION_DURATION,
                httponly=True,
                secure=True,
                samesite='None',
                path='/'
            )
        if csrf_token:
            response.set_cookie(
                CSRF_COOKIE_NAME,
                csrf_token,
                max_age=SESSION_DURATION,
                httponly=False,
                secure=True,
                samesite='None',
                path='/'
            )
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Passkey authentication complete failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# LEMMA ISSUANCE WITH EMBEDDED PASSKEY PROOF
# ============================================

def issue_lemma_with_passkey_proof(user_id: str, user_email: str, user_role: str,
                                    passkey_credential: dict, passkey_public_key: str,
                                    challenge: str) -> dict:
    """
    Issue a lemma that contains embedded passkey proof for local verification
    """
    import time
    
    try:
        from lemma_crypto import PyMinimalIssuer
        from api.issuer_management import get_issuer_manager
        
        issuer_manager = get_issuer_manager()
        iam_issuer = issuer_manager.get_iam_issuer('lemma.id')
        
        current_time = int(time.time())
        
        # Extract passkey proof components
        response = passkey_credential.get('response', {})
        
        passkey_proof = {
            'challenge': challenge,
            'authenticatorData': response.get('authenticatorData'),
            'clientDataJSON': response.get('clientDataJSON'),
            'signature': response.get('signature'),
            'publicKey': passkey_public_key,
            # Optional: userHandle for discoverable credentials
            'userHandle': response.get('userHandle'),
        }
        
        # Build claims with passkey proof
        claims = {
            'packageType': 'permission',
            'siteId': 'lemma.id',
            'permissionId': f'{user_role}_access',
            'accountType': user_role,
            'email': user_email,
            'authMethod': 'passkey',
            'passkeyVerified': 'true',
            'networkShared': 'false',
            'grantedAt': str(current_time),
            'scope': ','.join(['users:*', 'sites:*', 'permissions:*', 'billing:*'] 
                             if user_role == 'admin' 
                             else ['profile:read', 'profile:write']),
        }
        
        # Generate user DID
        customer_did = issuer_manager.generate_deterministic_user_did(f"customer_{user_id}")
        
        # Issue the lemma
        lemma_json = iam_issuer.issue_credential(customer_did, claims)
        lemma_data = json.loads(lemma_json)
        
        # Embed the passkey proof in the lemma
        lemma_data['passkeyProof'] = passkey_proof
        
        # Add issuer info for wallet caching (federated architecture)
        lemma_data['issuerInfo'] = {
            'did': iam_issuer.get_did(),
            'publicKey': iam_issuer.get_public_key_hex(),
            'name': 'Lemma IAM',
            'verified': True
        }
        
        logger.info(f"✅ Lemma with passkey proof issued: {lemma_data['id']}")
        
        return lemma_data
        
    except Exception as e:
        logger.error(f"❌ Failed to issue lemma with passkey proof: {e}")
        # Fail closed: never emit fallback auth artifacts when issuance fails.
        raise RuntimeError("lemma_issuance_failed") from e


# ============================================
# PASSKEY MANAGEMENT ENDPOINTS
# ============================================

@passkey_bp.route('/api/passkey/list', methods=['GET'])
@cross_origin()
def list_passkeys():
    """List all passkeys for the current user"""
    user_id = session.get('customer_id')
    
    if not user_id:
        return jsonify({
            'success': False,
            'error': 'Not authenticated'
        }), 401
    
    passkeys = get_user_passkeys(user_id)
    
    return jsonify({
        'success': True,
        'passkeys': [
            {
                'id': pk.id,
                'device_name': pk.device_name,
                'authenticator_type': pk.authenticator_type,
                'created_at': pk.created_at.isoformat() if pk.created_at else None,
                'last_used_at': pk.last_used_at.isoformat() if pk.last_used_at else None,
            }
            for pk in passkeys
        ]
    })


@passkey_bp.route('/api/passkey/<int:passkey_id>', methods=['DELETE'])
@cross_origin()
def delete_passkey(passkey_id):
    """
    Delete a passkey and revoke all associated credentials.
    
    SECURITY: When a passkey is deleted (device lost/stolen), we must:
    1. Deactivate the passkey
    2. Revoke ALL credentials for this user's wallet (all sites, all devices)
    
    This ensures attackers can't use cached credentials after device compromise.
    """
    user_id = session.get('customer_id')
    
    if not user_id:
        return jsonify({
            'success': False,
            'error': 'Not authenticated'
        }), 401
    
    db = get_db()
    try:
        passkey = db.query(Passkey).filter(
            Passkey.id == passkey_id,
            Passkey.user_id == user_id
        ).first()
        
        if not passkey:
            return jsonify({
                'success': False,
                'error': 'Passkey not found'
            }), 404
        
        # Get wallet_id for credential revocation
        customer = db.query(Customer).filter(Customer.id == user_id).first()
        wallet_id = customer.wallet_id if customer else None
        
        # Deactivate the passkey
        passkey.is_active = False
        
        # SECURITY: Revoke ALL credentials associated with this wallet
        # This prevents attackers from using cached credentials after device compromise
        revocation_count = 0
        if wallet_id:
            try:
                from api.database import RevocationList
                from datetime import datetime
                
                # Add wallet-level revocation (all sites, all devices)
                existing = db.query(RevocationList).filter(
                    RevocationList.credential_id == f"wallet:{wallet_id}"
                ).first()
                
                if not existing:
                    revocation = RevocationList(
                        lemma_id=f"wallet:{wallet_id}",
                        credential_id=f"wallet:{wallet_id}",
                        wallet_id=wallet_id,
                        revocation_type='wallet',  # Wallet-level revocation
                        reason=f'passkey_deleted:{passkey_id}',
                        revoked_at=datetime.utcnow(),
                        revoked_by=f'user:{user_id}'
                    )
                    db.add(revocation)
                    revocation_count = 1
                    logger.info(f"🔐 SECURITY: Wallet {wallet_id[:12]}... revoked due to passkey deletion")
                    
            except Exception as e:
                logger.error(f"Failed to revoke wallet credentials: {e}")
                # Continue with passkey deletion even if revocation fails
        
        db.commit()
        
        # Audit log
        try:
            from api.audit_logger import log_event, AuditEvent
            log_event(
                AuditEvent.CREDENTIAL_REVOKED,
                details={
                    'passkey_id': passkey_id,
                    'wallet_id': wallet_id,
                    'revocation_type': 'passkey_deleted',
                    'credentials_revoked': revocation_count
                },
                user_id=user_id
            )
        except Exception:
            pass
        
        logger.info(f"🗑️ Passkey {passkey_id} deleted for user {user_id}, {revocation_count} credential(s) revoked")
        
        return jsonify({
            'success': True,
            'message': 'Passkey deleted and credentials revoked',
            'credentials_revoked': revocation_count
        })
        
    finally:
        db.close()


# ============================================
# WALLET-BASED AUTH (replaces email sessions)
# ============================================

@passkey_bp.route('/api/wallet/auth', methods=['POST', 'OPTIONS'])
@secure_cors
@rate_limit(auth_limit)
def wallet_auth():
    """
    SECURE wallet authentication via WebAuthn assertion.
    
    SECURITY: This endpoint requires a REAL WebAuthn authentication assertion
    that is verified server-side against the stored public key. The client
    cannot forge this - it requires physical possession of the authenticator.
    
    Flow:
    1. Client calls /api/passkey/authenticate/begin to get a challenge
    2. Client performs navigator.credentials.get() with the challenge
    3. Client sends the assertion here for verification
    4. Server verifies signature against stored public key
    5. Only on success, session is granted
    
    POST /api/wallet/auth
    {
        "wallet_id": "wallet_abc123",
        "challenge_key": "passkey_auth_xxx",  // From authenticate/begin
        "credential": {
            "id": "base64url...",
            "rawId": "base64url...",
            "response": {
                "authenticatorData": "base64url...",
                "clientDataJSON": "base64url...",
                "signature": "base64url..."
            },
            "type": "public-key"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body required'
            }), 400
        
        wallet_id = data.get('wallet_id')
        challenge_key = data.get('challenge_key')
        credential = data.get('credential')
        
        # SECURITY: Require all fields
        if not wallet_id:
            return jsonify({
                'success': False,
                'error': 'wallet_id is required'
            }), 400
            
        if not challenge_key:
            return jsonify({
                'success': False,
                'error': 'challenge_key is required - call /api/passkey/authenticate/begin first'
            }), 400
            
        if not credential:
            return jsonify({
                'success': False,
                'error': 'WebAuthn credential assertion is required'
            }), 400
        
        # SECURITY: Validate challenge exists and hasn't expired (thread-safe)
        challenge_data = get_challenge(challenge_key)
        if not challenge_data:
            logger.warning(f"🚫 SECURITY: Invalid challenge_key attempted: {challenge_key}")
            return jsonify({
                'success': False,
                'error': 'Invalid or expired challenge - call /api/passkey/authenticate/begin first'
            }), 401

        # SECURITY: Check challenge expiration
        expires_str = challenge_data.get('expires')
        if expires_str:
            expires = datetime.fromisoformat(expires_str)
            if datetime.utcnow() > expires:
                # Clean up expired challenge
                delete_challenge(challenge_key)
                logger.warning(f"🚫 SECURITY: Expired challenge attempted: {challenge_key}")
                return jsonify({
                    'success': False,
                    'error': 'Challenge expired - call /api/passkey/authenticate/begin for a new one'
                }), 401
        
        # Get credential_id from the assertion
        credential_id_b64 = credential.get('id')
        if not credential_id_b64:
            return jsonify({
                'success': False,
                'error': 'credential.id is required'
            }), 400
        
        # SECURITY: Look up the passkey to get the public key for verification
        db = get_db()
        try:
            passkey = db.query(Passkey).filter(
                Passkey.credential_id == credential_id_b64,
                Passkey.is_active == True
            ).first()
            
            if not passkey:
                logger.warning(f"🚫 SECURITY: Unknown passkey in wallet auth: {credential_id_b64[:20]}...")
                return jsonify({
                    'success': False,
                    'error': 'Unknown or inactive passkey'
                }), 401
            
            # SECURITY: Verify the WebAuthn assertion server-side
            try:
                verification = verify_authentication_response(
                    credential=AuthenticationCredential.parse_raw(json.dumps(credential)),
                    expected_challenge=base64.urlsafe_b64decode(challenge_data['challenge']),
                    expected_rp_id=RP_ID,
                    expected_origin=EXPECTED_ORIGIN,
                    credential_public_key=base64.urlsafe_b64decode(passkey.public_key),
                    credential_current_sign_count=passkey.sign_count or 0,
                    require_user_verification=True,  # SECURITY: Require UV
                )
                
                # Update sign count to prevent replay attacks
                passkey.sign_count = verification.new_sign_count
                passkey.last_used_at = datetime.utcnow()
                
            except Exception as e:
                logger.warning(f"🚫 SECURITY: WebAuthn verification failed: {e}")
                return jsonify({
                    'success': False,
                    'error': 'WebAuthn assertion verification failed'
                }), 401
            
            # SECURITY: Delete used challenge to prevent replay (thread-safe)
            delete_challenge(challenge_key)

            # Get user info
            user_id = passkey.user_id
            
            # Store wallet_id with customer
            customer = db.query(Customer).filter(Customer.id == user_id).first()
            if customer:
                customer.wallet_id = wallet_id
            
            db.commit()
            
            # Set session (cryptographically verified)
            session['customer_id'] = user_id
            session['auth_method'] = 'wallet_passkey_verified'
            session['wallet_id'] = wallet_id
            session['passkey_verified'] = True
            
            # Set global wallet session for cross-device sync
            try:
                from auth.session_manager import get_session_expiry, get_current_time_ms
                from api.wallet_session_sync import _store_global_session
                unlocked_at_ms = get_current_time_ms()
                expires_at = get_session_expiry()
                _store_global_session(
                    wallet_id=wallet_id,
                    unlocked_at=unlocked_at_ms,
                    expires_at=expires_at,
                    profile_id='default',
                    profile_name='Personal'
                )
            except Exception as e:
                logger.warning(f"Could not set global wallet session: {e}")
            
            logger.info(f"✅ VERIFIED wallet auth for user {user_id}")
            
            return jsonify({
                'success': True,
                'authenticated': True,
                'verified': True,
                'user_id': user_id,
                'auth_method': 'wallet_passkey_verified',
                'wallet_id': wallet_id,
                'message': 'Authenticated via cryptographically verified WebAuthn assertion'
            })
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Wallet auth error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@passkey_bp.route('/api/wallet/status', methods=['GET'])
@cross_origin()
def wallet_status():
    """
    Check current wallet auth status from server perspective
    
    GET /api/wallet/status
    """
    wallet_id = session.get('wallet_id')
    auth_method = session.get('auth_method')
    
    if not wallet_id or not auth_method:
        return jsonify({
            'success': True,
            'authenticated': False,
            'reason': 'No wallet session'
        })
    
    return jsonify({
        'success': True,
        'authenticated': True,
        'wallet_id': wallet_id,
        'auth_method': auth_method,
        'user_id': session.get('customer_id')
    })
