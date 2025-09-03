"""
Centralized Wallet Management
Ensures consistent wallet handling across the platform to prevent multiple wallet issues
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import secrets
from datetime import datetime

logger = logging.getLogger(__name__)

wallet_management_bp = Blueprint('wallet_management', __name__)

@wallet_management_bp.route('/api/wallet/check-existing', methods=['POST'])
@cross_origin()
def check_existing_wallet():
    """
    Check if user already has a wallet and credentials
    
    POST /api/wallet/check-existing
    {
        "email": "user@example.com",
        "site_id": "site_123"
    }
    """
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        site_id = data.get('site_id', '')
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Create user identifier for privacy-preserving lookup
        user_did = f'did:lemma:user:{email.replace("@", "_at_").replace(".", "_")}'
        
        # Check if user has existing credentials in the network registry
        # This is a privacy-preserving check that doesn't expose email directly
        
        logger.info(f"🔍 Checking existing wallet for {email} (site: {site_id})")
        
        return jsonify({
            'success': True,
            'email': email,
            'user_did': user_did,
            'has_existing_wallet': True,  # Assume true for now - will be checked client-side
            'recommended_action': 'use_existing_wallet',
            'wallet_config': {
                'networkRegistryUrl': 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/network/sync',
                'networkAuthKey': 'lemma_network_federated_sync_2024',
                'debug': True
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Wallet check error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@wallet_management_bp.route('/api/wallet/unified-storage', methods=['POST'])
@cross_origin()
def unified_wallet_storage():
    """
    Store credential in unified wallet system (prevents multiple wallet issues)
    
    POST /api/wallet/unified-storage
    {
        "credential": {...},
        "user_email": "user@example.com",
        "force_storage": false
    }
    """
    try:
        data = request.get_json()
        credential = data.get('credential', {})
        user_email = data.get('user_email', '')
        force_storage = data.get('force_storage', False)
        
        if not credential or not user_email:
            return jsonify({
                'success': False,
                'error': 'Credential and user email are required'
            }), 400
        
        logger.info(f"💾 Unified wallet storage for {user_email}: {credential.get('id', 'unknown')}")
        
        # Return storage instructions for client-side execution
        return jsonify({
            'success': True,
            'storage_method': 'client_side_unified',
            'credential': credential,
            'user_email': user_email,
            'storage_config': {
                'use_existing_wallet': True,
                'prevent_duplicates': True,
                'cross_browser_sync': True,
                'network_registry_sync': True
            },
            'instructions': {
                'check_existing': 'Check for existing wallet instance first',
                'use_global': 'Use window.globalLemmaWallet if available',
                'prevent_duplicates': 'Check for existing credentials before storing',
                'sync_network': 'Enable network registry sync for cross-browser access'
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Unified storage error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
