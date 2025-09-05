"""
Network Revocation System for Federated Identity (PoH) Credentials
Manages network-wide revocation of personhood credentials for bot protection
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import os
import time
import secrets
from datetime import datetime, timedelta

from .database import get_db, UserLemma, Customer
from .network_registry import NETWORK_REGISTRY

logger = logging.getLogger(__name__)

network_revocation_bp = Blueprint('network_revocation', __name__)

class NetworkRevocationManager:
    """Manages network-wide revocation of federated identity (PoH) credentials"""
    
    def __init__(self):
        self.revocation_cache = {}
    
    def revoke_personhood_credential(self, user_did, reason, evidence=None):
        """
        Revoke personhood credential across the entire network
        
        This removes the user's "proof of humanness" from the federated identity network,
        effectively marking them as a bot/malicious actor across ALL sites using the network.
        """
        
        current_time = time.time()
        revocation_id = f"poh_revoke_{secrets.token_hex(16)}"
        
        try:
            db = get_db()
            
            # Find all identity lemmas for this user
            identity_lemmas = db.query(UserLemma).filter(
                UserLemma.user_did == user_did,
                UserLemma.lemma_type == 'identity',
                UserLemma.revoked_at.is_(None)  # Not already revoked
            ).all()
            
            revoked_lemmas = []
            
            for lemma in identity_lemmas:
                # Mark as revoked in database
                lemma.revoked_at = datetime.utcnow()
                lemma.revocation_reason = reason
                lemma.revocation_id = revocation_id
                
                revoked_lemmas.append({
                    'lemma_id': lemma.id,
                    'user_did': lemma.user_did,
                    'site_id': lemma.site_id,
                    'revoked_at': current_time
                })
            
            db.commit()
            
            # Add to network-wide revocation registry
            revocation_entry = {
                'revocation_id': revocation_id,
                'user_did': user_did,
                'revocation_type': 'personhood_credential',
                'revoked_at': current_time,
                'reason': reason,
                'evidence': evidence,
                'network_scope': 'global',
                'revoked_lemmas': revoked_lemmas,
                'propagated_to_sites': True
            }
            
            # Add to global network registry for immediate propagation
            NETWORK_REGISTRY['revocation_lists']['revocation_entries'][user_did] = revocation_entry
            
            # Add to OPRF bloom filter for fast checking
            user_hash = self._generate_user_hash(user_did)
            NETWORK_REGISTRY['revocation_lists']['oprf_bloom_filters'][user_hash] = {
                'bloom_hash': user_hash,
                'added_at': current_time,
                'network_level': 'global',
                'revocation_type': 'personhood'
            }
            
            # Update network metadata
            NETWORK_REGISTRY['revocation_lists']['last_updated'] = current_time
            NETWORK_REGISTRY['network_metadata']['total_revocations'] = len(
                NETWORK_REGISTRY['revocation_lists']['revocation_entries']
            )
            
            db.close()
            
            logger.info(f"🚫 Network-wide personhood revocation: {user_did} (reason: {reason})")
            
            return {
                'success': True,
                'revocation_id': revocation_id,
                'revoked_lemmas': len(revoked_lemmas),
                'network_propagation': 'immediate',
                'effect': 'user_marked_as_bot_across_network'
            }
            
        except Exception as e:
            if 'db' in locals():
                db.close()
            logger.error(f"❌ Network revocation failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def force_remove_from_wallet(self, user_did, reason):
        """
        Attempt to force remove PoH credential from user's wallet
        This sends a removal command to the user's wallet (if online)
        """
        
        removal_command = {
            'action': 'force_remove_poh_credential',
            'user_did': user_did,
            'authority': 'did:lemma:federated:issuer',
            'reason': reason,
            'network_revocation': True,
            'timestamp': time.time()
        }
        
        # Add to immediate removal queue (processed by wallet on next sync)
        NETWORK_REGISTRY['immediate_removals'] = NETWORK_REGISTRY.get('immediate_removals', {})
        NETWORK_REGISTRY['immediate_removals'][user_did] = removal_command
        
        logger.info(f"🗑️ Queued PoH credential for forced removal: {user_did}")
        
        return {
            'success': True,
            'removal_queued': True,
            'effect': 'credential_removed_on_next_wallet_sync'
        }
    
    def _generate_user_hash(self, user_did):
        """Generate hash for OPRF bloom filter"""
        import hashlib
        return hashlib.sha256(user_did.encode()).hexdigest()[:16]

# Global manager instance
network_revocation_manager = NetworkRevocationManager()

@network_revocation_bp.route('/api/network/revoke-personhood', methods=['POST'])
@cross_origin()
def revoke_personhood_credential():
    """
    Revoke personhood credential across the entire federated network
    
    POST /api/network/revoke-personhood
    {
        "user_did": "did:lemma:federated:user:malicious_actor",
        "reason": "bot_activity_detected",
        "evidence": "automated_signup_pattern",
        "admin_password": ".511MeV/c^2"
    }
    """
    try:
        data = request.get_json()
        user_did = data.get('user_did', '')
        reason = data.get('reason', 'network_admin_revocation')
        evidence = data.get('evidence', '')
        admin_password = data.get('admin_password', '')
        
        # Verify admin password
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', '.511MeV/c^2')
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        if not user_did:
            return jsonify({
                'success': False,
                'error': 'User DID is required'
            }), 400
        
        logger.info(f"🚫 Network personhood revocation requested: {user_did} (reason: {reason})")
        
        # Revoke across the network
        result = network_revocation_manager.revoke_personhood_credential(
            user_did=user_did,
            reason=reason,
            evidence=evidence
        )
        
        if result['success']:
            # Also attempt forced removal from wallet
            removal_result = network_revocation_manager.force_remove_from_wallet(
                user_did=user_did,
                reason=f"network_revocation_{reason}"
            )
            
            return jsonify({
                'success': True,
                'revocation_id': result['revocation_id'],
                'revoked_lemmas': result['revoked_lemmas'],
                'network_effect': 'immediate_bot_marking_across_all_sites',
                'wallet_removal': 'queued_for_next_sync',
                'propagation': 'all_network_sites',
                'user_status': 'marked_as_bot_network_wide'
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 500
        
    except Exception as e:
        logger.error(f"❌ Network revocation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@network_revocation_bp.route('/api/network/check-personhood-status', methods=['POST'])
@cross_origin()
def check_personhood_status():
    """
    Check if a user's personhood credential has been revoked
    Used by sites to verify if a user is still considered human
    """
    try:
        data = request.get_json()
        user_did = data.get('user_did', '')
        
        if not user_did:
            return jsonify({
                'success': False,
                'error': 'User DID is required'
            }), 400
        
        # Check revocation registry
        revocation_data = NETWORK_REGISTRY['revocation_lists']['revocation_entries']
        
        if user_did in revocation_data:
            revocation_info = revocation_data[user_did]
            return jsonify({
                'success': True,
                'revoked': True,
                'revoked_at': revocation_info['revoked_at'],
                'reason': revocation_info['reason'],
                'network_status': 'marked_as_bot',
                'verification_result': 'should_block_user'
            })
        else:
            return jsonify({
                'success': True,
                'revoked': False,
                'network_status': 'verified_human',
                'verification_result': 'allow_user_access'
            })
        
    except Exception as e:
        logger.error(f"❌ Personhood status check error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@network_revocation_bp.route('/api/network/revocation-stats', methods=['GET'])
@cross_origin()
def get_network_revocation_stats():
    """Get network-wide revocation statistics"""
    try:
        revocation_data = NETWORK_REGISTRY['revocation_lists']
        
        # Count different types of revocations
        personhood_revocations = 0
        bot_activity_revocations = 0
        admin_revocations = 0
        
        for entry in revocation_data['revocation_entries'].values():
            if entry.get('revocation_type') == 'personhood_credential':
                personhood_revocations += 1
                
            reason = entry.get('reason', '')
            if 'bot' in reason.lower():
                bot_activity_revocations += 1
            elif 'admin' in reason.lower():
                admin_revocations += 1
        
        return jsonify({
            'success': True,
            'network_revocation_stats': {
                'total_revocations': len(revocation_data['revocation_entries']),
                'personhood_revocations': personhood_revocations,
                'bot_activity_revocations': bot_activity_revocations,
                'admin_revocations': admin_revocations,
                'last_updated': revocation_data.get('last_updated', 0),
                'bloom_filter_entries': len(revocation_data.get('oprf_bloom_filters', {}))
            },
            'network_health': {
                'revocation_rate': personhood_revocations / max(len(NETWORK_REGISTRY['did_registry']), 1),
                'bot_detection_active': bot_activity_revocations > 0,
                'network_integrity': 'high' if personhood_revocations < 100 else 'medium'
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Network revocation stats error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@network_revocation_bp.route('/api/wallet/check-removal-queue', methods=['POST'])
@cross_origin()
def check_wallet_removal_queue():
    """
    Check if there are any PoH credentials queued for removal from user's wallet
    Called by user's wallet on sync
    """
    try:
        data = request.get_json()
        user_did = data.get('user_did', '')
        
        if not user_did:
            return jsonify({
                'success': False,
                'error': 'User DID is required'
            }), 400
        
        # Check immediate removal queue
        immediate_removals = NETWORK_REGISTRY.get('immediate_removals', {})
        
        if user_did in immediate_removals:
            removal_command = immediate_removals[user_did]
            
            # Remove from queue (one-time command)
            del immediate_removals[user_did]
            
            return jsonify({
                'success': True,
                'removal_required': True,
                'removal_command': removal_command,
                'reason': removal_command['reason'],
                'authority': removal_command['authority']
            })
        else:
            return jsonify({
                'success': True,
                'removal_required': False
            })
        
    except Exception as e:
        logger.error(f"❌ Wallet removal queue check error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
