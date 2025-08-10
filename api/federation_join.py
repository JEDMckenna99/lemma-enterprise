"""
Lemma Federated Network - Node Join Protocol
===========================================

Implements the signed join token protocol for dynamic site onboarding.
Sites can request to join the federation and receive network bundles.
"""

import json
import time
import hmac
import hashlib
import secrets
from typing import Dict, List, Optional, Any
from flask import Blueprint, request, jsonify
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Federation join blueprint
federation_join_bp = Blueprint('federation_join', __name__)

# Network configuration
NETWORK_CONFIG = {
    "network_did": "did:lemma:network",
    "network_name": "Lemma Federated Identity Network",
    "current_epoch": int(time.time() // 86400),  # Daily epochs
    "network_authority_key": "lemma_network_federated_sync_2024",
    "join_token_ttl": 3600,  # 1 hour
}

# Network public keys (in production, these would be proper Ed25519 keys)
NETWORK_PUBKEYS = {
    "network_sig": "ed25519:A1B2C3D4E5F6789012345678901234567890ABCDEF1234567890ABCDEF12345",
    "revocation_sig": "ed25519:F1E2D3C4B5A6789012345678901234567890FEDCBA1234567890FEDCBA12345"
}

# Active join requests (in production, use Redis or database)
active_join_requests = {}
approved_nodes = set()

class NetworkJoinManager:
    def __init__(self):
        self.pending_requests = {}
        self.approved_nodes = set()
        self.network_bundle_cache = None
        self.last_bundle_update = 0
        
    def generate_network_bundle(self) -> Dict[str, Any]:
        """Generate current network bundle with DIDs, keys, and revocation state"""
        current_time = time.time()
        
        # Update cache if stale (5 minute TTL)
        if not self.network_bundle_cache or (current_time - self.last_bundle_update) > 300:
            from api.realtime_network_sync import sync_manager
            
            # Get current revocation state
            with sync_manager.sync_lock:
                revocation_items = list(sync_manager.shared_bloom_filter)
            
            # Create revocation digests
            hard_items = [item for item in revocation_items if item.startswith('cred_')]
            soft_items = [item for item in revocation_items if item.startswith('oprf_')]
            
            hard_digest = hashlib.sha256(''.join(sorted(hard_items)).encode()).hexdigest()
            soft_digest = hashlib.sha256(''.join(sorted(soft_items)).encode()).hexdigest()
            
            self.network_bundle_cache = {
                "network_did": NETWORK_CONFIG["network_did"],
                "network_name": NETWORK_CONFIG["network_name"],
                "epoch": NETWORK_CONFIG["current_epoch"],
                "pubkeys": NETWORK_PUBKEYS,
                "revocation": {
                    "hard_digest": hard_digest,
                    "soft_digest": soft_digest,
                    "epoch": NETWORK_CONFIG["current_epoch"],
                    "total_revocations": len(revocation_items)
                },
                "network_endpoints": [
                    "https://lemma-8b58c15b2f1b.herokuapp.com",
                    "https://lemma-enterprise-0f6ba17076c1.herokuapp.com",
                    "https://lemma-identity-network-2d96786d6ffb.herokuapp.com"
                ],
                "capabilities": [
                    "identity_verification",
                    "cross_site_recognition", 
                    "real_time_revocation",
                    "microsecond_verification"
                ],
                "generated_at": current_time
            }
            self.last_bundle_update = current_time
            
        return self.network_bundle_cache
    
    def validate_join_request(self, request_data: Dict[str, Any]) -> tuple[bool, str]:
        """Validate a node join request"""
        required_fields = ["site_origin", "site_did", "nonce"]
        
        for field in required_fields:
            if field not in request_data:
                return False, f"Missing required field: {field}"
        
        site_origin = request_data["site_origin"]
        site_did = request_data["site_did"]
        nonce = request_data["nonce"]
        
        # Validate site origin format
        if not site_origin.startswith(('https://', 'http://localhost')):
            return False, "Invalid site origin - must use HTTPS"
        
        # Validate DID format
        if not site_did.startswith('did:'):
            return False, "Invalid DID format"
        
        # Validate nonce
        if not nonce or len(nonce) < 16:
            return False, "Invalid nonce - must be at least 16 characters"
        
        # Check if already approved
        if site_origin in self.approved_nodes:
            return False, "Site already approved in network"
        
        return True, "Valid request"
    
    def generate_join_token(self, site_origin: str, site_did: str, nonce: str) -> str:
        """Generate signed join token"""
        token_data = {
            "site_origin": site_origin,
            "site_did": site_did,
            "nonce": nonce,
            "network_did": NETWORK_CONFIG["network_did"],
            "issued_at": time.time(),
            "expires_at": time.time() + NETWORK_CONFIG["join_token_ttl"],
            "permissions": ["network_sync", "identity_sharing", "revocation_updates"]
        }
        
        # Create JWT-like token (simplified - in production use proper JWT/COSE)
        token_json = json.dumps(token_data, sort_keys=True)
        
        # Sign with network authority key
        signature = hmac.new(
            NETWORK_CONFIG["network_authority_key"].encode(),
            token_json.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"{token_json.encode().hex()}.{signature}"
    
    def verify_join_token(self, token: str) -> tuple[bool, Dict[str, Any]]:
        """Verify a join token"""
        try:
            token_hex, signature = token.split('.')
            token_json = bytes.fromhex(token_hex).decode()
            token_data = json.loads(token_json)
            
            # Verify signature
            expected_signature = hmac.new(
                NETWORK_CONFIG["network_authority_key"].encode(),
                token_json.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return False, {"error": "Invalid token signature"}
            
            # Check expiration
            if token_data["expires_at"] < time.time():
                return False, {"error": "Token expired"}
            
            return True, token_data
            
        except Exception as e:
            return False, {"error": f"Token validation failed: {str(e)}"}

# Global join manager
join_manager = NetworkJoinManager()

@federation_join_bp.route('/api/network/join-request', methods=['POST'])
def handle_join_request():
    """Handle node join request with signed response"""
    try:
        request_data = request.get_json() or {}
        
        logger.info(f"🌐 Received federation join request from {request_data.get('site_origin', 'unknown')}")
        
        # Validate request
        is_valid, validation_message = join_manager.validate_join_request(request_data)
        if not is_valid:
            logger.warning(f"❌ Invalid join request: {validation_message}")
            return jsonify({
                "success": False,
                "error": "invalid_request",
                "message": validation_message
            }), 400
        
        site_origin = request_data["site_origin"]
        site_did = request_data["site_did"]
        nonce = request_data["nonce"]
        
        # Generate network bundle
        network_bundle = join_manager.generate_network_bundle()
        
        # Generate join token
        join_token = join_manager.generate_join_token(site_origin, site_did, nonce)
        
        # Create signed response
        response_data = {
            **network_bundle,
            "join_token": join_token,
            "request_nonce": nonce,
            "approved": True,
            "message": f"Welcome to {NETWORK_CONFIG['network_name']}"
        }
        
        # Sign the entire response
        response_json = json.dumps(response_data, sort_keys=True)
        response_signature = hmac.new(
            NETWORK_CONFIG["network_authority_key"].encode(),
            (response_json + nonce).encode(),
            hashlib.sha256
        ).hexdigest()
        
        response_data["signature"] = response_signature
        
        # Add to approved nodes
        join_manager.approved_nodes.add(site_origin)
        
        # Add to network sync manager
        from api.realtime_network_sync import sync_manager
        sync_manager.add_network_node(site_origin)
        
        logger.info(f"✅ Approved federation join for {site_origin}")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"❌ Join request failed: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "Failed to process join request"
        }), 500

@federation_join_bp.route('/api/network/bundle', methods=['GET'])
def get_network_bundle():
    """Get current network bundle"""
    try:
        # Verify network authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Network '):
            return jsonify({
                "success": False,
                "error": "unauthorized",
                "message": "Network authorization required"
            }), 401
        
        network_key = auth_header[8:]
        if network_key != NETWORK_CONFIG["network_authority_key"]:
            return jsonify({
                "success": False,
                "error": "invalid_network_key",
                "message": "Invalid network authorization"
            }), 401
        
        # Generate and return current bundle
        bundle = join_manager.generate_network_bundle()
        
        logger.info("📦 Provided network bundle to authenticated node")
        
        return jsonify({
            "success": True,
            **bundle
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to provide network bundle: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "Failed to generate network bundle"
        }), 500

@federation_join_bp.route('/api/network/verify-token', methods=['POST'])
def verify_join_token():
    """Verify a join token"""
    try:
        data = request.get_json() or {}
        token = data.get('join_token')
        
        if not token:
            return jsonify({
                "success": False,
                "error": "missing_token",
                "message": "Join token required"
            }), 400
        
        is_valid, token_data = join_manager.verify_join_token(token)
        
        if is_valid:
            logger.info(f"✅ Valid join token for {token_data.get('site_origin')}")
            return jsonify({
                "success": True,
                "valid": True,
                "token_data": token_data
            })
        else:
            logger.warning(f"❌ Invalid join token: {token_data.get('error')}")
            return jsonify({
                "success": False,
                "valid": False,
                "error": token_data.get('error')
            })
        
    except Exception as e:
        logger.error(f"❌ Token verification failed: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "Token verification failed"
        }), 500

@federation_join_bp.route('/api/network/federation-status', methods=['GET'])
def get_federation_status():
    """Get current federation status"""
    try:
        # Verify network authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Network '):
            return jsonify({
                "success": False,
                "error": "unauthorized"
            }), 401
        
        network_key = auth_header[8:]
        if network_key != NETWORK_CONFIG["network_authority_key"]:
            return jsonify({
                "success": False,
                "error": "invalid_network_key"
            }), 401
        
        from api.realtime_network_sync import sync_manager
        
        with sync_manager.sync_lock:
            status = {
                "success": True,
                "network_did": NETWORK_CONFIG["network_did"],
                "network_name": NETWORK_CONFIG["network_name"],
                "current_epoch": NETWORK_CONFIG["current_epoch"],
                "approved_nodes": len(join_manager.approved_nodes),
                "active_nodes": len(sync_manager.network_nodes),
                "total_revocations": len(sync_manager.shared_bloom_filter),
                "total_identity_lemmas": len([k for k in sync_manager.shared_identity_lemmas.keys() if not k.startswith('user:')]),
                "last_bundle_update": join_manager.last_bundle_update
            }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"❌ Failed to get federation status: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error"
        }), 500

# Auto-initialize approved nodes from sync manager
def initialize_federation():
    """Initialize federation with known nodes"""
    try:
        from api.realtime_network_sync import sync_manager
        
        # Add known endpoints as approved nodes
        for endpoint in sync_manager.known_endpoints:
            join_manager.approved_nodes.add(endpoint)
            
        logger.info(f"🌐 Federation initialized with {len(join_manager.approved_nodes)} approved nodes")
        
    except Exception as e:
        logger.error(f"❌ Federation initialization failed: {e}")

# Initialize on import
initialize_federation()
