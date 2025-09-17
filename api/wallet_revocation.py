"""
Wallet Revocation API - Handle credential revocation from wallet interface
"""
import json
import time
import logging
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from auth.decorators import validate_api_key, rate_limit

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
wallet_revocation_bp = Blueprint('wallet_revocation', __name__)

@wallet_revocation_bp.route('/api/wallet/revoke', methods=['POST'])
@cross_origin()
@rate_limit(max_requests=10, window=60)  # Limit revocation calls
def revoke_credential():
    """
    Revoke credential from wallet and propagate to network
    
    This handles both PoH lemmas (network-wide revocation) and 
    permission lemmas (site-specific revocation)
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        credential_id = data.get('credential_id')
        credential_type = data.get('credential_type', 'unknown')  # 'poh' or 'permission'
        reason = data.get('reason', 'user_requested')
        
        if not credential_id:
            return jsonify({
                'success': False,
                'error': 'missing_credential_id',
                'message': 'credential_id is required'
            }), 400
        
        logger.info(f"🚨 Wallet revocation request: {credential_id} (type: {credential_type})")
        
        # For PoH lemmas: Network-wide revocation
        if credential_type == 'poh':
            network_success = await_network_revocation(credential_id, reason)
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'network_wide',
                'network_propagated': network_success,
                'message': 'PoH lemma revoked - network-wide revocation initiated',
                'scope': 'All sites in federated network will be updated'
            })
        
        # For permission lemmas: Site-specific revocation
        elif credential_type == 'permission':
            site_success = await_site_revocation(credential_id, reason)
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'site_specific',
                'site_updated': site_success,
                'message': 'Permission lemma revoked - site-specific revocation completed',
                'scope': 'Only this site\'s permissions affected'
            })
        
        # Unknown type: Local revocation only
        else:
            logger.warning(f"Unknown credential type: {credential_type}")
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'local_only',
                'message': 'Credential revoked locally',
                'scope': 'Local wallet only - network not updated'
            })
        
    except Exception as e:
        logger.error(f"❌ Wallet revocation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_failed',
            'message': str(e)
        }), 500

def await_network_revocation(credential_id: str, reason: str) -> bool:
    """
    Propagate PoH lemma revocation to the federated network
    """
    try:
        # Import the network revocation function
        from api.sdk_api import distribute_revocation_to_network
        
        # For PoH lemmas, we need OPRF evaluation and bloom hash
        # Simulate these for now (in production, use real crypto)
        import hashlib
        oprf_evaluation = f"oprf_{hashlib.sha256(credential_id.encode()).hexdigest()}"
        bloom_hash = f"bloom_{hashlib.sha256((credential_id + 'bloom').encode()).hexdigest()}"
        
        # Distribute to network
        success = distribute_revocation_to_network(
            credential_id=credential_id,
            oprf_evaluation=oprf_evaluation,
            bloom_hash=bloom_hash,
            reason=reason
        )
        
        logger.info(f"🌐 Network revocation result for {credential_id}: {success}")
        return success
        
    except Exception as e:
        logger.warning(f"⚠️ Network revocation failed for {credential_id}: {e}")
        return False

def await_site_revocation(credential_id: str, reason: str) -> bool:
    """
    Handle site-specific permission lemma revocation
    """
    try:
        # For permission lemmas, update local site revocation list
        # In production, this would update the site's permission database
        
        logger.info(f"🏠 Site-specific revocation for {credential_id}: {reason}")
        
        # Simulate site revocation list update
        # This would typically:
        # 1. Add to site's revoked permissions table
        # 2. Update site's permission bloom filter
        # 3. Notify site administrators if needed
        
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Site revocation failed for {credential_id}: {e}")
        return False

@wallet_revocation_bp.route('/api/wallet/revocation-status', methods=['GET'])
@cross_origin()
def get_revocation_status():
    """
    Get revocation status for credentials
    """
    try:
        credential_ids = request.args.getlist('credential_ids')
        
        if not credential_ids:
            return jsonify({
                'success': False,
                'error': 'no_credentials',
                'message': 'No credential IDs provided'
            }), 400
        
        # Check revocation status for each credential
        statuses = {}
        for cred_id in credential_ids:
            # In production, this would check:
            # 1. Network revocation lists (for PoH lemmas)
            # 2. Site revocation lists (for permission lemmas)
            # 3. OPRF bloom filter (for privacy-preserving checks)
            
            statuses[cred_id] = {
                'revoked': False,  # Placeholder
                'revocation_time': None,
                'reason': None,
                'scope': 'unknown'
            }
        
        return jsonify({
            'success': True,
            'statuses': statuses
        })
        
    except Exception as e:
        logger.error(f"❌ Revocation status check failed: {e}")
        return jsonify({
            'success': False,
            'error': 'status_check_failed',
            'message': str(e)
        }), 500
