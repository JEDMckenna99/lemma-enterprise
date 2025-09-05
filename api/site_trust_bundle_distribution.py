"""
Site Trust Bundle Distribution System
Sends verified trust bundles to all sites using the federated identity network for bot protection
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import time
import secrets
from datetime import datetime, timedelta

from .database import get_db, Site, UserLemma, Customer
from .network_registry import NETWORK_REGISTRY

logger = logging.getLogger(__name__)

site_trust_bundle_bp = Blueprint('site_trust_bundle', __name__)

class SiteTrustBundleManager:
    """Manages distribution of federated identity trust bundles to sites"""
    
    def __init__(self):
        self.bundle_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def build_federated_trust_bundle(self, site_id=None):
        """
        Build trust bundle containing ONLY federated identity credentials
        for bot protection across the network
        
        This contains:
        - Verified human identity DIDs (from verification card only)
        - Network revocation lists
        - OPRF bloom filters for bot detection
        - Does NOT contain site-specific permission lemmas
        """
        
        current_time = time.time()
        
        # Get all verified human identities from verification card onboarding
        db = get_db()
        
        # Only include identity lemmas from verification card sources
        verified_identities = db.query(UserLemma).filter(
            UserLemma.lemma_type == 'identity',
            UserLemma.lemma_data['verificationSource'].astext.in_([
                'verification_card',
                'stripe_identity_verification',
                'lemma_shield_verification'
            ])
        ).all()
        
        # Build DID registry for bot protection
        did_registry = {}
        for identity in verified_identities:
            user_did = identity.user_did
            lemma_data = identity.lemma_data
            
            # Only include if properly verified through verification card
            if self._is_valid_verification_card_source(lemma_data):
                did_registry[user_did] = {
                    'did': user_did,
                    'verified_human': True,
                    'verification_method': lemma_data.get('verificationSource'),
                    'verified_at': identity.issued_at.timestamp(),
                    'expires_at': identity.expires_at.timestamp() if identity.expires_at else None,
                    'trust_score': 1.0,
                    'network_level': True  # Available for bot protection network-wide
                }
        
        db.close()
        
        # Get network revocation data
        revocation_data = NETWORK_REGISTRY['revocation_lists']
        
        # Build trust bundle for sites
        trust_bundle = {
            'bundle_type': 'federated_identity_bot_protection',
            'created_at': current_time,
            'expires_at': current_time + 3600,  # 1 hour expiry
            'site_id': site_id,
            'network_scope': True,
            
            # Federated identity DIDs for bot protection
            'verified_human_dids': did_registry,
            
            # Revocation data for offline checking
            'revocation_lists': {
                'bloom_filter': revocation_data.get('oprf_bloom_filters', {}),
                'revocation_entries': revocation_data.get('revocation_entries', {}),
                'last_updated': revocation_data.get('last_updated', current_time)
            },
            
            # Network metadata
            'network_stats': {
                'total_verified_humans': len(did_registry),
                'total_sites_protected': NETWORK_REGISTRY['network_metadata']['total_sites'],
                'network_uptime': current_time - NETWORK_REGISTRY['network_metadata']['created_at']
            },
            
            # Explicitly exclude site-specific data
            'excluded_data': {
                'site_specific_permissions': 'Not included - handled separately',
                'user_personal_data': 'Not included - privacy preserved',
                'site_internal_users': 'Not included - site manages internally'
            }
        }
        
        return trust_bundle
    
    def _is_valid_verification_card_source(self, lemma_data):
        """Check if lemma data indicates proper verification card source"""
        
        verification_source = lemma_data.get('verificationSource', '')
        issuer = lemma_data.get('issuer', '')
        
        # Valid verification card sources
        valid_sources = [
            'verification_card',
            'stripe_identity_verification',
            'lemma_shield_verification'
        ]
        
        valid_issuers = [
            'did:lemma:verification-card',
            'did:lemma:platform:verification',
            'did:lemma:shield:verification'
        ]
        
        return (verification_source in valid_sources or 
                any(issuer_pattern in issuer for issuer_pattern in valid_issuers))
    
    def get_cached_bundle(self, site_id):
        """Get cached trust bundle for site"""
        cache_key = f"federated_bundle_{site_id or 'global'}"
        
        if cache_key in self.bundle_cache:
            bundle, timestamp = self.bundle_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return bundle
        
        # Build fresh bundle
        bundle = self.build_federated_trust_bundle(site_id)
        self.bundle_cache[cache_key] = (bundle, time.time())
        return bundle

# Global manager instance
trust_bundle_manager = SiteTrustBundleManager()

@site_trust_bundle_bp.route('/api/sites/<site_id>/trust-bundle', methods=['GET'])
@cross_origin()
def get_site_trust_bundle(site_id):
    """
    Get federated identity trust bundle for site bot protection
    
    This provides ONLY:
    - Verified human identities (from verification card)
    - Network revocation lists
    - Bot protection data
    
    Does NOT provide:
    - Site-specific permission lemmas
    - User personal data
    - Other sites' internal data
    """
    try:
        # Validate site exists
        db = get_db()
        site = db.query(Site).filter(Site.site_id == site_id).first()
        if not site:
            db.close()
            return jsonify({
                'success': False,
                'error': 'Site not found'
            }), 404
        
        db.close()
        
        # Get trust bundle for this site
        trust_bundle = trust_bundle_manager.get_cached_bundle(site_id)
        
        logger.info(f"📦 Trust bundle delivered to {site.site_domain}: {len(trust_bundle['verified_human_dids'])} verified humans")
        
        return jsonify({
            'success': True,
            'trust_bundle': trust_bundle,
            'usage': 'bot_protection_only',
            'note': 'This bundle contains only federated identity data for bot protection. Site-specific permissions are handled separately.'
        })
        
    except Exception as e:
        logger.error(f"❌ Trust bundle delivery error for site {site_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate trust bundle'
        }), 500

@site_trust_bundle_bp.route('/api/sites/global/trust-bundle', methods=['GET'])
@cross_origin()
def get_global_trust_bundle():
    """
    Get global federated identity trust bundle for bot protection
    Available to all sites in the network
    """
    try:
        # Get global trust bundle (not site-specific)
        trust_bundle = trust_bundle_manager.get_cached_bundle(None)
        
        logger.info(f"🌐 Global trust bundle delivered: {len(trust_bundle['verified_human_dids'])} verified humans")
        
        return jsonify({
            'success': True,
            'trust_bundle': trust_bundle,
            'scope': 'global_bot_protection',
            'usage': 'Federated identity verification for bot protection across all network sites'
        })
        
    except Exception as e:
        logger.error(f"❌ Global trust bundle error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate global trust bundle'
        }), 500

@site_trust_bundle_bp.route('/api/sites/<site_id>/verify-human', methods=['POST'])
@cross_origin()
def verify_human_for_site(site_id):
    """
    Verify if a user is human using federated identity network
    
    This endpoint allows sites to check if a user has verified humanity
    through the verification card system for bot protection
    """
    try:
        data = request.get_json()
        user_did = data.get('user_did', '')
        user_credential = data.get('credential', {})
        
        if not user_did and not user_credential:
            return jsonify({
                'success': False,
                'error': 'User DID or credential is required'
            }), 400
        
        # Get trust bundle for verification
        trust_bundle = trust_bundle_manager.get_cached_bundle(site_id)
        
        # Check if user is in verified humans registry
        if user_did:
            human_data = trust_bundle['verified_human_dids'].get(user_did)
            if human_data:
                return jsonify({
                    'success': True,
                    'verified_human': True,
                    'verification_source': human_data['verification_method'],
                    'trust_score': human_data['trust_score'],
                    'verified_at': human_data['verified_at'],
                    'network_verified': True
                })
        
        # If credential provided, validate it
        if user_credential:
            validation = validate_federated_identity_source(user_credential)
            if validation['valid']:
                return jsonify({
                    'success': True,
                    'verified_human': True,
                    'verification_source': validation['source'],
                    'credential_valid': True,
                    'network_verified': True
                })
        
        # User not verified or invalid credential
        return jsonify({
            'success': True,
            'verified_human': False,
            'reason': 'User not found in federated identity network',
            'recommendation': 'User should complete verification card process'
        })
        
    except Exception as e:
        logger.error(f"❌ Human verification error for site {site_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Verification failed'
        }), 500

@site_trust_bundle_bp.route('/api/federated/onboarding-stats', methods=['GET'])
@cross_origin()
def get_onboarding_stats():
    """Get statistics about federated identity onboarding sources"""
    try:
        db = get_db()
        
        # Count identity lemmas by source
        verification_card_count = db.query(UserLemma).filter(
            UserLemma.lemma_type == 'identity',
            UserLemma.lemma_data['verificationSource'].astext.in_([
                'verification_card',
                'stripe_identity_verification',
                'lemma_shield_verification'
            ])
        ).count()
        
        # Count any invalid sources (should be 0)
        invalid_sources = db.query(UserLemma).filter(
            UserLemma.lemma_type == 'identity',
            ~UserLemma.lemma_data['verificationSource'].astext.in_([
                'verification_card',
                'stripe_identity_verification',
                'lemma_shield_verification'
            ])
        ).count()
        
        db.close()
        
        return jsonify({
            'success': True,
            'onboarding_stats': {
                'verification_card_onboarding': verification_card_count,
                'invalid_sources': invalid_sources,
                'enforcement_active': True,
                'total_federated_users': verification_card_count,
                'compliance_rate': (verification_card_count / max(verification_card_count + invalid_sources, 1)) * 100
            },
            'message': 'Federated identity onboarding properly enforced through verification card only'
        })
        
    except Exception as e:
        logger.error(f"❌ Onboarding stats error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get onboarding statistics'
        }), 500
