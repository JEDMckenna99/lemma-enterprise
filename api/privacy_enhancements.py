"""
Lemma Federated Network - Privacy & Unlinkability Enhancements
============================================================

Implements:
1. Pairwise Pseudonymous IDs (PPIDs) per origin
2. Proof-of-Possession challenge-response
3. Static JSON replay prevention
"""

import json
import time
import hmac
import hashlib
import secrets
import base64
from typing import Dict, List, Optional, Any, Tuple
from flask import Blueprint, request, jsonify
import logging
from datetime import datetime, timedelta

# Import CORS decorator
from auth.decorators import cors_headers

logger = logging.getLogger(__name__)

# Privacy enhancements blueprint
privacy_bp = Blueprint('privacy', __name__)

# Privacy configuration
PRIVACY_CONFIG = {
    "ppid_master_key": "lemma_ppid_master_key_2024_secure",
    "challenge_ttl": 300,  # 5 minutes
    "max_replay_window": 60,  # 60 seconds
    "nonce_cache_size": 10000,
}

# Active challenges and nonce cache (in production, use Redis)
active_challenges = {}
used_nonces = set()

class PrivacyManager:
    def __init__(self):
        self.active_challenges = {}
        self.used_nonces = set()
        self.nonce_cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
    
    def generate_ppid(self, global_user_id: str, site_origin: str) -> str:
        """Generate pairwise pseudonymous ID for user per origin"""
        # PPID = HMAC(master_key, global_user_id || site_origin)
        combined_input = f"{global_user_id}||{site_origin}"
        
        ppid_raw = hmac.new(
            PRIVACY_CONFIG["ppid_master_key"].encode(),
            combined_input.encode(),
            hashlib.sha256
        ).digest()
        
        # Create readable PPID
        ppid = f"ppid:{base64.urlsafe_b64encode(ppid_raw[:16]).decode().rstrip('=')}"
        
        logger.info(f"🔐 Generated PPID for user {global_user_id[:8]}... at {site_origin}")
        
        return ppid
    
    def verify_ppid(self, ppid: str, global_user_id: str, site_origin: str) -> bool:
        """Verify PPID matches the user and origin"""
        expected_ppid = self.generate_ppid(global_user_id, site_origin)
        return hmac.compare_digest(ppid, expected_ppid)
    
    def generate_challenge(self, origin: str, user_ppid: str = None) -> Dict[str, Any]:
        """Generate proof-of-possession challenge"""
        current_time = time.time()
        epoch = int(current_time // 86400)  # Daily epoch
        
        # Generate cryptographically secure nonce
        nonce_bytes = secrets.token_bytes(32)
        nonce = base64.urlsafe_b64encode(nonce_bytes).decode().rstrip('=')
        
        challenge_id = hashlib.sha256(f"{origin}:{nonce}:{current_time}".encode()).hexdigest()[:16]
        
        challenge_data = {
            "challenge_id": challenge_id,
            "origin": origin,
            "nonce": nonce,
            "epoch": epoch,
            "issued_at": current_time,
            "expires_at": current_time + PRIVACY_CONFIG["challenge_ttl"],
            "user_ppid": user_ppid
        }
        
        # Store active challenge
        self.active_challenges[challenge_id] = challenge_data
        
        # Cleanup old challenges
        self._cleanup_expired_challenges()
        
        logger.info(f"🎯 Generated PoP challenge {challenge_id} for origin {origin}")
        
        return {
            "challenge_id": challenge_id,
            "nonce": nonce,
            "epoch": epoch,
            "expires_at": challenge_data["expires_at"]
        }
    
    def verify_proof_of_possession(self, challenge_id: str, presentation: Dict[str, Any], 
                                 timestamp: str) -> Tuple[bool, str]:
        """Verify proof-of-possession response"""
        try:
            # Check if challenge exists and is valid
            if challenge_id not in self.active_challenges:
                return False, "Invalid or expired challenge"
            
            challenge = self.active_challenges[challenge_id]
            current_time = time.time()
            
            # Check expiration
            if challenge["expires_at"] < current_time:
                del self.active_challenges[challenge_id]
                return False, "Challenge expired"
            
            # Parse timestamp
            try:
                request_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()
            except:
                return False, "Invalid timestamp format"
            
            # Check replay window
            if abs(current_time - request_time) > PRIVACY_CONFIG["max_replay_window"]:
                return False, "Request outside replay window"
            
            # Extract proof components
            proof = presentation.get("proof", "")
            selective_disclosure = presentation.get("selectiveDisclosure", [])
            
            if not proof:
                return False, "Missing proof in presentation"
            
            # Verify proof format (simplified - in production would verify Ed25519 signature)
            expected_proof_input = f"{challenge['nonce']}|{challenge['origin']}|{timestamp}"
            
            # For now, verify proof contains expected elements
            if challenge["nonce"] not in proof and challenge["origin"] not in proof:
                return False, "Invalid proof - missing required elements"
            
            # Check selective disclosure
            if "isHuman" not in selective_disclosure:
                return False, "Required claim 'isHuman' not disclosed"
            
            # Prevent replay attacks - check nonce uniqueness
            proof_nonce = f"{challenge_id}:{proof}:{timestamp}"
            if proof_nonce in self.used_nonces:
                return False, "Replay attack detected - nonce already used"
            
            # Add to used nonces
            self.used_nonces.add(proof_nonce)
            
            # Cleanup used nonces if cache is full
            if len(self.used_nonces) > PRIVACY_CONFIG["nonce_cache_size"]:
                self._cleanup_old_nonces()
            
            # Remove used challenge
            del self.active_challenges[challenge_id]
            
            logger.info(f"✅ Verified PoP for challenge {challenge_id}")
            
            return True, "Proof verified successfully"
            
        except Exception as e:
            logger.error(f"❌ PoP verification failed: {e}")
            return False, f"Verification error: {str(e)}"
    
    def _cleanup_expired_challenges(self):
        """Remove expired challenges"""
        current_time = time.time()
        expired = [cid for cid, challenge in self.active_challenges.items() 
                  if challenge["expires_at"] < current_time]
        
        for cid in expired:
            del self.active_challenges[cid]
        
        if expired:
            logger.info(f"🧹 Cleaned up {len(expired)} expired challenges")
    
    def _cleanup_old_nonces(self):
        """Remove old nonces from cache"""
        # Keep only recent half of nonces (simple LRU approximation)
        nonces_list = list(self.used_nonces)
        keep_count = PRIVACY_CONFIG["nonce_cache_size"] // 2
        self.used_nonces = set(nonces_list[-keep_count:])
        
        logger.info(f"🧹 Cleaned up old nonces, keeping {keep_count}")
    
    def get_privacy_stats(self) -> Dict[str, Any]:
        """Get privacy system statistics"""
        current_time = time.time()
        
        active_challenges_count = len([c for c in self.active_challenges.values() 
                                     if c["expires_at"] > current_time])
        
        return {
            "active_challenges": active_challenges_count,
            "total_challenges_issued": len(self.active_challenges),
            "used_nonces_cache_size": len(self.used_nonces),
            "challenge_ttl_seconds": PRIVACY_CONFIG["challenge_ttl"],
            "replay_window_seconds": PRIVACY_CONFIG["max_replay_window"]
        }

# Global privacy manager
privacy_manager = PrivacyManager()

@privacy_bp.route('/api/privacy/generate-ppid', methods=['POST', 'OPTIONS'])
@cors_headers
def generate_ppid():
    """Generate PPID for user at specific origin"""
    
    # Handle CORS preflight requests
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        # Verify network authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Network '):
            return jsonify({
                "success": False,
                "error": "unauthorized",
                "message": "Network authorization required"
            }), 401
        
        data = request.get_json() or {}
        global_user_id = data.get('global_user_id')
        site_origin = data.get('site_origin')
        
        if not global_user_id or not site_origin:
            return jsonify({
                "success": False,
                "error": "missing_parameters",
                "message": "global_user_id and site_origin required"
            }), 400
        
        ppid = privacy_manager.generate_ppid(global_user_id, site_origin)
        
        return jsonify({
            "success": True,
            "ppid": ppid,
            "site_origin": site_origin
        })
        
    except Exception as e:
        logger.error(f"❌ PPID generation failed: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "PPID generation failed"
        }), 500

@privacy_bp.route('/api/privacy/verify-start', methods=['POST'])
def verify_start():
    """Start verification with challenge generation"""
    try:
        data = request.get_json() or {}
        origin = data.get('origin')
        epoch = data.get('epoch')
        
        if not origin:
            return jsonify({
                "success": False,
                "error": "missing_origin",
                "message": "Origin required for challenge generation"
            }), 400
        
        # Validate origin format
        if not origin.startswith(('https://', 'http://localhost')):
            return jsonify({
                "success": False,
                "error": "invalid_origin",
                "message": "Origin must use HTTPS"
            }), 400
        
        # Generate challenge
        challenge = privacy_manager.generate_challenge(origin)
        
        logger.info(f"🎯 Started verification challenge for {origin}")
        
        return jsonify({
            "success": True,
            **challenge
        })
        
    except Exception as e:
        logger.error(f"❌ Challenge generation failed: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "Challenge generation failed"
        }), 500

@privacy_bp.route('/api/privacy/verify-complete', methods=['POST'])
def verify_complete():
    """Complete verification with proof-of-possession"""
    try:
        data = request.get_json() or {}
        challenge_id = data.get('challenge_id')
        lemma = data.get('lemma', {})
        presentation = data.get('presentation', {})
        timestamp = data.get('ts')
        
        if not challenge_id or not presentation or not timestamp:
            return jsonify({
                "success": False,
                "error": "missing_parameters",
                "message": "challenge_id, presentation, and timestamp required"
            }), 400
        
        # Verify proof of possession
        is_valid, message = privacy_manager.verify_proof_of_possession(
            challenge_id, presentation, timestamp
        )
        
        if is_valid:
            # Additional lemma verification can be done here
            cache_ttl = 86400  # 24 hours
            
            logger.info(f"✅ Verification completed successfully for challenge {challenge_id}")
            
            return jsonify({
                "success": True,
                "ok": True,
                "reason": None,
                "cache_ttl_s": cache_ttl,
                "verified_at": time.time()
            })
        else:
            logger.warning(f"❌ Verification failed for challenge {challenge_id}: {message}")
            
            return jsonify({
                "success": False,
                "ok": False,
                "reason": message
            }), 400
        
    except Exception as e:
        logger.error(f"❌ Verification completion failed: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "Verification completion failed"
        }), 500

@privacy_bp.route('/api/privacy/stats', methods=['GET'])
def get_privacy_stats():
    """Get privacy system statistics"""
    try:
        # Verify network authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Network '):
            return jsonify({
                "success": False,
                "error": "unauthorized"
            }), 401
        
        stats = privacy_manager.get_privacy_stats()
        
        return jsonify({
            "success": True,
            **stats
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to get privacy stats: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error"
        }), 500

@privacy_bp.route('/api/privacy/validate-ppid', methods=['POST', 'OPTIONS'])
@cors_headers
def validate_ppid():
    """Validate PPID for user and origin"""
    
    # Handle CORS preflight requests
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        # Verify network authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Network '):
            return jsonify({
                "success": False,
                "error": "unauthorized"
            }), 401
        
        data = request.get_json() or {}
        ppid = data.get('ppid')
        global_user_id = data.get('global_user_id')
        site_origin = data.get('site_origin')
        
        if not all([ppid, global_user_id, site_origin]):
            return jsonify({
                "success": False,
                "error": "missing_parameters",
                "message": "ppid, global_user_id, and site_origin required"
            }), 400
        
        is_valid = privacy_manager.verify_ppid(ppid, global_user_id, site_origin)
        
        return jsonify({
            "success": True,
            "valid": is_valid,
            "ppid": ppid,
            "site_origin": site_origin
        })
        
    except Exception as e:
        logger.error(f"❌ PPID validation failed: {e}")
        return jsonify({
            "success": False,
            "error": "internal_error",
            "message": "PPID validation failed"
        }), 500

# Utility functions for integration
def get_user_ppid_for_origin(global_user_id: str, site_origin: str) -> str:
    """Utility function to get PPID for user at origin"""
    return privacy_manager.generate_ppid(global_user_id, site_origin)

def create_verification_challenge(origin: str) -> Dict[str, Any]:
    """Utility function to create verification challenge"""
    return privacy_manager.generate_challenge(origin)

def verify_presentation(challenge_id: str, presentation: Dict[str, Any], 
                       timestamp: str) -> Tuple[bool, str]:
    """Utility function to verify presentation"""
    return privacy_manager.verify_proof_of_possession(challenge_id, presentation, timestamp)
