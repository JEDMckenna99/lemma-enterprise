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
    Get ALL trusted issuer DIDs from KMS-backed database entries.
    
    SECURITY: Only KMS-backed issuers are considered trusted.
    This is the authoritative list that client wallets use to validate credentials.
    """
    try:
        trusted_issuers = []
        
        try:
            # Query database for ALL sites with KMS-encrypted keys
            from api.database import SessionLocal, Site
            
            db = SessionLocal()
            try:
                # Get all sites that have KMS-backed keys (these are the trusted issuers)
                kms_backed_sites = db.query(Site).filter(
                    Site.kms_encrypted_signing_key.isnot(None),
                    Site.issuer_did.isnot(None),
                    Site.public_key_hex.isnot(None),
                    Site.key_status == 'active'
                ).all()
                
                logger.info(f"Found {len(kms_backed_sites)} KMS-backed issuers in database")
                
                # Map site types to friendly names
                issuer_type_map = {
                    'federated_network': ('Lemma Federated Identity Network', 'federated_identity', 0.95),
                    'lemma.id': ('Lemma Platform IAM', 'platform_iam', 0.98),
                    'multi_lemma_qr_authentication': ('Lemma QR Authentication', 'multi_lemma', 0.92),
                    'multi_lemma_delegation': ('Lemma Delegation Service', 'multi_lemma', 0.90),
                }
                
                for site in kms_backed_sites:
                    default_name = f'Lemma IAM - {site.site_id}'
                    default_type = 'site_iam'
                    default_score = 0.90
                    
                    name, issuer_type, trust_score = issuer_type_map.get(
                        site.site_id, 
                        (default_name, default_type, default_score)
                    )
                    
                    trusted_issuers.append({
                        'did': site.issuer_did,
                        'public_key': site.public_key_hex,
                        'name': name,
                        'issuer_type': issuer_type,
                        'site_id': site.site_id,
                        'trust_score': trust_score
                    })
                    
                    logger.debug(f"  Trusted issuer: {site.site_id} -> {site.issuer_did[:50]}...")
                    
            finally:
                db.close()
                
        except ImportError as e:
            logger.warning(f"Database module not available: {e}")
        except Exception as e:
            logger.warning(f"Could not load KMS-backed issuers from database: {e}")
        
        logger.info(f"Providing {len(trusted_issuers)} trusted issuer DIDs")
        return jsonify({
            'success': True,
            'issuers': trusted_issuers,
            'count': len(trusted_issuers)
        }), 200
        
    except Exception as e:
        logger.error(f"Trusted issuers error: {e}")
        return jsonify({
            'success': False,
            'error': 'issuers_error',
            'message': 'Failed to get trusted issuers'
        }), 500
