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
from auth.decorators import require_site_admin, require_api_key
import logging
import time
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
from api.revocation_verifier import is_credential_revoked

logger = logging.getLogger(__name__)

permission_verification_bp = Blueprint('permission_verification', __name__)

# Redis-based nonce cache (FIXES VULN-002: Multi-dyno nonce sharing)
try:
    from api.redis_client import get_shared_redis

    redis_client = get_shared_redis(prefer_cloud=True, decode_responses=True)
    REDIS_AVAILABLE = redis_client is not None
    if REDIS_AVAILABLE:
        logger.info("✅ Nonce cache using Redis (multi-dyno safe)")
    else:
        logger.warning("⚠️ Redis not available - nonce cache will use in-memory (not multi-dyno safe!)")
except Exception as e:
    redis_client = None
    REDIS_AVAILABLE = False
    logger.warning(f"⚠️ Redis connection failed: {e} - nonce cache will use in-memory")

# Fallback in-memory cache if Redis not available
_nonce_cache = {}
_NONCE_EXPIRY_SECONDS = 300  # 5 minutes

# Global verifier with Bloom filter (singleton)
_global_verifier = None

def get_global_verifier():
    """
    Get or create global OptimizedVerifier instance
    
    NOTE: Bloom filter sync is now EVENT-DRIVEN (not periodic)
    Revocations are synced immediately when credentials are revoked via Redis pub/sub
    """
    global _global_verifier
    
    from lemma_crypto import PyOptimizedVerifier
    
    # Create verifier if needed
    if _global_verifier is None:
        logger.info("🔐 Initializing global OptimizedVerifier with Bloom filter...")
        _global_verifier = PyOptimizedVerifier()
        
        # Do INITIAL sync of existing revocations
        try:
            sync_revocations_to_bloom()
            from api.revocation_verifier import mark_revocation_sync_ready

            mark_revocation_sync_ready()
            logger.info("✅ Initial bloom filter sync complete")
        except Exception as e:
            logger.warning(f"⚠️ Initial bloom filter sync failed: {e}")
        
        # Start event-driven revocation listener
        try:
            from api.revocation_sync import get_event_bus
            event_bus = get_event_bus()
            if event_bus.subscribed:
                logger.info("✅ Event-driven revocation sync active (Redis pub/sub)")
            else:
                logger.warning("⚠️ Event-driven revocation sync not available - using local-only mode")
        except Exception as e:
            logger.warning(f"⚠️ Could not start revocation event bus: {e}")
    
    return _global_verifier

def sync_revocations_to_bloom():
    """
    Sync ALL revoked credentials from database to Bloom filter
    This is called on startup to populate the bloom filter
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
            
            from api.site_ppid_revocation import keys_for_revocation_row

            count = 0
            seen_keys: set[str] = set()
            for revocation in revoked_list:
                for key in keys_for_revocation_row(revocation):
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    try:
                        _global_verifier.revoke_credential(key)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to add {key} to Bloom filter: {e}")

            logger.info(f"✅ Synced {count} revocation keys to Bloom filter")
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"❌ Revocation sync failed: {e}")


def sync_revocation_keys(credential_id: str) -> bool:
    """
    Sync all revocation identifiers for a credential into the in-process Bloom verifier.

    Looks up the revocation_list row when present so lemma_id, credential_id, ppid,
    and wallet_id keys stay aligned with sync_revocations_to_bloom().
    """
    global _global_verifier

    if _global_verifier is None:
        logger.warning("⚠️ Verifier not initialized - cannot sync revocation")
        return False

    keys = [credential_id]
    try:
        from api.database import get_db, RevocationList
        from api.site_ppid_revocation import keys_for_revocation_row

        session = get_db()
        try:
            row = (
                session.query(RevocationList)
                .filter(
                    (RevocationList.lemma_id == credential_id)
                    | (RevocationList.credential_id == credential_id)
                )
                .first()
            )
            if row:
                keys = keys_for_revocation_row(row)
        finally:
            session.close()
    except Exception as exc:
        logger.debug("Revocation row lookup failed for %s: %s", credential_id, exc)

    synced = False
    for key in keys:
        try:
            _global_verifier.revoke_credential(key)
            synced = True
            logger.info("✅ Added %s to bloom filter (immediate sync)", key)
        except Exception as exc:
            logger.error("❌ Failed to add %s to bloom filter: %s", key, exc)

    try:
        from api.bloom_snapshot import invalidate_bloom_filter_cache

        invalidate_bloom_filter_cache()
    except Exception:
        pass

    return synced


def sync_single_revocation(credential_id: str) -> bool:
    """
    Add a SINGLE revoked credential to Bloom filter immediately
    
    This is called by the event-driven revocation system when a 
    revocation event is received via Redis pub/sub.
    
    FIXES VULN-001: Immediate bloom filter update (no 60-second delay)
    
    Args:
        credential_id: ID of credential to revoke
        
    Returns:
        True if successfully added to bloom filter
    """
    return sync_revocation_keys(credential_id)

def is_nonce_fresh(nonce: str) -> bool:
    """
    Check if nonce has been used before (MULTI-DYNO SAFE)
    
    FIXES VULN-002: Uses Redis for shared nonce cache across all dynos
    
    Args:
        nonce: Nonce string to check
        
    Returns:
        True if nonce is fresh (not used), False if already used
    """
    if REDIS_AVAILABLE:
        # REDIS-BASED (multi-dyno safe)
        try:
            nonce_key = f"lemma:nonce:{nonce}"
            
            # Atomic check-and-set with SET NX (set if not exists)
            # Returns True if key was set (nonce is fresh)
            # Returns False if key already exists (nonce was used)
            was_set = redis_client.set(nonce_key, '1', nx=True, ex=_NONCE_EXPIRY_SECONDS)
            
            if not was_set:
                logger.warning(f"⚠️ Nonce reuse detected (possible replay attack): {nonce[:16]}...")
                logger.warning(f"   Multi-dyno replay protection working (Redis)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis nonce check failed: {e} - falling back to in-memory")
            # Fall through to in-memory cache
    
    # IN-MEMORY FALLBACK (not multi-dyno safe!)
    global _nonce_cache
    
    # Clean up expired nonces
    now = time.time()
    expired = [n for n, timestamp in _nonce_cache.items() if now - timestamp > _NONCE_EXPIRY_SECONDS]
    for n in expired:
        del _nonce_cache[n]
    
    # Check if nonce is fresh
    if nonce in _nonce_cache:
        logger.warning(f"⚠️ Nonce reuse detected (possible replay attack): {nonce[:16]}...")
        logger.warning(f"   WARNING: In-memory cache not multi-dyno safe!")
        return False
    
    # Mark nonce as used
    _nonce_cache[nonce] = now
    return True


@permission_verification_bp.route('/api/sdk/verify-permission-lemma', methods=['POST'])
@cross_origin()
@require_api_key
def verify_permission_lemma():
    """
    DEPRECATED: Server-side verification endpoint.

    Clients should verify credentials locally using the LemmaVerifier JS SDK
    (Ed25519 + Bloom filter). This endpoint is retained for backwards
    compatibility but will be removed in a future release.
    """
    logger.warning("Deprecated endpoint called: /api/sdk/verify-permission-lemma, migrate to local verification")
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
        
        # 3. Validate request origin matches site_domain when provided
        origin = request.headers.get('Origin')
        if origin:
            parsed = urlparse(origin)
            origin_host = parsed.hostname or ''
            if origin_host and origin_host != site_domain and not origin_host.endswith(f".{site_domain}"):
                return jsonify({
                    'success': False,
                    'verified': False,
                    'error': f'Origin mismatch: {origin_host} != {site_domain}'
                }), 403

        # 4. Extract credential claims
        claims = credential.get('claims') or credential.get('credentialSubject') or {}
        cred_site_domain = claims.get('siteDomain') or claims.get('site_domain')
        cred_id = credential.get('id')
        
        # 5. Verify site domain matches
        if cred_site_domain != site_domain:
            return jsonify({
                'success': False,
                'verified': False,
                'error': f'Site domain mismatch: {cred_site_domain} != {site_domain}'
            }), 403
        
        # 6. Cryptographic verification with Bloom filter revocation check
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
            # Layer 2: Bloom filter revocation check
            # Layer 3: Nonce freshness (already checked above)
            # Layer 5: Site domain binding (already checked above)
            
            is_valid = verifier.verify_credential_json(credential_json)
            
            verification_time_us = (time.perf_counter() - start_time) * 1_000_000
            
            if is_valid:
                # Canonical DB+verifier revocation guard for consistency.
                if is_credential_revoked(cred_id):
                    logger.warning(f"⚠️ Canonical revocation check denied credential (site: {site_domain})")
                    return jsonify({
                        'success': False,
                        'verified': False,
                        'error': 'Credential has been revoked',
                        'security_alert': True
                    }), 403

                # PRIVACY: Minimal logging - no credential contents, no user identifiers
                # Only log aggregate metrics for performance monitoring
                logger.info(f"✅ Verification OK: {verification_time_us:.0f}µs (site: {site_domain})")
                # REMOVED: credential ID logging - could enable correlation
                # REMOVED: permission ID logging - reveals user permissions
                # REMOVED: nonce logging - not needed after validation
                
                return jsonify({
                    'success': True,
                    'verified': True,
                    'verification_time_us': int(verification_time_us),
                    'confidence': 1.0,
                    'method': 'ed25519_bloom_nonce',
                    'security_layers': [
                        'ed25519_signature',
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
                # Check specifically for revocation through canonical helper
                is_revoked = is_credential_revoked(cred_id)
                
                if is_revoked:
                    # PRIVACY: Don't log credential ID - could enable tracking
                    logger.warning(f"⚠️ Revoked credential presented (site: {site_domain})")
                    return jsonify({
                        'success': False,
                        'verified': False,
                        'error': 'Credential has been revoked',
                        'security_alert': True
                    }), 403
                else:
                    # PRIVACY: Don't log credential ID
                    logger.warning(f"❌ Invalid signature (site: {site_domain})")
                    return jsonify({
                        'success': False,
                        'verified': False,
                        'error': 'Invalid signature',
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
@require_site_admin
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

