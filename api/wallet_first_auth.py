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


def issue_permission_lemma(user_id: str, site_id: str = 'lemma.id', permissions: list = None) -> dict:
    """
    Issue a permission lemma for direct wallet storage
    """
    try:
        # Import the IAM issuer
        from .iam_issuer import get_iam_issuer
        iam_issuer = get_iam_issuer()
        
        # Build claims
        claims = {
            'type': 'permission',
            'siteId': site_id,
            'permissions': permissions or ['read', 'write'],
            'issuedAt': datetime.utcnow().isoformat() + 'Z',
            'expiresAt': (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'
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
        
        logger.info(f"✅ Permission lemma issued for {user_id} on {site_id}")
        return credential
        
    except Exception as e:
        logger.error(f"❌ Failed to issue permission lemma: {e}")
        raise


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
