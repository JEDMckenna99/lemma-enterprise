"""
Federated Site API - Enables both Managed and Self-Service models

TWO SERVICE TIERS:
1. Managed Service: Lemma generates keys, issues credentials, stores users
2. Self-Service: Site generates keys, issues credentials, manages own users

Both tiers support:
- Local wallet storage
- Local verification
- Cross-site credential sharing
"""

import os
import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin

from .database import get_db, Site
from .issuer_registry import IssuerRecord, init_issuer_registry_table

logger = logging.getLogger(__name__)

federated_site_bp = Blueprint('federated_site', __name__)


# ============================================
# SITE REGISTRATION (Choose Your Model)
# ============================================

@federated_site_bp.route('/api/v1/sites/register/managed', methods=['POST'])
@cross_origin()
def register_managed_site():
    """
    Register a site for MANAGED service (Lemma handles everything)
    
    - Lemma generates site-specific keypair (KMS-backed)
    - Lemma stores site's users
    - Lemma issues credentials via API
    - Site pays per-user fees
    
    POST /api/v1/sites/register/managed
    {
        "site_domain": "customer.com",
        "company_name": "Customer Inc",
        "admin_email": "admin@customer.com",
        "plan": "starter|professional|enterprise"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['site_domain', 'company_name', 'admin_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Import the existing registration flow
        from .real_iam_manager import get_or_create_site_manager
        from .database import SessionLocal
        import secrets
        
        site_id = f"site_{secrets.token_hex(8)}"
        site_domain = data['site_domain']
        
        # Create site-specific IAM manager (KMS-backed)
        manager = get_or_create_site_manager(site_id, site_domain)
        
        # Register in issuer registry for cross-site verification
        db = get_db()
        try:
            issuer_record = IssuerRecord(
                issuer_did=manager.issuer_did,
                domain=site_domain,
                public_key=manager.get_public_key_hex() if hasattr(manager, 'get_public_key_hex') else manager.issuer.get_public_key_hex(),
                name=data['company_name'],
                description=f"Managed site: {site_domain}",
                verified=True,  # Managed sites are auto-verified
                verification_method='managed_service'
            )
            db.add(issuer_record)
            db.commit()
        except Exception as e:
            logger.warning(f"Could not add to issuer registry: {e}")
        finally:
            db.close()
        
        logger.info(f"✅ Registered managed site: {site_domain}")
        
        return jsonify({
            'success': True,
            'service_type': 'managed',
            'site_id': site_id,
            'issuer_did': manager.issuer_did,
            'features': {
                'key_management': 'lemma_kms',
                'user_storage': 'lemma_database',
                'credential_issuance': 'lemma_api',
                'billing': 'per_user'
            },
            'api_endpoints': {
                'create_permission': f'/api/v1/sites/{site_id}/permissions',
                'grant_permission': f'/api/v1/sites/{site_id}/users/{{user_did}}/permissions',
                'verify_permission': f'/api/v1/sites/{site_id}/verify',
                'list_users': f'/api/v1/sites/{site_id}/users'
            },
            'wallet_support': True,
            'local_verification': True
        }), 201
        
    except Exception as e:
        logger.error(f"Managed site registration error: {e}")
        return jsonify({'error': str(e)}), 500


@federated_site_bp.route('/api/v1/sites/register/self-service', methods=['POST'])
@cross_origin()
def register_self_service_site():
    """
    Register a site for SELF-SERVICE (Site handles own keys and users)
    
    - Site generates keypair in browser (via LemmaSiteIssuer SDK)
    - Site manages own user database
    - Site issues credentials via browser SDK
    - Site pays only for PoH verifications
    
    POST /api/v1/sites/register/self-service
    {
        "site_domain": "customer.com",
        "company_name": "Customer Inc",
        "admin_email": "admin@customer.com",
        "public_key": "base64url-encoded-ed25519-public-key"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['site_domain', 'company_name', 'public_key']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        site_domain = data['site_domain']
        issuer_did = f"did:web:{site_domain}"
        
        # Register in issuer registry
        import secrets
        verification_token = secrets.token_urlsafe(32)
        
        db = get_db()
        try:
            # Check if already registered
            existing = db.query(IssuerRecord).filter(
                IssuerRecord.domain == site_domain
            ).first()
            
            if existing:
                existing.public_key = data['public_key']
                existing.name = data['company_name']
                existing.updated_at = datetime.utcnow()
                existing.verification_token = verification_token
                db.commit()
                
                return jsonify({
                    'success': True,
                    'service_type': 'self_service',
                    'updated': True,
                    'issuer_did': existing.issuer_did,
                    'verification_token': verification_token,
                    'verification_required': not existing.verified
                })
            
            # Create new issuer record
            issuer_record = IssuerRecord(
                issuer_did=issuer_did,
                domain=site_domain,
                public_key=data['public_key'],
                name=data['company_name'],
                description=data.get('description', f"Self-service site: {site_domain}"),
                verified=False,  # Requires domain verification
                verification_token=verification_token,
                verification_method='pending'
            )
            db.add(issuer_record)
            db.commit()
            
            logger.info(f"✅ Registered self-service site: {site_domain}")
            
            return jsonify({
                'success': True,
                'service_type': 'self_service',
                'issuer_did': issuer_did,
                'features': {
                    'key_management': 'site_controlled',
                    'user_storage': 'site_controlled',
                    'credential_issuance': 'browser_sdk',
                    'billing': 'poh_only'
                },
                'sdk_usage': {
                    'issuer_sdk': 'https://lemma.id/js/lemma-issuer.js',
                    'wallet_sdk': 'https://lemma.id/js/lemma-wallet.js',
                    'example': '''
// Generate keypair (browser)
const issuer = new LemmaSiteIssuer({ domain: "your-site.com" });
await issuer.init();

// Issue credential to user
const lemma = await issuer.issueLemma(userId, {
    role: "admin",
    permissions: ["users:*"]
});

// User stores in wallet
await LemmaWallet.storeLemma(lemma, issuer.getPublicKeyInfo());
'''
                },
                'verification_required': True,
                'verification_token': verification_token,
                'verification_instructions': {
                    'well_known': {
                        'url': f'https://{site_domain}/.well-known/lemma-verification.txt',
                        'content': verification_token
                    },
                    'dns': {
                        'record': f'_lemma-verification.{site_domain}',
                        'type': 'TXT',
                        'value': verification_token
                    }
                }
            }), 201
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Self-service site registration error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# MANAGED SERVICE: User Management
# ============================================

@federated_site_bp.route('/api/v1/managed/<site_id>/users', methods=['POST'])
@cross_origin()
def managed_create_user(site_id):
    """
    Create a user for a managed site (Lemma stores user)
    
    POST /api/v1/managed/{site_id}/users
    {
        "user_email": "user@example.com",
        "display_name": "John Doe",
        "initial_roles": ["member"]
    }
    """
    try:
        data = request.get_json()
        
        # TODO: Implement user storage in Lemma's database
        # This already exists in your current system
        
        # Generate user DID
        from .issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        user_did = issuer_manager.generate_deterministic_user_did(
            f"{site_id}:{data['user_email']}"
        )
        
        # Issue initial credentials
        from .real_iam_manager import get_site_manager
        manager = get_site_manager(site_id)
        
        credentials = []
        for role in data.get('initial_roles', []):
            cred = manager.issue_permission_lemma(
                user_did,
                role,
                expiry_days=data.get('expiry_days', 365)
            )
            credentials.append(cred)
        
        return jsonify({
            'success': True,
            'user_did': user_did,
            'credentials': credentials,
            'wallet_instructions': 'Send credentials to user to store in their wallet'
        }), 201
        
    except Exception as e:
        logger.error(f"Managed user creation error: {e}")
        return jsonify({'error': str(e)}), 500


@federated_site_bp.route('/api/v1/managed/<site_id>/users/<user_did>/credentials', methods=['POST'])
@cross_origin()
def managed_issue_credential(site_id, user_did):
    """
    Issue a credential for a managed site user
    
    POST /api/v1/managed/{site_id}/users/{user_did}/credentials
    {
        "role": "admin",
        "permissions": ["users:*", "billing:*"],
        "expiry_days": 30
    }
    """
    try:
        data = request.get_json()
        
        from .real_iam_manager import get_site_manager
        manager = get_site_manager(site_id)
        
        if not manager:
            return jsonify({'error': 'Site not found'}), 404
        
        # Issue credential
        credential = manager.issue_permission_lemma(
            user_did,
            data.get('role', 'member'),
            expiry_days=data.get('expiry_days', 90),
            custom_claims={
                'permissions': data.get('permissions', []),
                **data.get('custom_claims', {})
            }
        )
        
        # Add issuer info for wallet storage
        credential['issuerInfo'] = {
            'did': manager.issuer_did,
            'publicKey': manager.issuer.get_public_key_hex(),
            'name': f"Managed Site: {site_id}",
            'verified': True
        }
        
        return jsonify({
            'success': True,
            'credential': credential,
            'wallet_storage': {
                'lemma': credential,
                'issuerInfo': credential['issuerInfo']
            }
        })
        
    except Exception as e:
        logger.error(f"Managed credential issuance error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# SELF-SERVICE: PoH Request
# ============================================

@federated_site_bp.route('/api/v1/self-service/poh/request', methods=['POST'])
@cross_origin()
def request_poh_for_user():
    """
    Request Proof-of-Human verification for a user
    (Self-service sites pay only for PoH, not user management)
    
    POST /api/v1/self-service/poh/request
    {
        "site_domain": "customer.com",
        "user_identifier": "user@example.com",
        "callback_url": "https://customer.com/poh/callback"
    }
    """
    try:
        data = request.get_json()
        
        # Generate PoH verification session
        import secrets
        session_id = f"poh_{secrets.token_hex(16)}"
        
        # TODO: Create Stripe Identity session for PoH
        # This integrates with your existing PoH flow
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'verification_url': f"https://lemma.id/verify/human/{session_id}",
            'callback_url': data.get('callback_url'),
            'cost': '$1.50',
            'result_format': {
                'type': 'lemma',
                'claims': {
                    'isHuman': True,
                    'verifiedAt': 'timestamp',
                    'verificationMethod': 'stripe_identity'
                }
            }
        })
        
    except Exception as e:
        logger.error(f"PoH request error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# SERVICE COMPARISON
# ============================================

@federated_site_bp.route('/api/v1/service-comparison', methods=['GET'])
@cross_origin()
def service_comparison():
    """
    Compare Managed vs Self-Service offerings
    
    GET /api/v1/service-comparison
    """
    return jsonify({
        'managed_service': {
            'name': 'Managed Service',
            'description': 'Lemma handles everything - keys, users, credentials',
            'best_for': 'Sites that want minimal setup',
            'features': {
                'key_management': '✅ Lemma generates KMS-backed keys',
                'user_storage': '✅ Lemma stores user data',
                'credential_issuance': '✅ Via Lemma API',
                'dashboard': '✅ Full user management UI',
                'analytics': '✅ Usage and permission analytics'
            },
            'pricing': {
                'model': 'Per active user per month',
                'starter': '$0.10/MAU',
                'professional': '$0.05/MAU',
                'enterprise': 'Contact us'
            },
            'setup': {
                'time': '5 minutes',
                'steps': [
                    'Register site',
                    'Get API key',
                    'Create permissions',
                    'Grant to users'
                ]
            }
        },
        'self_service': {
            'name': 'Self-Service (Federated)',
            'description': 'You control keys and users - pay only for PoH',
            'best_for': 'Sites with existing user databases',
            'features': {
                'key_management': '🔑 You generate in browser',
                'user_storage': '🔑 Your own database',
                'credential_issuance': '🔑 Via browser SDK',
                'dashboard': '❌ Not included',
                'analytics': '❌ Not included'
            },
            'pricing': {
                'model': 'Per Proof-of-Human verification only',
                'poh_verification': '$1.50/verification',
                'credential_issuance': '$0 (your infrastructure)',
                'verification': '$0 (local)'
            },
            'setup': {
                'time': '30 minutes',
                'steps': [
                    'Include SDK in your site',
                    'Generate keypair',
                    'Register public key with Lemma',
                    'Verify domain ownership',
                    'Issue credentials from your backend/frontend'
                ]
            }
        },
        'shared_features': {
            'wallet_storage': '✅ Users store credentials in wallet',
            'local_verification': '✅ ~1ms verification time',
            'cross_site_trust': '✅ Via issuer registry',
            'revocation': '✅ Network-wide revocation',
            'poh_network': '✅ Shared defense network'
        }
    })
