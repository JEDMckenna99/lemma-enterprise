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


@sdk_auth_bp.route('/api/auth/exchange-proof', methods=['POST', 'OPTIONS'])
@cross_origin()
def exchange_proof_for_token():
    """
    Exchange a verified site permission proof for a short-lived access token.

    Request body:
        credential: Permission lemma credential object
        site_id: Optional site binding assertion
        requested_scope: Optional string or list, must be subset of credential scope
        ttl_seconds: Optional token TTL (default 900, min 300, max 3600)
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json() or {}
        credential = data.get('credential')
        if not isinstance(credential, dict):
            return jsonify({'success': False, 'error': 'credential object required'}), 400

        from .trusted_issuers import verify_credential_with_trust
        verification = verify_credential_with_trust(credential)
        if not verification.get('valid'):
            return jsonify({
                'success': False,
                'error': 'invalid_proof',
                'reason': verification.get('reason'),
                'issuer_trusted': verification.get('issuer_trusted', False),
                'signature_valid': verification.get('signature_valid', False),
            }), 401

        claims = credential.get('claims') or credential.get('credentialSubject') or {}
        subject = (
            credential.get('subject')
            or credential.get('sub')
            or claims.get('sub')
            or claims.get('ppid')
            or claims.get('id')
        )
        if not subject:
            return jsonify({'success': False, 'error': 'credential subject missing'}), 400

        credential_site = (claims.get('siteId') or claims.get('site_id') or '').strip().lower()
        requested_site = (data.get('site_id') or '').strip().lower()
        if requested_site and credential_site and requested_site != credential_site:
            return jsonify({
                'success': False,
                'error': 'site_mismatch',
                'message': f'Credential is bound to {credential_site}, not {requested_site}.'
            }), 403
        site_id = requested_site or credential_site
        if not site_id:
            return jsonify({'success': False, 'error': 'site_id missing in request and credential'}), 400

        permission_id = (
            claims.get('permissionId')
            or claims.get('permission_id')
            or claims.get('permission')
            or claims.get('accountType')
            or 'read'
        )

        raw_scopes = claims.get('scope', [])
        if isinstance(raw_scopes, str):
            scopes = [s.strip().lower() for s in raw_scopes.split(',') if s.strip()]
        elif isinstance(raw_scopes, list):
            scopes = [str(s).strip().lower() for s in raw_scopes if str(s).strip()]
        else:
            scopes = []

        if not scopes:
            scopes = ['admin', 'write', 'read'] if 'admin' in str(permission_id).lower() else ['read']

        requested_scope = data.get('requested_scope')
        if requested_scope:
            if isinstance(requested_scope, str):
                requested = [s.strip().lower() for s in requested_scope.split(',') if s.strip()]
            elif isinstance(requested_scope, list):
                requested = [str(s).strip().lower() for s in requested_scope if str(s).strip()]
            else:
                requested = []
            if requested and not set(requested).issubset(set(scopes)):
                return jsonify({
                    'success': False,
                    'error': 'scope_escalation_denied',
                    'granted_scope': scopes
                }), 403
            if requested:
                scopes = requested

        ttl_seconds = int(data.get('ttl_seconds', 900))
        from .access_tokens import issue_access_token
        access_token, expires_in = issue_access_token(
            subject=subject,
            site_id=site_id,
            permission_id=str(permission_id),
            scopes=scopes,
            credential_id=credential.get('id'),
            issuer_did=credential.get('issuer'),
            ttl_seconds=ttl_seconds,
        )

        return jsonify({
            'success': True,
            'token_type': 'Bearer',
            'access_token': access_token,
            'expires_in': expires_in,
            'site_id': site_id,
            'subject': subject,
            'scope': scopes,
            'permission_id': permission_id,
        }), 200
    except Exception as e:
        logger.error(f"Proof exchange error: {e}")
        return jsonify({'success': False, 'error': 'exchange_failed'}), 500


# Clean up old pending requests periodically
def cleanup_pending_requests():
    """Remove pending requests older than 10 minutes"""
    import time
    current_time = time.time()
    expired = [k for k, v in pending_sdk_requests.items() 
               if current_time - v['created_at'] > 600]
    for k in expired:
        del pending_sdk_requests[k]

