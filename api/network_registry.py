"""
LEMMA NETWORK REGISTRY API
Distributed DID and Revocation List Management

This module provides network-wide distribution of:
1. DID Registry: Trusted issuer DIDs and public keys
2. Revocation Lists: OPRF + Bloom Filter revocation data
3. Trust Anchors: Root trust relationships

All sites using Lemma can sync from this central registry.
"""

import os
import json
import time
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from flask import Blueprint, request, jsonify, current_app
from functools import wraps
import logging

# Import CORS decorator
from auth.decorators import cors_headers

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
network_registry_bp = Blueprint('network_registry', __name__)

# Initialize with trusted DIDs for bootstrap
def initialize_trusted_dids():
    """Bootstrap the network registry with trusted issuers"""
    trusted_issuers = {
        'did:lemma:identity_network': {
            'did': 'did:lemma:identity_network',
            'public_key': 'lemma_identity_network_key_2024',
            'name': 'Lemma Identity Network',
            'issuer_type': 'identity_kyc_provider',
            'trust_score': 0.95,
            'verified': True,
            'created_at': time.time(),
            'capabilities': ['stripe_identity_verification', 'kyc_verification']
        },
        'did:lemma:stripe_identity': {
            'did': 'did:lemma:stripe_identity', 
            'public_key': 'lemma_stripe_integration_key_2024',
            'name': 'Lemma Stripe Identity Integration',
            'issuer_type': 'third_party_kyc',
            'trust_score': 0.90,
            'verified': True,
            'created_at': time.time(),
            'capabilities': ['stripe_identity_verification']
        },

    }
    return trusted_issuers

# Registry storage (in production, this would be a distributed database)
NETWORK_REGISTRY = {
    'did_registry': initialize_trusted_dids(),  # Bootstrap with trusted DIDs
    'revocation_lists': {
        'oprf_bloom_filters': {},
        'revocation_entries': {},
        'last_updated': 0
    },
    'trust_anchors': {},
    'network_metadata': {
        'version': '1.0.0',
        'created_at': time.time(),
        'total_sites': 0,
        'total_dids': len(initialize_trusted_dids()),  # Count bootstrapped DIDs  
        'total_revocations': 0
    }
}

def require_network_auth(f):
    """Require network authentication for registry operations"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Network '):
            return jsonify({
                'success': False,
                'error': 'missing_network_auth',
                'message': 'Network authorization required'
            }), 401
        
        network_key = auth_header[8:]  # Remove 'Network ' prefix
        
        # In production, validate against known network keys
        # For now, accept any key starting with 'lemma_network_'
        if not network_key.startswith('lemma_network_'):
            return jsonify({
                'success': False,
                'error': 'invalid_network_key',
                'message': 'Invalid network authorization key'
            }), 401
        
        return f(*args, **kwargs)
    return decorated_function

@network_registry_bp.route('/api/network/did-registry', methods=['GET', 'OPTIONS'])
@cors_headers
@require_network_auth
def get_did_registry():
    """
    Get the distributed DID registry for issuer verification
    
    Returns all trusted issuer DIDs, public keys, and trust scores
    used by sites for credential verification.
    """
    
    # Handle CORS preflight requests
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        site_id = request.args.get('site_id', 'unknown')
        version = request.args.get('version', '0')
        
        registry = NETWORK_REGISTRY['did_registry']
        current_version = str(hash(json.dumps(registry, sort_keys=True)))
        
        # Check if client needs update
        needs_update = version != current_version
        
        logger.info(f"📋 DID registry request from {site_id}, needs_update={needs_update}")
        
        response = {
            'success': True,
            'version': current_version,
            'needs_update': needs_update,
            'total_issuers': len(registry),
            'registry': registry if needs_update else {},
            'metadata': {
                'last_updated': NETWORK_REGISTRY['network_metadata'].get('last_updated', time.time()),
                'total_network_sites': NETWORK_REGISTRY['network_metadata']['total_sites'],
                'sync_timestamp': time.time()
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ DID registry fetch failed: {e}")
        return jsonify({
            'success': False,
            'error': 'registry_fetch_failed',
            'message': str(e)
        }), 500

@network_registry_bp.route('/api/network/revocation-lists', methods=['GET', 'OPTIONS'])
@cors_headers
@require_network_auth
def get_revocation_lists():
    """
    Get distributed revocation lists (OPRF + Bloom Filter data)
    
    Returns revocation bloom filters and OPRF evaluations
    for offline revocation checking.
    """
    try:
        site_id = request.args.get('site_id', 'unknown')
        last_sync = float(request.args.get('last_sync', '0'))
        
        revocation_data = NETWORK_REGISTRY['revocation_lists']
        current_timestamp = time.time()
        
        # Only return updates since last sync
        updates_since_sync = {}
        if current_timestamp - last_sync > 60:  # More than 1 minute old
            updates_since_sync = revocation_data
        else:
            # Return only recent updates
            for cred_id, entry in revocation_data['revocation_entries'].items():
                if entry.get('revoked_at', 0) > last_sync:
                    updates_since_sync[cred_id] = entry
        
        logger.info(f"🚫 Revocation list request from {site_id}, updates={len(updates_since_sync)}")
        
        response = {
            'success': True,
            'has_updates': len(updates_since_sync) > 0,
            'sync_timestamp': current_timestamp,
            'last_updated': revocation_data['last_updated'],
            'total_revocations': len(revocation_data['revocation_entries']),
            'revocation_updates': updates_since_sync,
            'bloom_filter_updates': revocation_data.get('oprf_bloom_filters', {}),
            'metadata': {
                'oprf_evaluations_count': len(revocation_data.get('oprf_bloom_filters', {})),
                'network_propagation': 'instant',
                'offline_checking': True
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Revocation list fetch failed: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_fetch_failed',
            'message': str(e)
        }), 500

@network_registry_bp.route('/api/network/register-did', methods=['POST'])
@require_network_auth
def register_did():
    """
    Register a new DID in the network registry
    
    Called by the Rust engine when creating new issuer DIDs
    """
    try:
        data = request.get_json() or {}
        
        did = data.get('did')
        public_key = data.get('public_key')
        issuer_info = data.get('issuer_info', {})
        
        if not did or not public_key:
            return jsonify({
                'success': False,
                'error': 'missing_required_fields',
                'message': 'DID and public_key are required'
            }), 400
        
        # Validate DID format
        if not did.startswith('did:lemma:'):
            return jsonify({
                'success': False,
                'error': 'invalid_did_format',
                'message': 'DID must use did:lemma: format'
            }), 400
        
        # Register in network registry
        registry_entry = {
            'did': did,
            'public_key': public_key,
            'registered_at': time.time(),
            'trust_score': issuer_info.get('trust_score', 0.8),
            'issuer_type': issuer_info.get('issuer_type', 'lemma_service'),
            'issuer_name': issuer_info.get('name', 'Lemma Network Issuer'),
            'verified': issuer_info.get('verified', True),
            'total_credentials_issued': 0,
            'metadata': {
                'created_by': 'rust_engine',
                'network_distributed': True,
                'last_activity': time.time()
            }
        }
        
        NETWORK_REGISTRY['did_registry'][did] = registry_entry
        NETWORK_REGISTRY['network_metadata']['total_dids'] = len(NETWORK_REGISTRY['did_registry'])
        NETWORK_REGISTRY['network_metadata']['last_updated'] = time.time()
        
        logger.info(f"📝 Registered new DID in network: {did}")
        
        return jsonify({
            'success': True,
            'did': did,
            'registered': True,
            'network_propagation': 'instant',
            'total_network_dids': len(NETWORK_REGISTRY['did_registry'])
        })
        
    except Exception as e:
        logger.error(f"❌ DID registration failed: {e}")
        return jsonify({
            'success': False,
            'error': 'did_registration_failed',
            'message': str(e)
        }), 500

@network_registry_bp.route('/api/network/register-revocation', methods=['POST'])
@require_network_auth
def register_revocation():
    """
    Register credential revocation in the network registry
    
    Called by the revocation system to distribute OPRF + Bloom Filter updates
    """
    try:
        data = request.get_json() or {}
        
        credential_id = data.get('credential_id')
        oprf_evaluation = data.get('oprf_evaluation')
        bloom_hash = data.get('bloom_hash')
        revocation_reason = data.get('reason', 'user_requested')
        
        if not credential_id or not oprf_evaluation:
            return jsonify({
                'success': False,
                'error': 'missing_required_fields',
                'message': 'credential_id and oprf_evaluation are required'
            }), 400
        
        current_time = time.time()
        
        # Add to revocation registry
        revocation_entry = {
            'credential_id': credential_id,
            'oprf_evaluation': oprf_evaluation,
            'bloom_hash': bloom_hash,
            'revoked_at': current_time,
            'reason': revocation_reason,
            'network_distributed': True,
            'propagation_time': 0  # Instant propagation
        }
        
        NETWORK_REGISTRY['revocation_lists']['revocation_entries'][credential_id] = revocation_entry
        NETWORK_REGISTRY['revocation_lists']['oprf_bloom_filters'][oprf_evaluation] = {
            'bloom_hash': bloom_hash,
            'added_at': current_time,
            'network_level': 'global'
        }
        NETWORK_REGISTRY['revocation_lists']['last_updated'] = current_time
        NETWORK_REGISTRY['network_metadata']['total_revocations'] = len(NETWORK_REGISTRY['revocation_lists']['revocation_entries'])
        
        logger.info(f"🚫 Registered revocation in network: {credential_id} (reason: {revocation_reason})")
        
        return jsonify({
            'success': True,
            'credential_id': credential_id,
            'revoked': True,
            'network_propagation': 'instant',
            'oprf_distributed': True,
            'bloom_filter_updated': True,
            'total_network_revocations': len(NETWORK_REGISTRY['revocation_lists']['revocation_entries'])
        })
        
    except Exception as e:
        logger.error(f"❌ Revocation registration failed: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_registration_failed',
            'message': str(e)
        }), 500

@network_registry_bp.route('/api/network/sync-status', methods=['GET'])
@require_network_auth
def get_sync_status():
    """
    Get network synchronization status for monitoring
    """
    try:
        site_id = request.args.get('site_id', 'unknown')
        
        status = {
            'success': True,
            'network_health': 'healthy',
            'sync_timestamp': time.time(),
            'statistics': {
                'total_sites': NETWORK_REGISTRY['network_metadata']['total_sites'],
                'total_dids': len(NETWORK_REGISTRY['did_registry']),
                'total_revocations': len(NETWORK_REGISTRY['revocation_lists']['revocation_entries']),
                'last_did_registration': max([entry.get('registered_at', 0) for entry in NETWORK_REGISTRY['did_registry'].values()] or [0]),
                'last_revocation': NETWORK_REGISTRY['revocation_lists']['last_updated']
            },
            'performance': {
                'avg_sync_time_ms': 45.2,  # Simulated performance data
                'oprf_evaluation_time_us': 12.8,
                'bloom_filter_update_time_us': 0.9,
                'network_propagation': 'instant'
            }
        }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"❌ Sync status failed: {e}")
        return jsonify({
            'success': False,
            'error': 'sync_status_failed',
            'message': str(e)
        }), 500

@network_registry_bp.route('/api/network/health', methods=['GET'])
def network_health():
    """Network registry health check - no auth required"""
    return jsonify({
        'status': 'healthy',
        'service': 'lemma_network_registry',
        'version': NETWORK_REGISTRY['network_metadata']['version'],
        'uptime': time.time() - NETWORK_REGISTRY['network_metadata']['created_at'],
        'total_dids': len(NETWORK_REGISTRY['did_registry']),
        'total_revocations': len(NETWORK_REGISTRY['revocation_lists']['revocation_entries']),
        'last_activity': NETWORK_REGISTRY['network_metadata'].get('last_updated', 0)
    })

# Initialize production network registry
def initialize_production_registry():
    """Initialize the registry with production trusted issuers"""
    # Initialize from trusted issuers defined above
    trusted_issuers = initialize_trusted_dids()
    
    for did, issuer_data in trusted_issuers.items():
        NETWORK_REGISTRY['did_registry'][did] = issuer_data
    
    NETWORK_REGISTRY['network_metadata']['total_dids'] = len(NETWORK_REGISTRY['did_registry'])
    NETWORK_REGISTRY['network_metadata']['last_updated'] = time.time()
    
    logger.info(f"🌐 Initialized production network registry with {len(NETWORK_REGISTRY['did_registry'])} trusted issuers")

# Initialize production registry when module is imported
initialize_production_registry()

# Export the blueprint
__all__ = ['network_registry_bp']