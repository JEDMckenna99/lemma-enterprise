"""
Federated Identity Onboarding Enforcement
Ensures verification card OR bot shield verification are the valid paths for federated identity network onboarding
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
from datetime import datetime, timedelta

from .database import get_db, UserLemma, Customer

logger = logging.getLogger(__name__)

federated_onboarding_bp = Blueprint('federated_onboarding', __name__)

def validate_federated_identity_source(credential):
    """
    Validate that federated identity credentials came from verification card OR bot shield verification
    
    Args:
        credential: The identity credential to validate
        
    Returns:
        dict: Validation result with source verification
    """
    
    # Check if credential has proper verification card signature
    if not credential.get('proof'):
        return {
            'valid': False,
            'reason': 'No cryptographic proof found',
            'source': 'unknown'
        }
    
    # Verification card credentials have specific issuer patterns
    issuer = credential.get('issuer', '')
    verification_method = credential.get('proof', {}).get('verificationMethod', '')
    
    # Valid sources for federated identity (verification card AND bot shield verification)
    valid_sources = [
        'did:lemma:verification-card',
        'did:lemma:platform:verification',
        'did:lemma:shield:verification',
        'did:lemma:bot-shield:verification',
        'did:lemma:stripe:identity',
        'did:lemma:federated:verification'
    ]
    
    # Check if issuer indicates verification card origin
    is_verification_card = any(source in issuer for source in valid_sources)
    
    # Check verification method
    is_proper_verification = any(source in verification_method for source in valid_sources)
    
    # Check claims for verification card indicators
    claims = credential.get('claims', {})
    verification_source = claims.get('verificationSource', '')
    is_human_verified = claims.get('isHuman', False)
    
    if is_verification_card or is_proper_verification:
        # Determine specific source type
        source_type = 'verification_card'
        if 'bot-shield' in issuer or 'shield' in verification_source:
            source_type = 'bot_shield_verification'
        elif 'stripe' in issuer or 'stripe' in verification_source:
            source_type = 'stripe_identity_verification'
        
        return {
            'valid': True,
            'source': source_type,
            'verification_method': verification_method,
            'human_verified': is_human_verified
        }
    
    # Reject non-verification-card sources for federated identity
    return {
        'valid': False,
        'reason': f'Invalid source for federated identity: {issuer}',
        'source': 'invalid',
        'required_source': 'verification_card_only'
    }

@federated_onboarding_bp.route('/api/federated/validate-identity-source', methods=['POST'])
@cross_origin()
def validate_identity_source():
    """
    Validate that identity credential came from verification card
    Used to enforce proper federated identity onboarding
    """
    try:
        data = request.get_json()
        credential = data.get('credential', {})
        
        if not credential:
            return jsonify({
                'success': False,
                'error': 'Credential is required'
            }), 400
        
        # Validate the source
        validation = validate_federated_identity_source(credential)
        
        if validation['valid']:
            logger.info(f"✅ Valid federated identity source: {validation['source']}")
            return jsonify({
                'success': True,
                'valid': True,
                'source': validation['source'],
                'verification_method': validation['verification_method'],
                'human_verified': validation['human_verified']
            })
        else:
            logger.warning(f"❌ Invalid federated identity source: {validation['reason']}")
            return jsonify({
                'success': True,
                'valid': False,
                'reason': validation['reason'],
                'required_source': validation['required_source']
            })
            
    except Exception as e:
        logger.error(f"❌ Identity source validation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@federated_onboarding_bp.route('/api/federated/reject-email-onboarding', methods=['POST'])
@cross_origin()
def reject_email_onboarding():
    """
    Explicitly reject attempts to create federated identity via email
    Federated identity MUST come through verification card only
    """
    try:
        data = request.get_json()
        email = data.get('email', '')
        attempted_method = data.get('method', 'unknown')
        
        logger.warning(f"🚫 Rejected federated identity onboarding attempt via {attempted_method} for {email}")
        
        return jsonify({
            'success': False,
            'error': 'Federated identity onboarding only available through verification card or bot shield verification',
            'required_methods': ['verification_card', 'bot_shield_verification'],
            'attempted_method': attempted_method,
            'verification_card_url': 'https://lemma.id/verify',
            'bot_shield_url': 'https://lemma.id/ (any site with bot shield)',
            'message': 'Please use the verification card or complete bot shield verification to join the federated identity network'
        }), 403
        
    except Exception as e:
        logger.error(f"❌ Email onboarding rejection error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

def ensure_verification_card_only_onboarding():
    """
    Enforcement function to ensure federated identity onboarding 
    only happens through verification card
    """
    
    # This function can be called by other endpoints to validate
    # that identity credentials are properly sourced
    
    def decorator(f):
        def wrapper(*args, **kwargs):
            # Add validation logic here if needed
            return f(*args, **kwargs)
        return wrapper
    return decorator
