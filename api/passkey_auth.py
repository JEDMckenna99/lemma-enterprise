"""
Passkey (WebAuthn) Authentication for Lemma
Enables hardware-backed authentication with embedded proofs in lemmas
"""

import os
import json
import base64
import secrets
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
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
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from .database import get_db, Passkey, Customer

logger = logging.getLogger(__name__)

passkey_bp = Blueprint('passkey', __name__)

# Configuration
RP_ID = os.getenv('PASSKEY_RP_ID', 'lemma.id')
RP_NAME = os.getenv('PASSKEY_RP_NAME', 'Lemma')
ORIGIN = os.getenv('PASSKEY_ORIGIN', 'https://lemma.id')

# Challenge storage (use Redis in production)
_challenges = {}  # In-memory for now, move to Redis


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

@passkey_bp.route('/api/passkey/register/begin', methods=['POST'])
@cross_origin()
def passkey_register_begin():
    """
    Begin passkey registration - returns options for navigator.credentials.create()
    
    POST /api/passkey/register/begin
    {
        "user_id": "customer_abc123",
        "user_email": "user@example.com",
        "device_name": "My iPhone"  // optional
    }
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id') or session.get('customer_id')
        user_email = data.get('user_email') or session.get('user_email')
        device_name = data.get('device_name', 'Passkey')
        
        if not user_id or not user_email:
            return jsonify({
                'success': False,
                'error': 'user_id and user_email are required'
            }), 400
        
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
        
        # Store challenge for verification
        challenge_key = f"passkey_reg_{user_id}"
        _challenges[challenge_key] = {
            'challenge': base64.urlsafe_b64encode(options.challenge).decode('utf-8'),
            'user_id': user_id,
            'user_email': user_email,
            'device_name': device_name,
            'expires': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        }
        
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


@passkey_bp.route('/api/passkey/register/complete', methods=['POST'])
@cross_origin()
def passkey_register_complete():
    """
    Complete passkey registration - verify and store the credential
    
    POST /api/passkey/register/complete
    {
        "user_id": "customer_abc123",
        "credential": { ... WebAuthn credential response ... }
    }
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id') or session.get('customer_id')
        credential = data.get('credential')
        
        if not user_id or not credential:
            return jsonify({
                'success': False,
                'error': 'user_id and credential are required'
            }), 400
        
        # Retrieve stored challenge
        challenge_key = f"passkey_reg_{user_id}"
        stored = _challenges.get(challenge_key)
        
        if not stored:
            return jsonify({
                'success': False,
                'error': 'Registration session expired'
            }), 400
        
        # Verify the registration
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64.urlsafe_b64decode(stored['challenge']),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_user_verification=False,  # Be lenient for wider device support
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
        
        # Clean up challenge
        del _challenges[challenge_key]
        
        logger.info(f"✅ Passkey registered for {stored['user_email']}")
        
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
                'algorithm': -7  # ES256, TODO: detect actual algorithm
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

@passkey_bp.route('/api/passkey/authenticate/begin', methods=['POST'])
@cross_origin()
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
        
        # Store challenge
        challenge_b64 = base64.urlsafe_b64encode(options.challenge).decode('utf-8')
        challenge_key = f"passkey_auth_{challenge_b64[:16]}"
        _challenges[challenge_key] = {
            'challenge': challenge_b64,
            'user_id': user_id,
            'expires': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        }
        
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


@passkey_bp.route('/api/passkey/authenticate/complete', methods=['POST'])
@cross_origin()
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
        passkey = get_passkey_by_credential_id(credential_id_b64)
        
        if not passkey:
            return jsonify({
                'success': False,
                'error': 'Passkey not found'
            }), 401
        
        # Retrieve stored challenge
        stored = _challenges.get(challenge_key)
        if not stored:
            return jsonify({
                'success': False,
                'error': 'Authentication session expired'
            }), 400
        
        # Verify the authentication
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64.urlsafe_b64decode(stored['challenge']),
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64.urlsafe_b64decode(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=False,
        )
        
        # Update sign count
        update_passkey_sign_count(passkey.id, verification.new_sign_count)
        
        # Clean up challenge
        del _challenges[challenge_key]
        
        # Get user info
        db = get_db()
        try:
            customer = db.query(Customer).filter(
                Customer.customer_id == passkey.user_id
            ).first()
            user_email = customer.email if customer else None
            user_role = customer.role if customer else 'user'
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
        
        logger.info(f"✅ Passkey authentication successful for {user_email}")
        
        return jsonify({
            'success': True,
            'user_id': passkey.user_id,
            'user_email': user_email,
            'auth_method': 'passkey',
            'lemma': lemma_with_proof,
            'message': 'Authentication successful'
        })
        
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
        
        logger.info(f"✅ Lemma with passkey proof issued: {lemma_data['id']}")
        
        return lemma_data
        
    except Exception as e:
        logger.error(f"❌ Failed to issue lemma with passkey proof: {e}")
        # Return basic lemma without proof on error
        return {
            'id': f"lemma_{secrets.token_hex(8)}",
            'claims': {
                'authMethod': 'passkey',
                'passkeyVerified': 'true',
            },
            'error': 'Full lemma issuance failed, basic proof returned'
        }


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
    """Delete a passkey"""
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
        
        passkey.is_active = False
        db.commit()
        
        logger.info(f"🗑️ Passkey {passkey_id} deleted for user {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Passkey deleted'
        })
        
    finally:
        db.close()
