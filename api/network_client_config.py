"""
Client-Side Network Configuration API
====================================

Provides environment-specific network configuration to JavaScript clients.
This allows the federated wallet to know which endpoints to sync with.
"""

from flask import Blueprint, jsonify, request
from .network_config import NETWORK_CONFIG, get_federation_endpoints, get_network_registry_url
import logging

# Import CORS decorator
from auth.decorators import cors_headers

logger = logging.getLogger(__name__)

# Client config blueprint
client_config_bp = Blueprint('client_config', __name__)

@client_config_bp.route('/api/network/client-config', methods=['GET', 'OPTIONS'])
@cors_headers
def get_client_network_config():
    """Get network configuration for JavaScript clients"""
    
    # Handle CORS preflight requests
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        config = {
            "success": True,
            "node_id": NETWORK_CONFIG["node_id"],
            "node_name": NETWORK_CONFIG["node_name"],
            "network_registry_url": get_network_registry_url(),
            "federation_endpoints": get_federation_endpoints(),
            "network_auth_key": NETWORK_CONFIG["network_authority_key"],
            "sync_interval": NETWORK_CONFIG["sync_interval"] * 1000,  # Convert to milliseconds
            "is_primary_node": NETWORK_CONFIG.get("is_primary_node", False)
        }
        
        logger.info(f"📡 Provided client config for {NETWORK_CONFIG['node_name']}")
        
        return jsonify(config)
        
    except Exception as e:
        logger.error(f"❌ Failed to get client config: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get network configuration"
        }), 500

@client_config_bp.route('/api/network/node-info', methods=['GET'])
def get_node_info():
    """Get basic node information"""
    try:
        info = {
            "success": True,
            "node_id": NETWORK_CONFIG["node_id"],
            "node_name": NETWORK_CONFIG["node_name"],
            "node_endpoint": NETWORK_CONFIG["node_endpoint"],
            "network_name": NETWORK_CONFIG["network_name"],
            "is_primary": NETWORK_CONFIG.get("is_primary_node", False),
            "federation_size": len(get_federation_endpoints()) + 1  # +1 for self
        }
        
        return jsonify(info)
        
    except Exception as e:
        logger.error(f"❌ Failed to get node info: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get node information"
        }), 500
