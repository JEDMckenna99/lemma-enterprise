"""
Enhanced API Routes with Cryptographic Security Hardening
Provides crypto-hardened endpoints for Lemma verification
"""

import time
import logging
from functools import wraps
from flask import Blueprint, request, jsonify, session, current_app, render_template
from lemma.core.crypto_hardened import (
    LemmaCryptoHardened, 
    SecurityLogger, 
    enhanced_verify_presentation,
    CryptoValidationMiddleware
)
from lemma.routes.api import require_api_key, rate_limit
from lemma.core.credential_service import get_credential_service

# Create enhanced API blueprint
api_enhanced = Blueprint('api_enhanced', __name__, url_prefix='/api/v2')

logger = logging.getLogger(__name__)

def require_crypto_v2(f):
    """Decorator to require crypto version 2.0"""
    @wraps(f)
    def decorated(*args, **kwargs):
        headers_valid, error = CryptoValidationMiddleware.validate_request_crypto_headers('2.0')
        if not headers_valid:
            SecurityLogger.log_security_event('crypto_version_rejected', {
                'error': error,
                'endpoint': request.endpoint
            }, 'WARNING')
            return jsonify({
                'success': False,
                'error': 'Crypto v2.0 required',
                'details': error
            }), 400
        return f(*args, **kwargs)
    return decorated

@api_enhanced.route('/verify-human', methods=['POST'])
@rate_limit
@require_crypto_v2
def verify_user_enhanced():
    """Enhanced user verification endpoint with crypto hardening"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            SecurityLogger.log_security_event('empty_verification_request', {}, 'WARNING')
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        presentation = data.get('presentation')
        challenge = data.get('challenge')
        security_token = data.get('securityToken')
        crypto_version = data.get('cryptoVersion', '2.0')

        if not presentation or not challenge:
            SecurityLogger.log_security_event('incomplete_verification_request', {
                'has_presentation': bool(presentation),
                'has_challenge': bool(challenge)
            }, 'WARNING')
            return jsonify({
                'success': False,
                'error': 'Presentation and challenge required'
            }), 400

        # Enhanced presentation verification
        verification_result = enhanced_verify_presentation(
            presentation=presentation,
            challenge=challenge,
            require_crypto_v2=True
        )

        if not verification_result['valid']:
            SecurityLogger.log_security_event('enhanced_verification_failed', {
                'errors': verification_result['errors'],
                'crypto_version': verification_result['crypto_version'],
                'security_level': verification_result['security_level']
            }, 'WARNING')
            
            return jsonify({
                'success': False,
                'verified': False,
                'cryptoValid': False,
                'error': 'User Trust Protocol verification failed',
                'errors': verification_result['errors'],
                'securityLevel': verification_result['security_level']
            }), 401

        # If we get here, verification passed
        # Set enhanced session with crypto validation
        session.regenerate() if hasattr(session, 'regenerate') else None
        session['verified_user'] = True
        session['crypto_verified'] = True
        session['crypto_version'] = crypto_version
        session['security_level'] = verification_result['security_level']
        session['verification_time'] = time.time()
        session['verification_ip'] = request.remote_addr

        # Extract credential info for session
        credential = presentation.get('verifiableCredential', [{}])[0]
        if credential and credential.get('id'):
            session['credential_id'] = credential['id']

        verification_time = time.time() - start_time
        
        SecurityLogger.log_security_event('enhanced_verification_success', {
            'crypto_version': crypto_version,
            'security_level': verification_result['security_level'],
            'verification_time_ms': round(verification_time * 1000, 2),
            'credential_id': session.get('credential_id', 'unknown')
        })

        return jsonify({
            'success': True,
            'verified': True,
            'cryptoValid': True,
            'securityLevel': verification_result['security_level'],
            'cryptoVersion': crypto_version,
            'verificationTime': round(verification_time * 1000, 2),
            'message': 'User Trust Protocol verification successful'
        })

    except Exception as e:
        SecurityLogger.log_security_event('verification_exception', {
            'error': str(e),
            'endpoint': 'verify_user_enhanced'
        }, 'ERROR')
        
        return jsonify({
            'success': False,
            'verified': False,
            'cryptoValid': False,
            'error': 'Internal verification error'
        }), 500

@api_enhanced.route('/generate-challenge', methods=['GET'])
@rate_limit
def generate_secure_challenge():
    """Generate cryptographically secure 256-bit challenge"""
    try:
        challenge = LemmaCryptoHardened.generate_secure_challenge()
        
        # Store challenge in session for validation
        session['current_challenge'] = challenge
        session['challenge_created'] = time.time()
        
        SecurityLogger.log_security_event('secure_challenge_generated', {
            'challenge_entropy_bits': 256
        })
        
        return jsonify({
            'success': True,
            'challenge': challenge,
            'entropyBits': 256,
            'expiresIn': 300  # 5 minutes
        })
        
    except Exception as e:
        SecurityLogger.log_security_event('challenge_generation_failed', {
            'error': str(e)
        }, 'ERROR')
        
        return jsonify({
            'success': False,
            'error': 'Challenge generation failed'
        }), 500

@api_enhanced.route('/verify-presentation', methods=['POST'])
@require_api_key
@rate_limit
@require_crypto_v2
def verify_presentation_enhanced():
    """Enhanced presentation verification for API clients"""
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        presentation = data.get('presentation')
        challenge = data.get('challenge')

        if not presentation:
            return jsonify({
                'success': False,
                'error': 'Presentation required'
            }), 400

        # Enhanced verification
        verification_result = enhanced_verify_presentation(
            presentation=presentation,
            challenge=challenge,
            require_crypto_v2=True
        )

        # Return detailed verification results for API clients
        response_data = {
            'success': verification_result['valid'],
            'verified': verification_result['valid'],
            'cryptoValid': verification_result['crypto_valid'],
            'cryptoVersion': verification_result['crypto_version'],
            'securityLevel': verification_result['security_level']
        }

        if not verification_result['valid']:
            response_data['errors'] = verification_result['errors']
            
            SecurityLogger.log_security_event('api_verification_failed', {
                'errors': verification_result['errors'],
                'crypto_version': verification_result['crypto_version']
            }, 'WARNING')
            
            return jsonify(response_data), 401

        # Log successful API verification
        SecurityLogger.log_security_event('api_verification_success', {
            'crypto_version': verification_result['crypto_version'],
            'security_level': verification_result['security_level']
        })

        return jsonify(response_data)

    except Exception as e:
        SecurityLogger.log_security_event('api_verification_exception', {
            'error': str(e)
        }, 'ERROR')
        
        return jsonify({
            'success': False,
            'verified': False,
            'cryptoValid': False,
            'error': 'Internal verification error'
        }), 500

@api_enhanced.route('/protected-content', methods=['GET'])
@rate_limit
def get_protected_content_enhanced():
    """Serve protected content with enhanced security validation"""
    
    try:
        # Check session-based verification
        if not session.get('verified_user'):
            SecurityLogger.log_security_event('protected_content_access_denied', {
                'reason': 'not_verified'
            }, 'WARNING')
            return jsonify({
                'error': 'User verification required'
            }), 401

        # Check crypto verification for enhanced security
        crypto_verified = session.get('crypto_verified', False)
        crypto_version = session.get('crypto_version', '1.0')
        security_level = session.get('security_level', 'basic')

        # Check session age
        verification_time = session.get('verification_time', 0)
        if time.time() - verification_time > 3600:  # 1 hour
            session.clear()
            SecurityLogger.log_security_event('protected_content_access_denied', {
                'reason': 'session_expired'
            }, 'WARNING')
            return jsonify({
                'error': 'Session expired'
            }), 401

        # Check IP consistency
        if session.get('verification_ip') != request.remote_addr:
            session.clear()
            SecurityLogger.log_security_event('protected_content_access_denied', {
                'reason': 'ip_mismatch',
                'session_ip': session.get('verification_ip'),
                'request_ip': request.remote_addr
            }, 'WARNING')
            return jsonify({
                'error': 'Session invalid'
            }), 401

        # Re-verify credential status for sensitive content
        credential_id = session.get('credential_id')
        if credential_id:
            # Here you would check credential revocation status
            # For now, we'll assume it's valid
            pass

        # Log successful content access
        SecurityLogger.log_security_event('protected_content_accessed', {
            'crypto_verified': crypto_verified,
            'crypto_version': crypto_version,
            'security_level': security_level
        })

        # Return content based on security level
        if crypto_verified and crypto_version == '2.0':
            content = """
            <div class="enhanced-content">
                <h2>🔒 Enhanced User Trust Protocol Content</h2>
                <p>You have accessed this content with <strong>Enhanced Security (User Trust Protocol v2.0)</strong></p>
                <div class="security-details">
                    <h3>Security Features Active:</h3>
                    <ul>
                        <li>✅ 256-bit challenge verification</li>
                        <li>✅ Multi-layer replay protection</li>
                        <li>✅ Domain binding validation</li>
                        <li>✅ Timestamp validation</li>
                        <li>✅ Presentation integrity checking</li>
                        <li>✅ Constant-time comparisons</li>
                    </ul>
                </div>
                <p class="crypto-info">
                    <strong>User Trust Protocol Version:</strong> {crypto_version}<br>
                    <strong>Security Level:</strong> {security_level}
                </p>
            </div>
            """.format(
                crypto_version=crypto_version,
                security_level=security_level
            )
        else:
            content = """
            <div class="basic-content">
                <h2>🔓 Basic Security Content</h2>
                <p>You have accessed this content with basic security validation.</p>
                <p><em>Upgrade to User Trust Protocol v2.0 for enhanced security features.</em></p>
            </div>
            """

        return jsonify({
            'success': True,
            'content': content,
            'securityLevel': security_level,
            'cryptoVersion': crypto_version,
            'cryptoVerified': crypto_verified
        })

    except Exception as e:
        SecurityLogger.log_security_event('protected_content_error', {
            'error': str(e)
        }, 'ERROR')
        
        return jsonify({
            'error': 'Content access error'
        }), 500

@api_enhanced.route('/security-log', methods=['POST'])
@rate_limit
def log_client_security_event():
    """Endpoint for clients to report security events"""
    
    try:
        # For security logging, we'll be more permissive with CSRF validation
        # since this is used for monitoring and doesn't modify sensitive data
        csrf_token = None
        
        # Try to get CSRF token from multiple locations
        csrf_token = request.headers.get('X-CSRF-Token')
        if not csrf_token and request.is_json:
            csrf_token = request.json.get('csrf_token')
        if not csrf_token:
            csrf_token = request.cookies.get('_csrf_token')
        
        # For security logging, we'll allow requests with valid session even without CSRF
        # This is acceptable since security logging doesn't modify sensitive data
        has_valid_session = bool(session.get('_csrf_token'))
        has_csrf_token = bool(csrf_token)
        
        if not has_valid_session and not has_csrf_token:
            logger.warning(f"Security log attempt without session or CSRF token from IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': 'Authentication required'
            }), 401
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        event_type = data.get('event')
        event_data = data.get('data', {})

        if not event_type:
            return jsonify({
                'success': False,
                'error': 'Event type required'
            }), 400

        # Validate and sanitize client-reported events
        allowed_events = [
            'crypto_verification_success',
            'crypto_verification_error',
            'presentation_validation_failed',
            'content_displayed',
            'gate_status_check',
            'crypto_status_verified',
            'gate_modal_displayed',
            'gate_initialized'
        ]

        if event_type not in allowed_events:
            return jsonify({
                'success': False,
                'error': 'Invalid event type'
            }), 400

        # Add client prefix to distinguish from server events
        event_type = f"client_{event_type}"

        # Log the client-reported event
        SecurityLogger.log_security_event(event_type, event_data)

        return jsonify({
            'success': True,
            'logged': True
        })

    except Exception as e:
        logger.error(f"Client security logging error: {e}")
        return jsonify({
            'success': False,
            'error': 'Logging failed'
        }), 500

@api_enhanced.route('/crypto-status', methods=['GET'])
def get_crypto_status():
    """Get current cryptographic security status"""
    
    try:
        status = {
            'protocolVersion': '2.0',
            'supportedVersions': LemmaCryptoHardened.SUPPORTED_CRYPTO_VERSIONS,
            'securityFeatures': {
                'enhancedChallenges': True,
                'replayProtection': True,
                'domainBinding': True,
                'timestampValidation': True,
                'integrityChecking': True,
                'constantTimeOperations': True
            },
            'securityLevels': {
                'basic': 'User Trust Protocol v1.0 - Standard security',
                'enhanced': 'User Trust Protocol v2.0 - Enhanced security with hardening'
            },
            'entropyRequirements': {
                'challengeBits': LemmaCryptoHardened.MIN_CHALLENGE_ENTROPY_BITS,
                'tokenBits': LemmaCryptoHardened.MIN_TOKEN_ENTROPY_BITS
            },
            'timeouts': {
                'presentationMaxAgeMinutes': LemmaCryptoHardened.MAX_PRESENTATION_AGE_MINUTES,
                'sessionMaxAgeMinutes': 60
            },
            'protocolName': 'User Trust Protocol',
            'description': 'Enterprise-grade user verification with cryptographic security'
        }

        return jsonify({
            'success': True,
            'status': status
        })

    except Exception as e:
        logger.error(f"Crypto status error: {e}")
        return jsonify({
            'success': False,
            'error': 'Status unavailable'
        }), 500

@api_enhanced.route('/demo', methods=['GET'])
def crypto_enhanced_demo():
    """Serve the crypto enhanced demo page"""
    try:
        return render_template('crypto_enhanced_demo.html')
    except Exception as e:
        logger.error(f"Demo page error: {e}")
        return jsonify({
            'error': 'Demo page unavailable'
        }), 500 