"""
Automatic Credential Refresh API
=================================

Handles seamless credential refresh before expiry to prevent lockouts.

Flow:
1. Client detects credential expiring soon (< 7 days)
2. Sends refresh request with old credential
3. Server verifies old credential is still valid
4. Issues new credential with extended expiry
5. Client replaces old credential in wallet
6. User experiences zero downtime
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import time
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

credential_refresh_bp = Blueprint('credential_refresh', __name__)


@credential_refresh_bp.route('/api/credentials/refresh', methods=['POST'])
@cross_origin()
def refresh_credential():
    """
    Refresh a credential before it expires
    
    POST /api/credentials/refresh
    {
        "credential": {...},  // Existing credential to refresh
        "site_id": "site_123"  // Site ID (for permission credentials)
    }
    
    Returns:
        New credential with extended expiry
    """
    try:
        data = request.get_json()
        
        if not data or 'credential' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing credential in request'
            }), 400
        
        old_credential = data['credential']
        site_id = data.get('site_id')
        credential_type = old_credential.get('credentialSubject', {}).get('packageType', 'unknown')
        
        # Extract credential details
        credential_id = old_credential.get('id')
        subject = old_credential.get('subject')
        issuer = old_credential.get('issuer')
        claims = old_credential.get('credentialSubject', {})
        
        logger.info(f"🔄 Refresh request for credential: {credential_id}")
        logger.info(f"   Type: {credential_type}")
        logger.info(f"   Subject: {subject[:50]}...")
        
        # Verify old credential is still valid
        if not verify_old_credential(old_credential):
            return jsonify({
                'success': False,
                'error': 'Old credential is invalid or revoked',
                'message': 'Cannot refresh an invalid credential'
            }), 403
        
        # Check if credential is expiring soon (< 30 days)
        expiry = claims.get('expiresAt')
        if expiry:
            try:
                expiry_time = int(expiry) if isinstance(expiry, str) else expiry
                time_until_expiry = expiry_time - int(time.time())
                days_until_expiry = time_until_expiry / (24 * 60 * 60)
                
                logger.info(f"   Time until expiry: {days_until_expiry:.1f} days")
                
                if days_until_expiry > 30:
                    # Too early to refresh
                    return jsonify({
                        'success': False,
                        'error': 'Credential not eligible for refresh yet',
                        'message': f'Credential has {days_until_expiry:.0f} days remaining. Refresh available at < 30 days.',
                        'days_remaining': days_until_expiry,
                        'refresh_available_at': expiry_time - (30 * 24 * 60 * 60)
                    }), 400
                
                if days_until_expiry < 0:
                    # Already expired
                    return jsonify({
                        'success': False,
                        'error': 'Credential has expired',
                        'message': 'Cannot refresh expired credential. Please re-authenticate.'
                    }), 403
                    
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing expiry: {e}")
        
        # Issue new credential based on type
        if credential_type == 'permission' and site_id:
            new_credential = refresh_permission_credential(old_credential, site_id)
        elif credential_type == 'poh':
            new_credential = refresh_poh_credential(old_credential)
        else:
            return jsonify({
                'success': False,
                'error': 'Unknown credential type or missing site_id',
                'credential_type': credential_type
            }), 400
        
        if new_credential:
            logger.info(f"✅ Credential refreshed successfully")
            logger.info(f"   New ID: {new_credential.get('id')}")
            logger.info(f"   New expiry: {new_credential.get('credentialSubject', {}).get('expiresAt')}")
            
            return jsonify({
                'success': True,
                'credential': new_credential,
                'old_credential_id': credential_id,
                'message': 'Credential refreshed successfully',
                'refresh_timestamp': int(time.time())
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to issue new credential'
            }), 500
        
    except Exception as e:
        logger.error(f"❌ Credential refresh error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def verify_old_credential(credential: dict) -> bool:
    """
    Verify that old credential is still valid before refreshing
    
    Checks:
    1. Signature is valid
    2. Not revoked
    3. Not expired (or expiring soon)
    """
    try:
        from lemma_crypto import PyOptimizedVerifier
        
        verifier = PyOptimizedVerifier()
        credential_json = json.dumps(credential)
        is_valid = verifier.verify_credential_json(credential_json)  # Returns boolean
        
        if not is_valid:
            logger.warning("Old credential verification failed")
            return False
        
        logger.info("✅ Old credential verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"Credential verification error: {e}")
        return False


def refresh_permission_credential(old_credential: dict, site_id: str) -> dict:
    """
    Refresh a permission credential
    
    Reissues the same permission with extended expiry
    """
    try:
        from api.real_iam_manager import get_site_manager
        
        # Extract details from old credential
        claims = old_credential.get('credentialSubject', {})
        subject = old_credential.get('subject')
        permission_id = claims.get('permissionId')
        site_domain = claims.get('siteDomain', f'site_{site_id}.com')
        
        logger.info(f"🔄 Refreshing permission credential: {permission_id}")
        
        # Get site manager
        manager = get_site_manager(site_id, site_domain)
        
        if not manager:
            logger.error(f"Site manager not found for {site_id}")
            return None
        
        # Check if permission still exists
        if permission_id not in manager.permissions:
            logger.warning(f"Permission '{permission_id}' no longer exists - recreating from old credential")
            # Permission was deleted but credential exists - recreate it
            manager.add_permission({
                'permission_id': permission_id,
                'display_name': claims.get('displayName', permission_id),
                'scope': claims.get('scope', []),
                'conditions': [],
                'priority': 100
            })
        
        # Issue new credential with same permissions, extended expiry
        new_credential = manager.issue_permission_lemma(
            subject,
            permission_id,
            expiry_days=90,  # Fresh 90-day expiry
            custom_claims=None
        )
        
        logger.info(f"✅ New permission credential issued")
        return new_credential
        
    except Exception as e:
        logger.error(f"Permission refresh error: {e}")
        return None


def refresh_poh_credential(old_credential: dict) -> dict:
    """
    Refresh a Proof of Humanity credential
    
    Note: PoH credentials should require re-verification
    This is a placeholder for future implementation
    """
    logger.warning("PoH credential refresh requested - not implemented yet")
    logger.warning("PoH credentials should require fresh verification")
    
    return None


@credential_refresh_bp.route('/api/credentials/check-refresh-eligibility', methods=['POST'])
@cross_origin()
def check_refresh_eligibility():
    """
    Check if credentials are eligible for refresh
    
    POST /api/credentials/check-refresh-eligibility
    {
        "credentials": [...]  // Array of credentials to check
    }
    
    Returns:
        Array of eligibility status for each credential
    """
    try:
        data = request.get_json()
        credentials = data.get('credentials', [])
        
        if not credentials:
            return jsonify({
                'success': False,
                'error': 'No credentials provided'
            }), 400
        
        results = []
        current_time = int(time.time())
        
        for credential in credentials:
            credential_id = credential.get('id')
            claims = credential.get('credentialSubject', {})
            expiry = claims.get('expiresAt')
            
            if not expiry:
                # No expiry = no refresh needed
                results.append({
                    'credential_id': credential_id,
                    'eligible': False,
                    'reason': 'No expiration date',
                    'action': 'none'
                })
                continue
            
            try:
                expiry_time = int(expiry) if isinstance(expiry, str) else expiry
                time_until_expiry = expiry_time - current_time
                days_until_expiry = time_until_expiry / (24 * 60 * 60)
                
                if days_until_expiry < 0:
                    # Expired
                    results.append({
                        'credential_id': credential_id,
                        'eligible': False,
                        'reason': 'Credential expired',
                        'action': 'reauthenticate',
                        'days_remaining': days_until_expiry
                    })
                elif days_until_expiry < 7:
                    # Urgent - refresh now
                    results.append({
                        'credential_id': credential_id,
                        'eligible': True,
                        'reason': 'Expiring soon (< 7 days)',
                        'action': 'refresh_now',
                        'priority': 'high',
                        'days_remaining': days_until_expiry
                    })
                elif days_until_expiry < 30:
                    # Can refresh
                    results.append({
                        'credential_id': credential_id,
                        'eligible': True,
                        'reason': 'Eligible for refresh (< 30 days)',
                        'action': 'refresh_optional',
                        'priority': 'medium',
                        'days_remaining': days_until_expiry
                    })
                else:
                    # Too early
                    results.append({
                        'credential_id': credential_id,
                        'eligible': False,
                        'reason': f'{days_until_expiry:.0f} days remaining',
                        'action': 'none',
                        'days_remaining': days_until_expiry
                    })
                    
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing expiry for {credential_id}: {e}")
                results.append({
                    'credential_id': credential_id,
                    'eligible': False,
                    'reason': 'Invalid expiry format',
                    'action': 'none'
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'checked_at': current_time
        }), 200
        
    except Exception as e:
        logger.error(f"Eligibility check error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



