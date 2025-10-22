"""
Permission Lemma Verification with Nonce (Bot Defense)
========================================================

Cryptographically verifies permission lemmas with fresh nonces to prevent:
- Replay attacks
- Credential theft/reuse
- Bot farms automating with stolen credentials

Flow:
1. Client generates fresh nonce (256-bit random)
2. Client sends credential + nonce to server
3. Server verifies:
   - Ed25519 signature is valid
   - Credential not revoked
   - Nonce hasn't been used before (Redis cache)
   - Timestamp is recent (5-minute window)
4. Server caches nonce to prevent reuse
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

permission_verification_bp = Blueprint('permission_verification', __name__)

# In-memory nonce cache (use Redis in production)
_nonce_cache = {}
_NONCE_EXPIRY_SECONDS = 300  # 5 minutes

def is_nonce_fresh(nonce: str) -> bool:
    """
    Check if nonce has been used before
    Also clean up expired nonces
    """
    global _nonce_cache
    
    # Clean up expired nonces
    now = time.time()
    expired = [n for n, timestamp in _nonce_cache.items() if now - timestamp > _NONCE_EXPIRY_SECONDS]
    for n in expired:
        del _nonce_cache[n]
    
    # Check if nonce is fresh
    if nonce in _nonce_cache:
        logger.warning(f"⚠️ Nonce reuse detected (possible replay attack): {nonce[:16]}...")
        return False
    
    # Mark nonce as used
    _nonce_cache[nonce] = now
    return True


@permission_verification_bp.route('/api/sdk/verify-permission-lemma', methods=['POST'])
@cross_origin()
def verify_permission_lemma():
    """
    Verify permission lemma with nonce for bot defense
    """
    try:
        data = request.get_json()
        
        credential = data.get('credential')
        nonce = data.get('nonce')
        site_domain = data.get('site_domain')
        timestamp = data.get('timestamp')
        
        if not all([credential, nonce, site_domain, timestamp]):
            return jsonify({
                'success': False,
                'verified': False,
                'error': 'Missing required fields: credential, nonce, site_domain, timestamp'
            }), 400
        
        # 1. Check nonce freshness (replay attack prevention)
        if not is_nonce_fresh(nonce):
            return jsonify({
                'success': False,
                'verified': False,
                'error': 'Nonce already used (possible replay attack)',
                'security_alert': True
            }), 403
        
        # 2. Check timestamp (5-minute window)
        now = time.time() * 1000  # milliseconds
        time_diff = abs(now - timestamp)
        
        if time_diff > 300000:  # 5 minutes
            return jsonify({
                'success': False,
                'verified': False,
                'error': f'Timestamp too old ({time_diff / 1000:.0f}s ago)',
                'security_alert': True
            }), 403
        
        # 3. Extract credential claims
        claims = credential.get('claims') or credential.get('credentialSubject') or {}
        cred_site_domain = claims.get('siteDomain') or claims.get('site_domain')
        cred_id = credential.get('id')
        
        # 4. Verify site domain matches
        if cred_site_domain != site_domain:
            return jsonify({
                'success': False,
                'verified': False,
                'error': f'Site domain mismatch: {cred_site_domain} != {site_domain}'
            }), 403
        
        # 5. Check revocation status
        from api.database import get_db, RevocationList
        
        session = get_db()
        try:
            revoked = session.query(RevocationList).filter_by(lemma_id=cred_id).first()
            if revoked:
                logger.warning(f"⚠️ Revoked credential presented: {cred_id}")
                return jsonify({
                    'success': False,
                    'verified': False,
                    'error': 'Credential has been revoked',
                    'revoked_at': revoked.revoked_at.isoformat() if revoked.revoked_at else None
                }), 403
        finally:
            session.close()
        
        # 6. Cryptographic verification (Ed25519 signature)
        start_time = time.perf_counter()
        
        try:
            from lemma_crypto import PyMinimalVerifier
            
            # Extract signature and issuer DID
            proof = credential.get('proof', {})
            signature_hex = proof.get('proofValue') or proof.get('signatureValue')
            issuer_did = credential.get('issuer')
            
            if not signature_hex or not issuer_did:
                return jsonify({
                    'success': False,
                    'verified': False,
                    'error': 'Missing signature or issuer in credential'
                }), 400
            
            # Create verifier from issuer DID
            # Format: did:lemma:{public_key_hex}
            public_key_hex = issuer_did.replace('did:lemma:', '')
            
            # Convert credential to canonical JSON for verification
            import json
            credential_json = json.dumps(
                {k: v for k, v in credential.items() if k != 'proof'},
                sort_keys=True,
                separators=(',', ':')
            )
            
            # Verify signature
            verifier = PyMinimalVerifier.from_public_key_hex(public_key_hex)
            is_valid = verifier.verify_credential(credential_json, signature_hex)
            
            verification_time_us = (time.perf_counter() - start_time) * 1_000_000
            
            if is_valid:
                logger.info(f"✅ Permission lemma verified for {site_domain} in {verification_time_us:.0f}µs")
                logger.info(f"   Credential: {cred_id}")
                logger.info(f"   Permission: {claims.get('permissionId')}")
                logger.info(f"   Nonce: {nonce[:16]}...")
                
                return jsonify({
                    'success': True,
                    'verified': True,
                    'verification_time_us': int(verification_time_us),
                    'confidence': 1.0,
                    'method': 'ed25519_signature_with_nonce',
                    'credential_id': cred_id,
                    'permission_id': claims.get('permissionId'),
                    'nonce_verified': True
                }), 200
            else:
                logger.warning(f"❌ Invalid signature for credential {cred_id}")
                return jsonify({
                    'success': False,
                    'verified': False,
                    'error': 'Invalid Ed25519 signature',
                    'security_alert': True
                }), 403
                
        except Exception as e:
            logger.error(f"❌ Cryptographic verification failed: {e}")
            return jsonify({
                'success': False,
                'verified': False,
                'error': f'Verification error: {str(e)}'
            }), 500
        
    except Exception as e:
        logger.error(f"❌ Permission verification error: {e}")
        return jsonify({
            'success': False,
            'verified': False,
            'error': str(e)
        }), 500


@permission_verification_bp.route('/api/admin/nonce-stats', methods=['GET'])
def nonce_stats():
    """
    Admin endpoint to monitor nonce cache (bot activity detection)
    """
    global _nonce_cache
    
    now = time.time()
    active_nonces = {n: now - timestamp for n, timestamp in _nonce_cache.items()}
    
    return jsonify({
        'total_nonces': len(_nonce_cache),
        'active_nonces': len([t for t in active_nonces.values() if t < _NONCE_EXPIRY_SECONDS]),
        'expired_nonces': len([t for t in active_nonces.values() if t >= _NONCE_EXPIRY_SECONDS]),
        'cache_size_kb': len(str(_nonce_cache)) / 1024
    })

