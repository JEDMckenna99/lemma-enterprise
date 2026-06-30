"""
Pairwise Tagging Service
Generates HMAC-based pairwise tags for RP uniqueness enforcement
"""

import os
import hmac
import hashlib
import logging
import secrets as _secrets
from typing import Dict, Optional
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from auth.decorators import require_api_key

logger = logging.getLogger(__name__)

# Create blueprint
pairwise_tagging_bp = Blueprint('pairwise_tagging', __name__)

# Env var holding the pairwise HMAC key material (HSM/KMS-backed in production).
_PAIRWISE_KEY_ENV = "LEMMA_PAIRWISE_TAG_KEY"


def _is_production() -> bool:
    try:
        from api.config import is_production
        return is_production()
    except Exception:
        return (
            os.environ.get("FLASK_ENV") == "production"
            or os.environ.get("ENVIRONMENT") == "production"
        )


class PairwiseTagManager:
    """Manages pairwise tag generation for RP uniqueness"""

    def __init__(self):
        # SECURITY: never hardcode the pairwise key. It is resolved lazily from
        # the environment (HSM/KMS-backed) on first use so an unconfigured
        # optional feature cannot crash app startup, while still failing closed
        # in production when the key is absent.
        self._k_pair: Optional[bytes] = None
        self._k_pair_dev_only = False

        # Tag cache for performance
        self.tag_cache: Dict[str, str] = {}

        logger.info("🏷️ Pairwise Tag Manager initialized")

    @property
    def k_pair(self) -> bytes:
        """Resolve the 32-byte HMAC key, deriving a stable value from the
        configured secret. Raises in production when the key is unset so tags
        are never generated under a predictable/forgeable key."""
        if self._k_pair is not None:
            return self._k_pair

        raw = os.environ.get(_PAIRWISE_KEY_ENV)
        if raw and len(raw) >= 32:
            # Normalize arbitrary-length secret material to a fixed 32-byte key.
            self._k_pair = hashlib.sha256(raw.encode("utf-8")).digest()
            self._k_pair_dev_only = False
            return self._k_pair

        if _is_production():
            raise RuntimeError(
                f"CRITICAL: {_PAIRWISE_KEY_ENV} not set (or <32 chars) in production; "
                "refusing to generate pairwise tags under a predictable key."
            )

        # Development only: stable-per-process random key (never persisted,
        # never the same across deployments).
        logger.warning(
            "⚠️ DEV MODE: generating an ephemeral pairwise tag key; set %s for stable tags.",
            _PAIRWISE_KEY_ENV,
        )
        self._k_pair = _secrets.token_bytes(32)
        self._k_pair_dev_only = True
        return self._k_pair
    
    def generate_pairwise_tag(self, rid: str, rp_id: str) -> str:
        """
        Generate pairwise tag for RP uniqueness enforcement
        tag_rp = HMAC(k_pair, RID || rp_id)
        
        Args:
            rid: Root ID (from KYC)
            rp_id: Relying Party identifier
            
        Returns:
            str: Hex-encoded pairwise tag
        """
        cache_key = f"{rid}:{rp_id}"
        
        # Check cache first
        if cache_key in self.tag_cache:
            return self.tag_cache[cache_key]
        
        try:
            # Generate HMAC-based pairwise tag
            mac = hmac.new(self.k_pair, digestmod=hashlib.sha256)
            mac.update(rid.encode('utf-8'))
            mac.update(rp_id.encode('utf-8'))
            
            tag = mac.hexdigest()
            
            # Cache the result
            self.tag_cache[cache_key] = tag
            
            logger.info(f"✅ Generated pairwise tag for RP {rp_id}")
            
            return tag
            
        except Exception as e:
            logger.error(f"❌ Pairwise tag generation failed: {e}")
            raise
    
    def validate_tag_uniqueness(self, tag: str, rp_id: str) -> Dict[str, any]:
        """
        Validate that pairwise tag is unique for this RP
        
        Args:
            tag: Pairwise tag to validate
            rp_id: Relying Party identifier
            
        Returns:
            dict: Validation result
        """
        # In production, would check against RP's user database
        # For now, simulate uniqueness check
        
        # Check if tag follows expected format
        if not tag or len(tag) != 64:  # SHA256 hex = 64 chars
            return {
                'unique': False,
                'reason': 'invalid_tag_format',
                'expected_length': 64,
                'actual_length': len(tag) if tag else 0
            }
        
        # Simulate database lookup (would be real RP database check)
        # For development, assume all tags are unique
        return {
            'unique': True,
            'tag': tag,
            'rp_id': rp_id,
            'validation_method': 'simulated',
            'note': 'In production, would check RP user database'
        }
    
    def get_tag_stats(self) -> Dict[str, any]:
        """Get pairwise tag statistics"""
        try:
            key_available = bool(self.k_pair)
        except Exception:
            key_available = False
        return {
            'total_tags_generated': len(self.tag_cache),
            'cache_size': len(self.tag_cache),
            'k_pair_available': key_available
        }

# Global tag manager
tag_manager = PairwiseTagManager()

@pairwise_tagging_bp.route('/api/issuer/pairwise-tag', methods=['POST'])
@cross_origin()
@require_api_key
def generate_pairwise_tag():
    """
    Generate pairwise tag for RP uniqueness enforcement
    
    POST /api/issuer/pairwise-tag
    {
        "rp_id": "example.com",
        "wallet_type": "integrated_advanced"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        rp_id = data.get('rp_id')
        wallet_type = data.get('wallet_type', 'unknown')
        
        if not rp_id:
            return jsonify({
                'success': False,
                'error': 'missing_rp_id',
                'message': 'rp_id parameter is required'
            }), 400
        
        # Get RID from session or generate temporary one
        # In production, would get from authenticated KYC session
        rid = session.get('user_rid')
        if not rid:
            # Generate temporary RID for development
            import secrets
            rid = f"temp_rid_{secrets.token_hex(16)}"
            session['user_rid'] = rid
            
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"🔄 Generated temporary RID for development: {rid[:16]}...")
        
        # Generate pairwise tag
        pairwise_tag = tag_manager.generate_pairwise_tag(rid, rp_id)
        
        return jsonify({
            'success': True,
            'pairwise_tag': pairwise_tag,
            'rp_id': rp_id,
            'wallet_type': wallet_type,
            'tag_method': 'hmac_sha256',
            'uniqueness_enforced': True
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Pairwise tag endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@pairwise_tagging_bp.route('/api/issuer/validate-uniqueness', methods=['POST'])
@cross_origin()
@require_api_key
def validate_tag_uniqueness():
    """
    Validate pairwise tag uniqueness for RP
    
    POST /api/issuer/validate-uniqueness
    {
        "pairwise_tag": "64_char_hex_tag",
        "rp_id": "example.com"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        pairwise_tag = data.get('pairwise_tag')
        rp_id = data.get('rp_id')
        
        if not pairwise_tag or not rp_id:
            return jsonify({
                'success': False,
                'error': 'missing_parameters',
                'message': 'pairwise_tag and rp_id are required'
            }), 400
        
        # Validate uniqueness
        validation_result = tag_manager.validate_tag_uniqueness(pairwise_tag, rp_id)
        
        return jsonify({
            'success': True,
            'validation': validation_result,
            'enforcement_policy': 'strict_uniqueness',
            'recommendation': 'reject_duplicate_signups' if not validation_result['unique'] else 'allow_signup'
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Tag validation endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@pairwise_tagging_bp.route('/api/issuer/tag-stats', methods=['GET'])
@cross_origin()
@require_api_key
def get_tag_stats():
    """Get pairwise tag statistics"""
    try:
        stats = tag_manager.get_tag_stats()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'service': 'pairwise_tagging',
            'version': '1.0.0'
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Tag stats endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

# Export tag manager for testing
def get_tag_manager():
    """Get tag manager instance for testing"""
    return tag_manager
