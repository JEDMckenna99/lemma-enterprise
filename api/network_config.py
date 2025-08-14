"""
Environment-Specific Network Configuration
==========================================

Configures network identity and endpoints based on deployment environment.
This allows different deployments to properly federate with each other.
"""

import os
import logging

logger = logging.getLogger(__name__)

def get_network_config():
    """Get network configuration based on environment"""
    
    # Detect environment based on HEROKU_APP_NAME or domain
    heroku_app = os.environ.get('HEROKU_APP_NAME', '')
    
    # Also check for Heroku deployment indicators
    is_heroku = bool(os.environ.get('DYNO')) or bool(os.environ.get('PORT'))
    
    # Default configuration
    config = {
        "network_did": "did:lemma:network",
        "network_name": "Lemma Federated Identity Network",
        "network_authority_key": "lemma_network_federated_sync_2024",
        "sync_interval": 5,
    }
    
    if heroku_app == 'lemma-enterprise' or 'lemma-enterprise' in heroku_app:
        # Production lemma.id configuration
        config.update({
            "node_id": "lemma-enterprise",
            "node_name": "Lemma Enterprise (lemma.id)",
            "node_endpoint": "https://lemma-enterprise-0f6ba17076c1.herokuapp.com",
            "is_primary_node": True,
            "federation_endpoints": [
                "https://lemma-identity-network-2d96786d6ffb.herokuapp.com"
            ],
            "network_registry_url": "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/network/sync"
        })
        logger.info("🏢 Configured as Lemma Enterprise (Primary Node)")
        
    elif heroku_app == 'lemma-identity-network' or 'identity-network' in heroku_app:
        # Testing federated network configuration  
        config.update({
            "node_id": "lemma-identity-network",
            "node_name": "Lemma Identity Network (Testing)",
            "node_endpoint": "https://lemma-identity-network-2d96786d6ffb.herokuapp.com",
            "is_primary_node": False,
            "federation_endpoints": [
                "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
            ],
            "network_registry_url": "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/network/sync"
        })
        logger.info("🌐 Configured as Lemma Identity Network (Federated Node)")
        
    else:
        # Check if we're on Heroku but app name detection failed
        if is_heroku:
            # Default to lemma-enterprise configuration for unknown Heroku deployments
            config.update({
                "node_id": "lemma-enterprise",
                "node_name": "Lemma Enterprise (lemma.id)",
                "node_endpoint": "https://lemma-enterprise-0f6ba17076c1.herokuapp.com",
                "is_primary_node": True,
                "federation_endpoints": [
                    "https://lemma-identity-network-2d96786d6ffb.herokuapp.com"
                ],
                "network_registry_url": "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/network/sync"
            })
            logger.info("🏢 Configured as Lemma Enterprise (Heroku Fallback)")
        else:
            # True local development
            config.update({
                "node_id": "lemma-local",
                "node_name": "Lemma Local Development",
                "node_endpoint": "http://localhost:5000",
                "is_primary_node": True,
                "federation_endpoints": [],
                "network_registry_url": "http://localhost:5000/api/network/sync"
            })
            logger.info("💻 Configured as Local Development")
    
    # Add all known endpoints for the network bundle
    config["all_network_endpoints"] = [
        "https://lemma-enterprise-0f6ba17076c1.herokuapp.com",
        "https://lemma-identity-network-2d96786d6ffb.herokuapp.com"
    ]
    
    return config

# Global network configuration
NETWORK_CONFIG = get_network_config()

def get_federation_endpoints():
    """Get list of federation endpoints to sync with (excluding self)"""
    return NETWORK_CONFIG["federation_endpoints"]

def get_own_endpoint():
    """Get this node's own endpoint"""
    return NETWORK_CONFIG["node_endpoint"]

def is_primary_node():
    """Check if this is the primary node"""
    return NETWORK_CONFIG.get("is_primary_node", False)

def get_network_registry_url():
    """Get the network registry URL for this deployment"""
    return NETWORK_CONFIG["network_registry_url"]

def get_node_identity():
    """Get this node's identity information"""
    return {
        "node_id": NETWORK_CONFIG["node_id"],
        "node_name": NETWORK_CONFIG["node_name"], 
        "node_endpoint": NETWORK_CONFIG["node_endpoint"],
        "is_primary": NETWORK_CONFIG["is_primary_node"]
    }
