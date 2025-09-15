"""
Network Client Configuration API
Provides configuration for federated wallet and bot shield clients
"""

import os
from flask import Blueprint, jsonify
from flask_cors import cross_origin
import logging

logger = logging.getLogger(__name__)

# Create blueprint
network_client_config_bp = Blueprint('network_client_config', __name__)

@network_client_config_bp.route('/api/network/client-config', methods=['GET'])
@cross_origin()
def get_client_config():
    """
    Get client configuration for federated wallet and bot shield
    """
    try:
        config = {
            'success': True,
            'network_config': {
                'registry_url': '/api/network-registry',
                'sync_url': '/api/network/sync',
                'privacy_url': '/api/privacy',
                'auth_key': 'lemma_network_federated_sync_2024'
            },
            'shield_config': {
                'api_key': os.environ.get('LEMMA_PLATFORM_API_KEY', 'lemma_platform_production_key_2024'),
                'security_level': 'medium',
                'check_interval': 300000,  # 5 minutes
                'offline_mode': True
            },
            'wallet_config': {
                'storage_layers': ['memory', 'indexeddb', 'localstorage'],
                'sync_interval': 30000,  # 30 seconds
                'background_checks': True
            }
        }
        
        logger.info("✅ Client config provided")
        return jsonify(config), 200
        
    except Exception as e:
        logger.error(f"❌ Client config error: {e}")
        return jsonify({
            'success': False,
            'error': 'config_error',
            'message': 'Failed to get client configuration'
        }), 500

@network_client_config_bp.route('/api/privacy/generate-ppid', methods=['POST'])
@cross_origin()
def generate_ppid():
    """
    Generate privacy-preserving identifier for user tracking
    """
    try:
        from flask import request
        import hashlib
        import secrets
        
        # Generate privacy-preserving ID
        salt = secrets.token_bytes(16)
        user_agent = request.headers.get('User-Agent', 'unknown')
        origin = request.headers.get('Origin', 'unknown')
        
        # Create deterministic but private identifier
        ppid_data = f"{origin}|{user_agent}|{salt.hex()}"
        ppid = hashlib.sha256(ppid_data.encode()).hexdigest()[:32]
        
        logger.info("✅ PPID generated")
        return jsonify({
            'success': True,
            'ppid': ppid,
            'privacy_preserved': True
        }), 200
        
    except Exception as e:
        logger.error(f"❌ PPID generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'ppid_error',
            'message': 'Failed to generate PPID'
        }), 500

@network_client_config_bp.route('/api/network/sync/check-shared-identity', methods=['POST'])
@cross_origin()
def check_shared_identity():
    """
    Check for shared identity credentials across network
    """
    try:
        from flask import request
        data = request.get_json() or {}
        
        # For now, return empty result (no shared identities)
        # In production, would check federated network registry
        
        logger.info("✅ Shared identity check completed")
        return jsonify({
            'success': True,
            'shared_identities': [],
            'network_status': 'active',
            'message': 'No shared identities found'
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Shared identity check error: {e}")
        return jsonify({
            'success': False,
            'error': 'check_error',
            'message': 'Failed to check shared identity'
        }), 500

@network_client_config_bp.route('/api/network/trusted-issuers', methods=['GET'])
@cross_origin()
def get_trusted_issuers():
    """
    Get trusted issuer DIDs from crypto engine for DID registry
    """
    try:
        # Get real issuer DIDs from crypto engine
        trusted_issuers = []
        
        try:
            # Import crypto engine to get real issuer DIDs
            from lemma_crypto import PyMinimalIssuer
            from api.issuer_management import get_issuer_manager
            
            # Get issuer manager
            issuer_manager = get_issuer_manager()
            
            # Get federated issuer (for PoH lemmas)
            federated_issuer = issuer_manager.get_federated_issuer()
            trusted_issuers.append({
                'did': federated_issuer.get_did(),
                'public_key': federated_issuer.get_public_key_hex(),
                'name': 'Lemma Federated Identity Network',
                'issuer_type': 'federated_identity',
                'trust_score': 0.95
            })
            
            # Get IAM issuer (for permission lemmas)
            iam_issuer = issuer_manager.get_iam_issuer()
            trusted_issuers.append({
                'did': iam_issuer.get_did(),
                'public_key': iam_issuer.get_public_key_hex(),
                'name': 'Lemma Platform IAM',
                'issuer_type': 'platform_iam',
                'trust_score': 0.98
            })
            
            # Get multi-lemma issuer (for advanced wallet features)
            multi_lemma_issuer = issuer_manager.get_multi_lemma_issuer()
            trusted_issuers.append({
                'did': multi_lemma_issuer.get_did(),
                'public_key': multi_lemma_issuer.get_public_key_hex(),
                'name': 'Lemma Multi-Lemma System',
                'issuer_type': 'multi_lemma',
                'trust_score': 0.92
            })
            
        except ImportError:
            logger.warning("⚠️ Crypto engine not available for trusted issuers")
        except Exception as e:
            logger.warning(f"⚠️ Could not get real issuer DIDs: {e}")
        
        logger.info(f"✅ Providing {len(trusted_issuers)} trusted issuer DIDs")
        return jsonify({
            'success': True,
            'issuers': trusted_issuers,
            'count': len(trusted_issuers)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Trusted issuers error: {e}")
        return jsonify({
            'success': False,
            'error': 'issuers_error',
            'message': 'Failed to get trusted issuers'
        }), 500
