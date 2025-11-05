"""
OPRF Evaluation API
===================
Server-side OPRF evaluation for privacy-preserving revocation checking

The server evaluates blinded points without learning the credential ID.
"""

import logging
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

oprf_eval_bp = Blueprint('oprf_eval', __name__)

# Global OPRF server instance (initialized on first use)
_oprf_server = None

def get_oprf_server():
    """Get or create global OPRF server instance"""
    global _oprf_server
    if _oprf_server is None:
        try:
            from lemma_crypto import PyOPRFServer
            _oprf_server = PyOPRFServer()
            logger.info("✅ OPRF server initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OPRF server: {e}")
            raise
    return _oprf_server


@oprf_eval_bp.route('/api/oprf/evaluate', methods=['POST'])
@cross_origin()
def evaluate_oprf():
    """
    Evaluate OPRF on a blinded point (server-side)
    
    POST /api/oprf/evaluate
    {
        "blinded": "hex-encoded blinded point from client"
    }
    
    Returns:
    {
        "success": true,
        "evaluated": "hex-encoded evaluated point",
        "server_public_key": "optional: for client verification"
    }
    
    Privacy guarantee:
    - Server receives only the blinded point
    - Server cannot determine the original credential ID
    - Client unblinds locally to get final OPRF output
    """
    try:
        data = request.json
        
        if not data or 'blinded' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing blinded point'
            }), 400
        
        blinded_hex = data['blinded']
        
        # Validate hex format
        if not isinstance(blinded_hex, str) or len(blinded_hex) != 64:
            return jsonify({
                'success': False,
                'error': 'Invalid blinded point format (expected 64-char hex)'
            }), 400
        
        # Get OPRF server
        oprf_server = get_oprf_server()
        
        # Evaluate OPRF
        evaluated_hex = oprf_server.evaluate(blinded_hex)
        
        logger.info(f"📡 OPRF evaluated: {blinded_hex[:16]}... -> {evaluated_hex[:16]}...")
        
        return jsonify({
            'success': True,
            'evaluated': evaluated_hex,
            # Optionally include server public key for verification
            # 'server_public_key': oprf_server.get_public_key_hex()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ OPRF evaluation error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'OPRF evaluation failed'
        }), 500


@oprf_eval_bp.route('/api/oprf/batch-evaluate', methods=['POST'])
@cross_origin()
def batch_evaluate_oprf():
    """
    Batch evaluate multiple blinded points
    
    POST /api/oprf/batch-evaluate
    {
        "blinded_list": ["hex1", "hex2", "hex3", ...]
    }
    
    Returns:
    {
        "success": true,
        "evaluated_list": ["eval1", "eval2", "eval3", ...],
        "count": 3
    }
    """
    try:
        data = request.json
        
        if not data or 'blinded_list' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing blinded_list'
            }), 400
        
        blinded_list = data['blinded_list']
        
        if not isinstance(blinded_list, list):
            return jsonify({
                'success': False,
                'error': 'blinded_list must be an array'
            }), 400
        
        # Limit batch size
        MAX_BATCH_SIZE = 100
        if len(blinded_list) > MAX_BATCH_SIZE:
            return jsonify({
                'success': False,
                'error': f'Batch size limited to {MAX_BATCH_SIZE}'
            }), 400
        
        # Get OPRF server
        oprf_server = get_oprf_server()
        
        # Batch evaluate
        evaluated_list = oprf_server.batch_evaluate(blinded_list)
        
        logger.info(f"📡 OPRF batch evaluated: {len(blinded_list)} points")
        
        return jsonify({
            'success': True,
            'evaluated_list': evaluated_list,
            'count': len(evaluated_list)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ OPRF batch evaluation error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'OPRF batch evaluation failed'
        }), 500


@oprf_eval_bp.route('/api/oprf/server-info', methods=['GET'])
@cross_origin()
def oprf_server_info():
    """
    Get OPRF server information (for debugging/monitoring)
    
    GET /api/oprf/server-info
    
    Returns:
    {
        "success": true,
        "oprf_enabled": true,
        "server_public_key": "hex-encoded public key (optional)"
    }
    """
    try:
        oprf_server = get_oprf_server()
        
        return jsonify({
            'success': True,
            'oprf_enabled': True,
            'privacy_mechanism': 'client_blind_server_evaluate_client_unblind',
            'zero_knowledge': True,
            # Optionally include server public key
            # 'server_public_key': oprf_server.get_public_key_hex()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ OPRF server info error: {e}")
        return jsonify({
            'success': False,
            'oprf_enabled': False,
            'error': str(e)
        }), 500

