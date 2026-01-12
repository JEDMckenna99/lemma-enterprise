"""
SDK Remote Configuration API
Allows pushing updates to all SDK instances without code changes
"""

from flask import Blueprint, jsonify, request
from flask_cors import cross_origin
import logging

logger = logging.getLogger(__name__)

sdk_config_bp = Blueprint('sdk_config', __name__)

# Current SDK configuration - update this to push changes to all sites
SDK_CONFIG = {
    'version': '2.0.0',
    'features': {
        'centralWallet': True,
        'bridgeEnabled': True,
        'offlineVerification': True,
        'revocationChecks': True,
    },
    'endpoints': {
        'bridge': '/wallet/bridge',
        'issue': '/api/wallet-auth/issue',
        'revocationList': '/api/v1/revocation/list',
    },
    'settings': {
        'bridgeTimeout': 5000,
        'verificationCacheMinutes': 5,
        'autoRefreshCredentials': True,
        'debugMode': False,
    },
    'ui': {
        'showWalletButton': True,
        'buttonText': 'Sign in with Lemma',
        'buttonStyle': 'modern',  # 'modern', 'minimal', 'custom'
    },
    'announcements': [
        # Push announcements to all SDK instances
        # {
        #     'id': 'new-feature-2024',
        #     'type': 'info',
        #     'message': 'New: Central wallet now available!',
        #     'showOnce': True
        # }
    ]
}


@sdk_config_bp.route('/api/sdk/config', methods=['GET'])
@cross_origin()
def get_sdk_config():
    """
    Get current SDK configuration
    SDKs fetch this on init to get latest settings
    
    GET /api/sdk/config?site_id=example.com&sdk_version=1.0.0
    """
    site_id = request.args.get('site_id', 'unknown')
    sdk_version = request.args.get('sdk_version', '0.0.0')
    
    logger.info(f"📱 SDK config request: site={site_id}, version={sdk_version}")
    
    # Could customize config per site if needed
    config = SDK_CONFIG.copy()
    
    # Add site-specific overrides if needed
    # config['siteOverrides'] = get_site_overrides(site_id)
    
    return jsonify({
        'success': True,
        'config': config,
        'serverTime': __import__('time').time()
    })


@sdk_config_bp.route('/api/sdk/check-update', methods=['GET'])
@cross_origin()
def check_sdk_update():
    """
    Check if SDK needs update
    
    GET /api/sdk/check-update?current_version=1.0.0
    """
    current = request.args.get('current_version', '0.0.0')
    latest = SDK_CONFIG['version']
    
    def parse_version(v):
        try:
            return tuple(map(int, v.split('.')))
        except:
            return (0, 0, 0)
    
    needs_update = parse_version(current) < parse_version(latest)
    
    return jsonify({
        'success': True,
        'currentVersion': current,
        'latestVersion': latest,
        'needsUpdate': needs_update,
        'updateUrl': 'https://lemma.id/static/js/lemma-iam-sdk.js',
        'changelog': 'https://lemma.id/docs/changelog'
    })


@sdk_config_bp.route('/api/sdk/features', methods=['GET'])
@cross_origin()
def get_feature_flags():
    """
    Get feature flags - enable/disable features remotely
    
    GET /api/sdk/features?site_id=example.com
    """
    site_id = request.args.get('site_id', 'unknown')
    
    # Default features
    features = SDK_CONFIG['features'].copy()
    
    # Could enable/disable features per site
    # site_features = get_site_features(site_id)
    # features.update(site_features)
    
    return jsonify({
        'success': True,
        'features': features,
        'site': site_id
    })
