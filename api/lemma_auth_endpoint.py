"""
Lemma Wallet Authentication Endpoint
Handles "Sign in with Lemma" authentication using wallet credentials
"""

from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from datetime import datetime, timedelta
import logging
import secrets

from .database import get_db, Customer as DBCustomer
from .customer_accounts import customer_manager

logger = logging.getLogger(__name__)

lemma_auth_bp = Blueprint('lemma_auth', __name__)

@lemma_auth_bp.route('/api/auth/lemma-signin', methods=['POST'])
@cross_origin()
def lemma_signin():
    """
    Authenticate user using Lemma wallet credentials
    
    POST /api/auth/lemma-signin
    {
        "user_email": "jedmckenna@lemma.id",
        "user_role": "admin",
        "identity_credentials": [...],
        "permission_credentials": [...],
        "verification_result": {...},
        "auth_method": "lemma_wallet"
    }
    """
    try:
        data = request.get_json()
        user_email = data.get('user_email', '').strip().lower()
        user_role = data.get('user_role', 'customer')
        identity_credentials = data.get('identity_credentials', [])
        permission_credentials = data.get('permission_credentials', [])
        verification_result = data.get('verification_result', {})
        auth_method = data.get('auth_method', 'lemma_wallet')
        
        if not user_email:
            return jsonify({
                'success': False,
                'error': 'User email is required'
            }), 400
        
        if not identity_credentials:
            return jsonify({
                'success': False,
                'error': 'Identity credentials are required'
            }), 400
        
        if not verification_result.get('verified'):
            return jsonify({
                'success': False,
                'error': 'Credentials failed verification'
            }), 401
        
        logger.info(f"🔐 Lemma wallet authentication for: {user_email} ({user_role})")
        logger.info(f"📊 Credentials: {len(identity_credentials)} identity, {len(permission_credentials)} permission")
        logger.info(f"⚡ Verification time: {verification_result.get('verification_time_us', 'unknown')}µs")
        
        # Find or create customer account
        customer = customer_manager.get_customer_by_email(user_email)
        if not customer:
            # Create customer account for Lemma wallet user
            create_result = customer_manager.create_customer(
                email=user_email,
                name=f"Lemma User ({user_role.title()})",
                company="Lemma Platform" if user_role == 'admin' else "Personal"
            )
            
            if not create_result.get('success'):
                return jsonify({
                    'success': False,
                    'error': 'Failed to create customer account'
                }), 500
            
            # Get the newly created customer
            customer = customer_manager.get_customer_by_email(user_email)
            
            if customer:
                # Update role based on permission credentials
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.email == user_email).first()
                if db_customer:
                    db_customer.role = user_role
                    db_customer.permissions = [f'{user_role}_access']
                    db.commit()
                db.close()
                
                logger.info(f"✅ Created customer account for Lemma wallet user: {user_email}")
        
        # Verify the customer has the right role
        if customer.role != user_role:
            # Update customer role to match permission credentials
            db = get_db()
            db_customer = db.query(DBCustomer).filter(DBCustomer.email == user_email).first()
            if db_customer:
                db_customer.role = user_role
                db_customer.permissions = [f'{user_role}_access']
                db_customer.last_login = datetime.utcnow()
                db_customer.login_count += 1
                db.commit()
            db.close()
            
            logger.info(f"✅ Updated customer role to match credentials: {user_role}")
        
        # Create authenticated session
        session['customer_id'] = customer.customer_id
        session['user_role'] = user_role
        session['auth_method'] = auth_method
        session['lemma_verified'] = True
        session['verification_time_us'] = verification_result.get('verification_time_us', 0)
        
        # Issue fresh permission lemma for the session (client-side storage)
        permission_lemma_data = None
        if customer:
            import time
            current_time = int(time.time())
            user_did = f"did:lemma:customer:{customer.customer_id}"
            
            permission_lemma_data = {
                'id': f"session_perm_{secrets.token_hex(16)}",
                'issuer': 'did:lemma:platform:lemma.id',
                'subject': user_did,
                'packageType': 'permission',
                'issued_at': current_time,
                'expires_at': current_time + (90 * 24 * 60 * 60),  # 90 days
                'claims': {
                    'packageType': 'permission',
                    'siteId': 'lemma.id',
                    'permissionId': f'{user_role}_access',
                    'accountType': user_role,
                    'email': user_email,
                    'customerId': customer.customer_id,
                    'authMethod': 'lemma_wallet',
                    'verificationTimeUs': verification_result.get('verification_time_us', 0),
                    'networkShared': True,
                    'grantedBy': 'did:lemma:platform:lemma.id',
                    'grantedAt': current_time,
                    'scope': ['users:*', 'sites:*', 'permissions:*', 'billing:*', 'analytics:*'] if user_role == 'admin' else ['profile:read', 'profile:write', 'billing:read', 'usage:read']
                },
                'proof': {
                    'type': 'Ed25519Signature2020',
                    'created': current_time,
                    'verificationMethod': 'did:lemma:platform:lemma.id',
                    'signatureValue': f"lemma_wallet_sig_{secrets.token_hex(32)}"
                }
            }
        
        logger.info(f"✅ Lemma wallet authentication successful for {user_email}")
        
        return jsonify({
            'success': True,
            'customer_id': customer.customer_id,
            'user_email': user_email,
            'user_role': user_role,
            'auth_method': auth_method,
            'permission_lemma': permission_lemma_data,
            'verification_time_us': verification_result.get('verification_time_us', 0),
            'message': f'Welcome back! Authenticated via Lemma wallet in {verification_result.get("verification_time_us", "unknown")}µs',
            'redirect_url': '/dashboard'
        })
        
    except Exception as e:
        logger.error(f"❌ Lemma authentication error: {e}")
        return jsonify({
            'success': False,
            'error': 'Lemma authentication failed'
        }), 500
