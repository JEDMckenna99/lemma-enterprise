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

# Global verifier with OPRF + Bloom filter (singleton)
_global_verifier = None
_verifier_last_sync = 0
_SYNC_INTERVAL_SECONDS = 60  # Sync revocations every 60 seconds

def get_global_verifier():
    """
    Get or create global OptimizedVerifier instance
    Automatically syncs revocations from database to Bloom filter
    """
    global _global_verifier, _verifier_last_sync
    
    from lemma_crypto import PyOptimizedVerifier
    
    # Create verifier if needed
    if _global_verifier is None:
        logger.info("🔐 Initializing global OptimizedVerifier with OPRF + Bloom filter...")
        _global_verifier = PyOptimizedVerifier.new()
        _verifier_last_sync = 0  # Force initial sync
    
    # Sync revocations from database to Bloom filter
    now = time.time()
    if now - _verifier_last_sync > _SYNC_INTERVAL_SECONDS:
        try:
            sync_revocations_to_bloom()
            _verifier_last_sync = now
        except Exception as e:
            logger.warning(f"⚠️ Failed to sync revocations to Bloom filter: {e}")
    
    return _global_verifier

def sync_revocations_to_bloom():
    """
    Sync all revoked credentials from database to Bloom filter
    This enables privacy-preserving, offline-capable revocation checks
    """
    global _global_verifier
    
    if _global_verifier is None:
        return
    
    try:
        from api.database import get_db, RevocationList
        
        session = get_db()
        try:
            # Get all revoked credentials
            revoked_list = session.query(RevocationList).all()
            
            if not revoked_list:
                logger.debug("No revocations to sync")
                return
            
            # Add each to Bloom filter via OPRF
            count = 0
            for revocation in revoked_list:
                try:
                    _global_verifier.revoke_credential(revocation.lemma_id)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to add {revocation.lemma_id} to Bloom filter: {e}")
            
            logger.info(f"✅ Synced {count} revocations to OPRF + Bloom filter")
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"❌ Revocation sync failed: {e}")

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
        
        # 5. Cryptographic verification with OPRF + Bloom filter revocation check
        start_time = time.perf_counter()
        
        try:
            from lemma_crypto import PyOptimizedVerifier
            import json
            
            # Get or create global verifier (singleton with Bloom filter)
            verifier = get_global_verifier()
            
            # Convert credential to JSON for Rust verification
            credential_json = json.dumps(credential)
            
            # COMPLETE VERIFICATION (includes all security layers):
            # Layer 1: Ed25519 signature verification
            # Layer 2: OPRF privacy-preserving evaluation
            # Layer 3: Cascaded Bloom filter revocation check
            # Layer 4: Nonce freshness (already checked above)
            # Layer 5: Site domain binding (already checked above)
            
            is_valid = verifier.verify_credential_json(credential_json)
            
            verification_time_us = (time.perf_counter() - start_time) * 1_000_000
            
            if is_valid:
                logger.info(f"✅ Permission lemma verified for {site_domain} in {verification_time_us:.0f}µs")
                logger.info(f"   Credential: {cred_id}")
                logger.info(f"   Permission: {claims.get('permissionId')}")
                logger.info(f"   Nonce: {nonce[:16]}...")
                logger.info(f"   Method: Ed25519 + OPRF + Bloom filter + nonce")
                
                return jsonify({
                    'success': True,
                    'verified': True,
                    'verification_time_us': int(verification_time_us),
                    'confidence': 1.0,
                    'method': 'ed25519_oprf_bloom_nonce',
                    'security_layers': [
                        'ed25519_signature',
                        'oprf_privacy',
                        'bloom_filter_revocation',
                        'nonce_replay_protection',
                        'site_domain_binding'
                    ],
                    'credential_id': cred_id,
                    'permission_id': claims.get('permissionId'),
                    'nonce_verified': True
                }), 200
            else:
                # Verification failed - could be invalid signature OR revoked credential
                # Check specifically for revocation
                is_revoked = verifier.is_revoked(cred_id)
                
                if is_revoked:
                    logger.warning(f"⚠️ Revoked credential presented: {cred_id}")
                    return jsonify({
                        'success': False,
                        'verified': False,
                        'error': 'Credential has been revoked (OPRF + Bloom filter)',
                        'security_alert': True,
                        'revocation_method': 'oprf_bloom_filter'
                    }), 403
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
            import traceback
            logger.error(traceback.format_exc())
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

