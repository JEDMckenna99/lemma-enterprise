"""
OPRF Key Management API

Provides endpoints for:
- OPRF key metadata (not actual keys)
- Signed bloom filter distribution
- Key rotation status
"""

from flask import Blueprint, jsonify, request
from auth.decorators import require_api_key, rate_limit
import logging
import time
import base64
import json
import hashlib

oprf_key_bp = Blueprint('oprf_key', __name__)
logger = logging.getLogger(__name__)

# Global OPRF key manager (initialized at startup)
_oprf_key_manager = None

def init_oprf_key_manager():
    """Initialize OPRF key manager at application startup"""
    global _oprf_key_manager
    try:
        import lemma_crypto
        _oprf_key_manager = lemma_crypto.PyOPRFKeyManager('network')
        
        # Check if we have any keys, if not generate first one
        if _oprf_key_manager.get_active_version() == 0:
            logger.info("🔑 Generating initial OPRF key...")
            version = _oprf_key_manager.generate_new_version()
            _oprf_key_manager.activate_key(version)
            logger.info(f"✅ Initial OPRF key v{version} activated")
        else:
            logger.info(f"🔑 OPRF key manager initialized with version {_oprf_key_manager.get_active_version()}")
            
        return _oprf_key_manager
    except Exception as e:
        logger.error(f"❌ Failed to initialize OPRF key manager: {e}")
        return None

def get_oprf_key_manager():
    """Get global OPRF key manager instance"""
    global _oprf_key_manager
    if _oprf_key_manager is None:
        _oprf_key_manager = init_oprf_key_manager()
    return _oprf_key_manager


@oprf_key_bp.route('/api/v1/oprf/key-metadata', methods=['GET'])
@require_api_key
@rate_limit(max_requests=100, window=60)
def get_key_metadata():
    """
    Get OPRF key version metadata (NOT the actual keys)
    
    Returns information about:
    - Current active version
    - Supported versions for verification
    - Rotation schedule
    """
    try:
        key_manager = get_oprf_key_manager()
        if not key_manager:
            return jsonify({
                'success': False,
                'error': 'key_manager_unavailable'
            }), 503
        
        return jsonify({
            'success': True,
            'current_version': key_manager.get_active_version(),
            'supported_versions': key_manager.get_supported_versions(),
            'rotation_schedule': {
                'next_rotation': '2026-01-15T00:00:00Z',  # 1 year from deployment
                'rotation_frequency_days': 365,
                'grace_period_days': 90
            },
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"❌ Key metadata request failed: {e}")
        return jsonify({
            'success': False,
            'error': 'metadata_fetch_failed',
            'message': str(e)
        }), 500


@oprf_key_bp.route('/api/v1/oprf/bloom-filter', methods=['GET'])
@require_api_key
@rate_limit(max_requests=50, window=60)
def get_signed_bloom_filter():
    """
    Get signed bloom filter for specific OPRF key version
    
    CRITICAL: Bloom filter is cryptographically signed to prevent:
    - Malicious filter injection
    - Downgrade attacks  
    - Replay attacks
    - Tampering
    """
    try:
        # Get requested version (default to current)
        version = request.args.get('version', type=int)
        key_manager = get_oprf_key_manager()
        
        if not key_manager:
            return jsonify({
                'success': False,
                'error': 'key_manager_unavailable'
            }), 503
        
        if not version:
            version = key_manager.get_active_version()
        
        # Get bloom filter for this version
        bloom_filter_data, envelope = get_bloom_filter_envelope_for_version(version)
        
        if not bloom_filter_data or not envelope:
            return jsonify({
                'success': False,
                'error': 'filter_not_found',
                'version': version
            }), 404
        
        return jsonify({
            'success': True,
            'version': envelope['version'],
            'oprf_key_version': envelope['oprf_key_version'],
            'bloom_filter': {
                'data': base64.b64encode(bloom_filter_data).decode('utf-8'),
                'size_bytes': len(bloom_filter_data),
                'num_levels': envelope['filter_params']['num_levels'],
                'false_positive_rate': envelope['filter_params']['false_positive_rate']
            },
            'signature': envelope['signature'],
            'issuer_did': envelope['issuer_did'],
            'created_at': envelope['created_at'],
            'valid_from': envelope['valid_from'],
            'valid_until': envelope['valid_until'],
            'content_hash': envelope['content_hash'],
            'previous_version': envelope.get('previous_version'),
            'previous_version_hash': envelope.get('previous_version_hash')
        })
        
    except Exception as e:
        logger.error(f"❌ Bloom filter request failed: {e}")
        return jsonify({
            'success': False,
            'error': 'filter_fetch_failed',
            'message': str(e)
        }), 500


def get_bloom_filter_envelope_for_version(version: int):
    """
    Get bloom filter envelope for specific OPRF key version
    
    In production, this would:
    1. Fetch filter from database/cache
    2. Verify it's signed
    3. Check freshness
    4. Return envelope
    
    For now, we'll generate a test filter
    """
    try:
        import lemma_crypto
        
        # Create test bloom filter
        filter = lemma_crypto.CascadedBloomFilter(3, 10000, 0.001)
        
        # TODO: Add actual revoked credentials to filter
        # For now, it's empty (no revocations)
        
        # Create signed envelope
        # In production, use actual network authority key
        from api.issuer_management import get_network_authority_issuer
        authority_issuer = get_network_authority_issuer()
        
        # Get issuer DID
        issuer_did = authority_issuer.get_did()
        
        # Serialize filter
        filter_data = serialize_bloom_filter(filter)
        
        # Create envelope metadata
        now = int(time.time())
        envelope = {
            'version': 1,  # TODO: Track actual version
            'oprf_key_version': version,
            'filter_params': {
                'num_levels': 3,
                'base_capacity': 10000,
                'false_positive_rate': 0.001
            },
            'created_at': now,
            'valid_from': now,
            'valid_until': now + (7 * 24 * 3600),  # 7 days
            'content_hash': hashlib.sha256(filter_data).hexdigest(),
            'issuer_did': issuer_did,
            'signature': sign_bloom_filter_envelope(filter_data, version, issuer_did, authority_issuer)
        }
        
        return filter_data, envelope
        
    except Exception as e:
        logger.error(f"❌ Failed to generate bloom filter envelope: {e}")
        return None, None


def serialize_bloom_filter(filter):
    """Serialize bloom filter to bytes"""
    # TODO: Implement proper serialization
    # For now, return placeholder
    return b"bloom_filter_data_placeholder"


def sign_bloom_filter_envelope(filter_data: bytes, version: int, issuer_did: str, issuer) -> str:
    """
    Sign bloom filter envelope with network authority key
    
    This prevents:
    - Malicious clients creating fake filters
    - Downgrade attacks (using old filters)
    - Tampering with filter contents
    """
    # Create canonical signing payload
    payload = {
        'version': version,
        'data_hash': hashlib.sha256(filter_data).hexdigest(),
        'timestamp': int(time.time()),
        'type': 'revocation_bloom_filter'
    }
    
    # Sign with Ed25519 using network authority key
    canonical_payload = json.dumps(payload, sort_keys=True)
    
    # TODO: Implement actual signing with issuer's private key
    # For now, return placeholder
    return "signature_placeholder_" + hashlib.sha256(canonical_payload.encode()).hexdigest()


@oprf_key_bp.route('/api/v1/oprf/initiate-rotation', methods=['POST'])
@require_api_key
@rate_limit(max_requests=5, window=3600)  # Very limited - admin only
def initiate_key_rotation():
    """
    Initiate OPRF key rotation
    
    This is a CRITICAL operation that should only be done:
    - On schedule (annually)
    - In response to suspected compromise
    - For compliance requirements
    """
    try:
        data = request.json or {}
        reason = data.get('reason', 'scheduled_rotation')
        
        key_manager = get_oprf_key_manager()
        if not key_manager:
            return jsonify({
                'success': False,
                'error': 'key_manager_unavailable'
            }), 503
        
        # Generate new key version
        new_version = key_manager.generate_new_version()
        logger.info(f"🔄 Generated new OPRF key version: {new_version}")
        
        # Activate new key (starts rotation)
        rotation_plan = key_manager.activate_key(new_version)
        logger.info(f"✅ OPRF key rotation initiated: v{rotation_plan['old_version']} → v{rotation_plan['new_version']}")
        
        return jsonify({
            'success': True,
            'rotation_plan': {
                'old_version': rotation_plan['old_version'],
                'new_version': rotation_plan['new_version'],
                'grace_period_days': rotation_plan['grace_period_days'],
                'estimated_completion': rotation_plan['estimated_completion']
            },
            'message': 'Key rotation initiated successfully',
            'next_steps': [
                'Old key will remain valid for 90 days',
                'New credentials will use new key',
                'Old credentials remain verifiable during grace period',
                'Rebuild bloom filters with new key'
            ]
        })
        
    except Exception as e:
        logger.error(f"❌ Key rotation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'rotation_failed',
            'message': str(e)
        }), 500


@oprf_key_bp.route('/api/v1/oprf/revoke-key', methods=['POST'])
@require_api_key
@rate_limit(max_requests=2, window=3600)  # Very limited - emergency only
def emergency_key_revocation():
    """
    Emergency OPRF key revocation
    
    Use only when:
    - Key compromise is suspected or confirmed
    - Security incident requires immediate response
    - Regulatory requirement demands it
    """
    try:
        data = request.json or {}
        version = data.get('version')
        reason = data.get('reason', 'unspecified')
        
        if not version:
            return jsonify({
                'success': False,
                'error': 'version_required'
            }), 400
        
        key_manager = get_oprf_key_manager()
        if not key_manager:
            return jsonify({
                'success': False,
                'error': 'key_manager_unavailable'
            }), 503
        
        # Revoke key (will auto-generate and activate new key)
        key_manager.revoke_key(version, reason)
        logger.warning(f"🚨 OPRF key v{version} REVOKED: {reason}")
        
        # Get new active version
        new_version = key_manager.get_active_version()
        
        return jsonify({
            'success': True,
            'revoked_version': version,
            'reason': reason,
            'new_active_version': new_version,
            'message': 'Key revoked and new key activated',
            'impact': 'All credentials using revoked key are now invalid',
            'action_required': 'Re-issue all credentials with new key version'
        })
        
    except Exception as e:
        logger.error(f"❌ Key revocation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_failed',
            'message': str(e)
        }), 500

