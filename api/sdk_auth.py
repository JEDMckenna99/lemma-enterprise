"""
SDK Authentication API for External Sites
Handles sign-in flow for sites using Lemma Sign-In SDK
"""

import os
import secrets
import logging
from flask import Blueprint, request, jsonify, redirect, render_template_string
from flask_cors import cross_origin
from urllib.parse import urlencode, urlparse

logger = logging.getLogger(__name__)

sdk_auth_bp = Blueprint('sdk_auth', __name__)

# Store pending SDK auth requests (in production, use Redis)
pending_sdk_requests = {}


@sdk_auth_bp.route('/auth/sdk-request', methods=['GET'])
@cross_origin()
def sdk_auth_request():
    """
    SDK sign-in request endpoint
    Called when user clicks "Sign in with Lemma" button
    
    Query params:
        site: Site ID or domain
        return: Return URL after authentication
    """
    site_id = request.args.get('site', '')
    return_url = request.args.get('return', '')
    
    if not site_id:
        return jsonify({'error': 'Site ID required'}), 400
    
    if not return_url:
        return jsonify({'error': 'Return URL required'}), 400
    
    # Validate return URL (basic security check)
    try:
        parsed = urlparse(return_url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': 'Invalid return URL'}), 400
    except Exception:
        return jsonify({'error': 'Invalid return URL'}), 400
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store pending request
    pending_sdk_requests[state] = {
        'site_id': site_id,
        'return_url': return_url,
        'created_at': __import__('time').time()
    }
    
    # Redirect to login with SDK context
    params = urlencode({
        'sdk_state': state,
        'site_id': site_id,
        'return_url': return_url
    })
    
    return redirect(f'/login?{params}')


@sdk_auth_bp.route('/auth/sdk-callback', methods=['GET'])
@cross_origin()
def sdk_auth_callback():
    """
    SDK callback after successful authentication
    Redirects back to the external site with success status
    """
    state = request.args.get('state', '')
    
    if not state or state not in pending_sdk_requests:
        return jsonify({'error': 'Invalid or expired session'}), 400
    
    pending = pending_sdk_requests.pop(state)
    return_url = pending['return_url']
    
    # Add success indicator to return URL
    separator = '&' if '?' in return_url else '?'
    return redirect(f"{return_url}{separator}lemma_auth=success")


@sdk_auth_bp.route('/api/auth/signout', methods=['POST', 'OPTIONS'])
@cross_origin()
def sdk_signout():
    """
    Sign out endpoint for SDK
    Clears any server-side session (if applicable)
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    # In session-free architecture, sign-out is primarily client-side
    # This endpoint exists for compatibility and future session management
    return jsonify({
        'success': True,
        'message': 'Signed out successfully'
    })


@sdk_auth_bp.route('/api/verify-credential', methods=['POST', 'OPTIONS'])
@cross_origin()
def verify_credential():
    """
    Verify a credential is still valid
    Used by SDK to check credential validity
    
    SECURITY: Now includes trusted issuer validation to reject credentials
    signed by unknown/revoked issuers.
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        data = request.get_json()
        credential = data.get('credential', {})
        
        if not credential:
            return jsonify({'valid': False, 'error': 'No credential provided'}), 400
        
        # Use secure verification with trusted issuer check
        from .trusted_issuers import verify_credential_with_trust
        result = verify_credential_with_trust(credential)
        
        claims = credential.get('claims', credential.get('credentialSubject', {}))
        
        return jsonify({
            'valid': result['valid'],
            'claims': claims if result['valid'] else {},
            'reason': result.get('reason'),
            'issuer_trusted': result['issuer_trusted'],
            'signature_valid': result['signature_valid']
        })
        
    except Exception as e:
        logger.error(f"Credential verification error: {e}")
        return jsonify({'valid': False, 'error': str(e)}), 500


# Clean up old pending requests periodically
def cleanup_pending_requests():
    """Remove pending requests older than 10 minutes"""
    import time
    current_time = time.time()
    expired = [k for k, v in pending_sdk_requests.items() 
               if current_time - v['created_at'] > 600]
    for k in expired:
        del pending_sdk_requests[k]

