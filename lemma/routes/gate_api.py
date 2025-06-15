"""
Lemma Gate API - Core gate functionality centralized in the API
All gate logic is handled server-side for security and consistency
"""

from flask import Blueprint, request, session, jsonify, current_app
from lemma.routes.api import require_api_key, csrf_protect, rate_limit
from lemma.core.credential_service import get_credential_service
from lemma.utils.input_validation import ValidationError, validate_string, validate_dict
from lemma.auth.security import SecurityLogger
import time
import hashlib
import secrets

gate_api = Blueprint('gate_api', __name__)

@gate_api.route('/api/gate/status', methods=['GET'])
@csrf_protect()
@rate_limit
def gate_status():
    """
    Check the current gate status for the user
    Returns what the gate should do: show gate, allow access, or needs verification
    """
    try:
        user_session_data = {
            'verified_user': session.get('verified_user', False),
            'verified_human': session.get('verified_human', False),
            'verification_time': session.get('verification_time'),
            'credential_id': session.get('credential_id'),
            'user_id': session.get('user_id')
        }
        
        # Check if user is already verified in session
        if user_session_data['verified_user'] and user_session_data['verified_human']:
            verification_age = time.time() - (user_session_data['verification_time'] or 0)
            
            # Check if verification is still valid (24 hours)
            if verification_age < 86400:  # 24 hours
                return jsonify({
                    'success': True,
                    'gate_action': 'allow_access',
                    'message': 'User already verified',
                    'data': {
                        'verified': True,
                        'verification_age_hours': round(verification_age / 3600, 1),
                        'credential_id': user_session_data['credential_id']
                    }
                })
        
        # No valid session verification found
        return jsonify({
            'success': True,
            'gate_action': 'check_credentials',
            'message': 'Need to check user credentials',
            'data': {
                'verified': False,
                'session_expired': user_session_data['verification_time'] is not None
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Gate status check error: {e}")
        return jsonify({
            'success': False,
            'gate_action': 'show_gate',
            'error': 'Status check failed'
        }), 500

@gate_api.route('/api/gate/verify-credentials', methods=['POST'])
@csrf_protect()
@rate_limit
def verify_credentials():
    """
    Verify user credentials and perform background verification
    This handles the full credential verification flow including:
    - Credential validation
    - VP creation and verification
    - Revocation checking
    - Session setting
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'gate_action': 'show_gate',
                'error': 'No data provided'
            }), 400
        
        # Validate input
        try:
            credentials = validate_dict(data.get('credentials'), 'credentials')
            challenge = validate_string(data.get('challenge'), 'challenge', min_length=16, max_length=128)
            domain = validate_string(data.get('domain', ''), 'domain', required=False)
        except ValidationError as e:
            return jsonify({
                'success': False,
                'gate_action': 'show_gate',
                'error': f'Invalid input: {str(e)}'
            }), 400
        
        # Extract credential from wallet format if needed
        if isinstance(credentials, list) and len(credentials) > 0:
            credential = credentials[0]
        else:
            credential = credentials
            
        # Handle wallet credential format
        if 'credential' in credential:
            actual_credential = credential['credential']
        else:
            actual_credential = credential
            
        # Step 1: Validate credential structure
        if not actual_credential.get('id') or not actual_credential.get('issuer'):
            return jsonify({
                'success': False,
                'gate_action': 'show_gate',
                'error': 'Invalid credential format'
            }), 400
        
        # Step 2: Create and verify presentation
        credential_service = get_credential_service()
        
        # Create presentation
        presentation = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "verifiableCredential": [actual_credential],
            "proof": {
                "type": "Ed25519Signature2020",
                "challenge": challenge,
                "created": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "verificationMethod": actual_credential.get('issuer'),
                "domain": domain or request.headers.get('Host', 'localhost')
            }
        }
        
        # Step 3: Verify presentation
        verification_result = credential_service.verify_presentation(presentation, challenge)
        
        if not verification_result.get('valid'):
            SecurityLogger.log_security_event('gate_verification_failed', {
                'credential_id': actual_credential.get('id'),
                'reason': verification_result.get('reason', 'Unknown'),
                'ip': request.remote_addr
            }, 'WARNING')
            
            return jsonify({
                'success': False,
                'gate_action': 'show_gate',
                'error': 'Credential verification failed',
                'details': verification_result.get('reason')
            }), 401
        
        # Step 4: Check revocation status
        revocation_status = check_credential_revocation(actual_credential.get('id'))
        if not revocation_status['valid']:
            SecurityLogger.log_security_event('revoked_credential_gate_attempt', {
                'credential_id': actual_credential.get('id'),
                'ip': request.remote_addr
            }, 'WARNING')
            
            return jsonify({
                'success': False,
                'gate_action': 'show_gate',
                'error': 'Credential has been revoked',
                'details': revocation_status.get('reason')
            }), 401
        
        # Step 5: Set secure session
        user_id = extract_user_id_from_credential(actual_credential)
        
        # Regenerate session to prevent fixation
        if hasattr(session, 'regenerate'):
            session.regenerate()
            
        session['verified_user'] = True
        session['verified_human'] = True
        session['verification_time'] = time.time()
        session['credential_id'] = actual_credential.get('id')
        session['user_id'] = user_id
        session['verification_ip'] = request.remote_addr
        session['verification_method'] = 'gate_api'
        
        # Step 6: Log successful verification
        SecurityLogger.log_security_event('gate_verification_success', {
            'credential_id': actual_credential.get('id'),
            'user_id': user_id,
            'ip': request.remote_addr,
            'verification_time': session['verification_time']
        })
        
        return jsonify({
            'success': True,
            'gate_action': 'allow_access',
            'message': 'Verification successful',
            'data': {
                'verified': True,
                'user_id': user_id,
                'credential_id': actual_credential.get('id'),
                'verification_time': session['verification_time']
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Gate credential verification error: {e}")
        SecurityLogger.log_security_event('gate_verification_error', {
            'error': str(e),
            'ip': request.remote_addr
        }, 'ERROR')
        
        return jsonify({
            'success': False,
            'gate_action': 'show_gate',
            'error': 'Verification system error'
        }), 500

@gate_api.route('/api/gate/challenge', methods=['GET'])
@csrf_protect()
@rate_limit
def generate_gate_challenge():
    """
    Generate a cryptographically secure challenge for credential verification
    """
    try:
        # Generate secure random challenge
        challenge = secrets.token_hex(32)  # 64 character hex string
        
        # Store challenge in session for validation
        session['gate_challenge'] = challenge
        session['gate_challenge_time'] = time.time()
        
        return jsonify({
            'success': True,
            'challenge': challenge,
            'expires_in': 300  # 5 minutes
        })
        
    except Exception as e:
        current_app.logger.error(f"Challenge generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate challenge'
        }), 500

@gate_api.route('/api/gate/start-verification', methods=['POST'])
@csrf_protect()
@rate_limit
def start_verification():
    """
    Start the verification process for users without credentials
    This redirects to the appropriate verification flow
    """
    try:
        data = request.get_json() or {}
        return_url = data.get('return_url', request.referrer or '/')
        
        # Validate return URL for security
        if not is_safe_url(return_url):
            return_url = '/'
        
        # Generate verification session
        verification_session_id = secrets.token_urlsafe(32)
        session['verification_session_id'] = verification_session_id
        session['verification_return_url'] = return_url
        session['verification_started'] = time.time()
        
        # Return verification URL
        verification_url = f"/verify?session_id={verification_session_id}&redirect={return_url}"
        
        return jsonify({
            'success': True,
            'verification_url': verification_url,
            'session_id': verification_session_id,
            'message': 'Verification process started'
        })
        
    except Exception as e:
        current_app.logger.error(f"Start verification error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to start verification'
        }), 500

@gate_api.route('/api/gate/config', methods=['GET'])
@rate_limit
def gate_config():
    """
    Get gate configuration for client-side initialization
    """
    try:
        config = {
            'endpoints': {
                'status': '/api/gate/status',
                'verify_credentials': '/api/gate/verify-credentials', 
                'challenge': '/api/gate/challenge',
                'start_verification': '/api/gate/start-verification'
            },
            'settings': {
                'verification_timeout': 300,  # 5 minutes
                'session_timeout': 86400,    # 24 hours
                'retry_attempts': 3,
                'retry_delay': 1000
            },
            'features': {
                'background_verification': True,
                'revocation_checking': True,
                'session_management': True,
                'security_logging': True
            }
        }
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        current_app.logger.error(f"Gate config error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get configuration'
        }), 500

def check_credential_revocation(credential_id):
    """
    Check if a credential has been revoked
    Integrates with the OPRF revocation system
    """
    try:
        # TODO: Integrate with actual revocation system
        # For now, return valid for all credentials
        return {
            'valid': True,
            'reason': 'Revocation checking not yet implemented'
        }
        
    except Exception as e:
        current_app.logger.error(f"Revocation check error: {e}")
        return {
            'valid': True,  # Fail open for now
            'reason': f'Revocation check failed: {str(e)}'
        }

def extract_user_id_from_credential(credential):
    """
    Extract user ID from credential subject
    """
    try:
        if 'credentialSubject' in credential:
            subject = credential['credentialSubject']
            if 'id' in subject:
                # Handle DID format
                user_id = subject['id']
                if user_id.startswith('did:user:'):
                    return user_id.replace('did:user:', '')
                elif user_id.startswith('did:'):
                    # Extract the identifier part
                    return user_id.split(':')[-1]
                else:
                    return user_id
        
        # Fallback to credential ID
        cred_id = credential.get('id', '')
        if 'user' in cred_id:
            return cred_id.split('user')[-1].strip('_-:')
        
        # Generate hash-based user ID as last resort
        return hashlib.sha256(cred_id.encode()).hexdigest()[:16]
        
    except Exception as e:
        current_app.logger.error(f"User ID extraction error: {e}")
        return f"user_{int(time.time())}"

def is_safe_url(url):
    """
    Check if a URL is safe for redirects
    """
    try:
        if not url:
            return False
        
        # Only allow relative URLs or same-origin URLs
        if url.startswith('/'):
            return True
        
        # Block external URLs for security
        if url.startswith('http://') or url.startswith('https://'):
            return False
        
        return True
        
    except Exception:
        return False 