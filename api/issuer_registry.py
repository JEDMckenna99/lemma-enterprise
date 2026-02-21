"""
Issuer Registry API
Allows sites to register as trusted issuers and share public keys
for cross-site lemma verification.
"""

import os
import json
import hashlib
import secrets
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from auth.decorators import require_api_key

from .database import get_db, Base, engine

logger = logging.getLogger(__name__)

issuer_registry_bp = Blueprint('issuer_registry', __name__)


# ============================================
# DATABASE MODEL
# ============================================

class IssuerRecord(Base):
    """Registered issuer in the Lemma network"""
    __tablename__ = 'issuer_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    issuer_did = Column(String(512), unique=True, nullable=False)
    domain = Column(String(255), nullable=False)
    public_key = Column(Text, nullable=False)
    name = Column(String(255))
    description = Column(Text)
    
    # Verification status
    verified = Column(Boolean, default=False)
    verification_method = Column(String(50))  # 'dns', 'well-known', 'manual'
    verification_token = Column(String(255))
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime)
    
    # Status
    is_active = Column(Boolean, default=True)
    revoked_at = Column(DateTime)
    revocation_reason = Column(String(255))
    
    # Stats
    lemmas_issued = Column(Integer, default=0)


def init_issuer_registry_table():
    """Create the issuer registry table if it doesn't exist"""
    try:
        IssuerRecord.__table__.create(engine, checkfirst=True)
        logger.info("✅ Issuer registry table ready")
    except Exception as e:
        logger.warning(f"⚠️ Issuer registry table creation: {e}")


# ============================================
# API ENDPOINTS
# ============================================

@issuer_registry_bp.route('/api/issuers/register', methods=['POST'])
@cross_origin()
@require_api_key
def register_issuer():
    """
    Register a new issuer with the Lemma network
    
    POST /api/issuers/register
    {
        "did": "did:web:mysite.com",
        "domain": "mysite.com",
        "name": "My Site",
        "publicKey": "base64url-encoded-public-key",
        "description": "Optional description"
    }
    """
    try:
        data = request.get_json()
        
        issuer_did = data.get('did')
        domain = data.get('domain')
        public_key = data.get('publicKey')
        name = data.get('name', domain)
        description = data.get('description', '')
        
        if not issuer_did or not domain or not public_key:
            return jsonify({
                'success': False,
                'error': 'did, domain, and publicKey are required'
            }), 400
        
        # Validate DID format
        if not issuer_did.startswith('did:'):
            return jsonify({
                'success': False,
                'error': 'Invalid DID format'
            }), 400
        
        # Generate verification token for domain verification
        verification_token = secrets.token_urlsafe(32)
        
        db = get_db()
        try:
            # Check if issuer already exists
            existing = db.query(IssuerRecord).filter(
                IssuerRecord.issuer_did == issuer_did
            ).first()
            
            if existing:
                # Update existing record
                existing.public_key = public_key
                existing.name = name
                existing.description = description
                existing.updated_at = datetime.utcnow()
                existing.verification_token = verification_token
                db.commit()
                
                logger.info(f"🔄 Updated issuer: {issuer_did}")
                
                return jsonify({
                    'success': True,
                    'issuer_did': issuer_did,
                    'updated': True,
                    'verification_token': verification_token,
                    'verification_instructions': get_verification_instructions(domain, verification_token)
                })
            
            # Create new issuer
            issuer = IssuerRecord(
                issuer_did=issuer_did,
                domain=domain,
                public_key=public_key,
                name=name,
                description=description,
                verification_token=verification_token,
                verified=False
            )
            
            db.add(issuer)
            db.commit()
            
            logger.info(f"✅ Registered new issuer: {issuer_did}")
            
            return jsonify({
                'success': True,
                'issuer_did': issuer_did,
                'created': True,
                'verification_token': verification_token,
                'verification_instructions': get_verification_instructions(domain, verification_token)
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Issuer registration failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@issuer_registry_bp.route('/api/issuers/<path:issuer_did>', methods=['GET'])
@cross_origin()
def get_issuer(issuer_did):
    """
    Get issuer information by DID
    
    GET /api/issuers/did:web:mysite.com
    """
    try:
        db = get_db()
        try:
            issuer = db.query(IssuerRecord).filter(
                IssuerRecord.issuer_did == issuer_did,
                IssuerRecord.is_active == True
            ).first()
            
            if not issuer:
                return jsonify({
                    'success': False,
                    'error': 'Issuer not found'
                }), 404
            
            return jsonify({
                'success': True,
                'did': issuer.issuer_did,
                'domain': issuer.domain,
                'name': issuer.name,
                'publicKey': issuer.public_key,
                'verified': issuer.verified,
                'description': issuer.description,
                'createdAt': issuer.created_at.isoformat() if issuer.created_at else None
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Get issuer failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@issuer_registry_bp.route('/api/issuers', methods=['GET'])
@cross_origin()
def list_issuers():
    """
    List registered issuers
    
    GET /api/issuers?verified=true&limit=50
    """
    try:
        verified_only = request.args.get('verified', 'false').lower() == 'true'
        limit = min(int(request.args.get('limit', 50)), 100)
        
        db = get_db()
        try:
            query = db.query(IssuerRecord).filter(IssuerRecord.is_active == True)
            
            if verified_only:
                query = query.filter(IssuerRecord.verified == True)
            
            issuers = query.order_by(IssuerRecord.created_at.desc()).limit(limit).all()
            
            return jsonify({
                'success': True,
                'issuers': [
                    {
                        'did': issuer.issuer_did,
                        'domain': issuer.domain,
                        'name': issuer.name,
                        'publicKey': issuer.public_key,
                        'verified': issuer.verified,
                        'createdAt': issuer.created_at.isoformat() if issuer.created_at else None
                    }
                    for issuer in issuers
                ],
                'count': len(issuers)
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ List issuers failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@issuer_registry_bp.route('/api/issuers/verify', methods=['POST'])
@cross_origin()
@require_api_key
def verify_issuer():
    """
    Verify domain ownership for an issuer
    
    POST /api/issuers/verify
    {
        "did": "did:web:mysite.com",
        "method": "well-known"  // 'dns' or 'well-known'
    }
    """
    try:
        data = request.get_json()
        issuer_did = data.get('did')
        method = data.get('method', 'well-known')
        
        if not issuer_did:
            return jsonify({
                'success': False,
                'error': 'did is required'
            }), 400
        
        db = get_db()
        try:
            issuer = db.query(IssuerRecord).filter(
                IssuerRecord.issuer_did == issuer_did
            ).first()
            
            if not issuer:
                return jsonify({
                    'success': False,
                    'error': 'Issuer not found. Register first.'
                }), 404
            
            # Attempt verification
            verified = False
            
            if method == 'well-known':
                verified = verify_well_known(issuer.domain, issuer.verification_token)
            elif method == 'dns':
                verified = verify_dns(issuer.domain, issuer.verification_token)
            
            if verified:
                issuer.verified = True
                issuer.verification_method = method
                issuer.updated_at = datetime.utcnow()
                db.commit()
                
                logger.info(f"✅ Verified issuer: {issuer_did} via {method}")
                
                return jsonify({
                    'success': True,
                    'verified': True,
                    'method': method,
                    'message': 'Domain ownership verified!'
                })
            else:
                return jsonify({
                    'success': False,
                    'verified': False,
                    'error': 'Verification failed. Check token placement.',
                    'instructions': get_verification_instructions(issuer.domain, issuer.verification_token)
                }), 400
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Verify issuer failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@issuer_registry_bp.route('/api/issuers/<path:issuer_did>/revoke', methods=['POST'])
@cross_origin()
@require_api_key
def revoke_issuer(issuer_did):
    """
    Revoke an issuer (mark as inactive)
    
    POST /api/issuers/did:web:mysite.com/revoke
    {
        "reason": "Compromised key"
    }
    """
    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'No reason provided')
        
        db = get_db()
        try:
            issuer = db.query(IssuerRecord).filter(
                IssuerRecord.issuer_did == issuer_did
            ).first()
            
            if not issuer:
                return jsonify({
                    'success': False,
                    'error': 'Issuer not found'
                }), 404
            
            issuer.is_active = False
            issuer.revoked_at = datetime.utcnow()
            issuer.revocation_reason = reason
            db.commit()
            
            logger.info(f"🚫 Revoked issuer: {issuer_did} - {reason}")
            
            return jsonify({
                'success': True,
                'revoked': True,
                'reason': reason
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Revoke issuer failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# VERIFICATION HELPERS
# ============================================

def get_verification_instructions(domain, token):
    """Get instructions for domain verification"""
    return {
        'well_known': {
            'description': 'Place a file at this URL with the verification token',
            'url': f'https://{domain}/.well-known/lemma-verification.txt',
            'content': token
        },
        'dns': {
            'description': 'Add a TXT record to your DNS',
            'record_type': 'TXT',
            'host': '_lemma-verification',
            'value': token
        }
    }


def verify_well_known(domain, token):
    """Verify domain via .well-known file"""
    import requests
    
    try:
        url = f'https://{domain}/.well-known/lemma-verification.txt'
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            return token in response.text
        return False
    except Exception as e:
        logger.warning(f"Well-known verification failed for {domain}: {e}")
        return False


def verify_dns(domain, token):
    """Verify domain via DNS TXT record"""
    import dns.resolver
    
    try:
        answers = dns.resolver.resolve(f'_lemma-verification.{domain}', 'TXT')
        for rdata in answers:
            if token in str(rdata):
                return True
        return False
    except Exception as e:
        logger.warning(f"DNS verification failed for {domain}: {e}")
        return False


# ============================================
# BOOTSTRAP
# ============================================

def register_lemma_as_issuer():
    """Register Lemma itself as a trusted issuer in the federated network"""
    try:
        from .issuer_management import get_issuer_manager
        
        issuer_manager = get_issuer_manager()
        
        db = get_db()
        try:
            # Register both the IAM issuer and federated issuer
            issuers_to_register = [
                {
                    'issuer_func': lambda: issuer_manager.get_iam_issuer('lemma.id'),
                    'domain': 'lemma.id',
                    'name': 'Lemma IAM',
                    'description': 'Official Lemma Identity & Access Management Service - issues PoH credentials'
                },
                {
                    'issuer_func': lambda: issuer_manager.get_federated_issuer(),
                    'domain': 'federated.lemma.id',
                    'name': 'Lemma Federated Network',
                    'description': 'Lemma Federated Identity Network - cross-platform identity'
                }
            ]
            
            for issuer_config in issuers_to_register:
                try:
                    issuer = issuer_config['issuer_func']()
                    
                    existing = db.query(IssuerRecord).filter(
                        IssuerRecord.domain == issuer_config['domain']
                    ).first()
                    
                    if existing:
                        # Update existing record
                        existing.public_key = issuer.get_public_key_hex()
                        existing.issuer_did = issuer.get_did()
                        existing.updated_at = datetime.utcnow()
                        logger.info(f"🔄 Updated {issuer_config['name']} in registry")
                    else:
                        # Create new record
                        record = IssuerRecord(
                            issuer_did=issuer.get_did(),
                            domain=issuer_config['domain'],
                            public_key=issuer.get_public_key_hex(),
                            name=issuer_config['name'],
                            description=issuer_config['description'],
                            verified=True,
                            verification_method='bootstrap'
                        )
                        db.add(record)
                        logger.info(f"✅ Registered {issuer_config['name']} as trusted issuer")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Could not register {issuer_config['name']}: {e}")
            
            db.commit()
            
        finally:
            db.close()
            
    except Exception as e:
        logger.warning(f"⚠️ Could not register Lemma issuers: {e}")


# ============================================
# WALLET INTEGRATION ENDPOINTS
# ============================================

@issuer_registry_bp.route('/api/issuers/lemma', methods=['GET'])
@cross_origin()
def get_lemma_issuer():
    """
    Get Lemma's issuer info for wallet caching
    This is the primary endpoint for wallets to bootstrap trust
    
    GET /api/issuers/lemma
    """
    try:
        from .issuer_management import get_issuer_manager
        
        issuer_manager = get_issuer_manager()
        iam_issuer = issuer_manager.get_iam_issuer('lemma.id')
        
        return jsonify({
            'success': True,
            'issuer': {
                'did': iam_issuer.get_did(),
                'domain': 'lemma.id',
                'name': 'Lemma',
                'publicKey': iam_issuer.get_public_key_hex(),
                'verified': True,
                'type': 'poh',  # Proof of Human issuer
                'description': 'Official Lemma Identity Service - issues Proof of Human credentials'
            },
            'walletStorage': {
                'did': iam_issuer.get_did(),
                'publicKey': iam_issuer.get_public_key_hex(),
                'name': 'Lemma',
                'verified': True
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Get Lemma issuer failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
