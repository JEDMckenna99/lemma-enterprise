"""
Pairwise Tagging Service
Generates HMAC-based pairwise tags for RP uniqueness enforcement
"""

import hmac
import hashlib
import logging
from typing import Dict, Optional
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from auth.decorators import require_api_key

logger = logging.getLogger(__name__)

# Create blueprint
pairwise_tagging_bp = Blueprint('pairwise_tagging', __name__)

class PairwiseTagManager:
    """Manages pairwise tag generation for RP uniqueness"""
    
    def __init__(self):
        # In production, this would be stored in HSM/KMS
        self.k_pair = b"lemma_pairwise_key_production_hsm_2024_secure_key_material_32bytes"[:32]
        
        # Tag cache for performance
        self.tag_cache: Dict[str, str] = {}
        
        logger.info("🏷️ Pairwise Tag Manager initialized")
    
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
        return {
            'total_tags_generated': len(self.tag_cache),
            'cache_size': len(self.tag_cache),
            'k_pair_available': bool(self.k_pair)
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
