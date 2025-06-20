"""
Lemma Shield API - Core shield functionality centralized in the API
All shield logic is handled server-side for security and consistency
Enhanced with enterprise security controls and revocation management
"""

from flask import Blueprint, request, session, jsonify, current_app, render_template
from lemma.routes.api import require_api_key, csrf_protect, rate_limit
from lemma.core.credential_service import get_credential_service
from lemma.utils.input_validation import ValidationError, InputValidator
from lemma.core.crypto_hardened import SecurityLogger
import time
import hashlib
import secrets
import json
import os

shield_api = Blueprint('shield_api', __name__)

@shield_api.route('/api/shield/config', methods=['GET'])
@rate_limit
def shield_config():
    """Get Shield configuration for the requested security level."""
    try:
        security_level = request.args.get('security_level', 'standard')
        if security_level not in SECURITY_LEVELS:
            security_level = 'standard'
        
        config = SECURITY_LEVELS[security_level]
        
        return jsonify({
            'success': True,
            'config': {
                'security_level': security_level,
                'settings': config,
                'available_levels': list(SECURITY_LEVELS.keys())
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Shield config error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to load configuration'
        }), 500

# Security Level Configurations
SECURITY_LEVELS = {
    'basic': {
        'did_verification_interval': 86400,  # 24 hours
        'revocation_check_interval': 3600,   # 1 hour
        'session_timeout': 86400,            # 24 hours
        'require_fresh_verification': False,
        'max_verification_age': 604800       # 7 days
    },
    'standard': {
        'did_verification_interval': 3600,   # 1 hour
        'revocation_check_interval': 1800,   # 30 minutes
        'session_timeout': 28800,            # 8 hours
        'require_fresh_verification': False,
        'max_verification_age': 259200       # 3 days
    },
    'high': {
        'did_verification_interval': 1800,   # 30 minutes
        'revocation_check_interval': 900,    # 15 minutes
        'session_timeout': 14400,            # 4 hours
        'require_fresh_verification': True,
        'max_verification_age': 86400        # 1 day
    },
    'maximum': {
        'did_verification_interval': 300,    # 5 minutes
        'revocation_check_interval': 300,    # 5 minutes
        'session_timeout': 3600,             # 1 hour
        'require_fresh_verification': True,
        'max_verification_age': 3600         # 1 hour
    }
}

@shield_api.route('/api/shield/status', methods=['GET', 'POST'])
@rate_limit
def shield_status():
    """
    Check the current shield status for the user with configurable security levels
    Returns what the shield should do: show shield, allow access, or needs verification
    
    GET: Check session-based status
    POST: Verify credentials sent from wallet for offline verification
    """
    try:
        # Get security level from request or default to 'standard'
        if request.method == 'GET':
            security_level = request.args.get('security_level', 'standard')
            credential_data = None
        else:  # POST
            data = request.get_json() or {}
            security_level = data.get('security_level', 'standard')
            credential_data = data.get('credential')
        
        if security_level not in SECURITY_LEVELS:
            security_level = 'standard'
        
        config = SECURITY_LEVELS[security_level]
        
        user_session_data = {
            'verified_user': session.get('verified_user', False),
            'verified_human': session.get('verified_human', False),
            'verification_time': session.get('verification_time'),
            'last_did_check': session.get('last_did_check'),
            'last_revocation_check': session.get('last_revocation_check'),
            'credential_id': session.get('credential_id'),
            'user_id': session.get('user_id'),
            'security_level': session.get('security_level', 'standard')
        }
        
        current_time = time.time()
        
        # Check if user is verified in session
        if user_session_data['verified_user'] and user_session_data['verified_human']:
            verification_age = current_time - (user_session_data['verification_time'] or 0)
            
            # Check if verification is too old for this security level
            if verification_age > config['max_verification_age']:
                SecurityLogger.log_security_event('verification_expired', {
                    'credential_id': user_session_data['credential_id'],
                    'verification_age': verification_age,
                    'max_age': config['max_verification_age'],
                    'security_level': security_level
                }, 'INFO')
                
                return jsonify({
                    'success': True,
                    'shield_action': 'require_reverification',
                    'message': 'Verification expired for security level',
                    'data': {
                        'verified': False,
                        'reason': 'verification_expired',
                        'security_level': security_level,
                        'verification_age_hours': round(verification_age / 3600, 1),
                        'max_age_hours': round(config['max_verification_age'] / 3600, 1)
                    }
                })
            
            # Check if session has expired
            if verification_age > config['session_timeout']:
                return jsonify({
                    'success': True,
                    'shield_action': 'check_credentials',
                    'message': 'Session expired, need to re-verify',
                    'data': {
                        'verified': False,
                        'reason': 'session_expired',
                        'security_level': security_level
                    }
                })
            
            # Check if we need fresh DID verification
            last_did_check = user_session_data['last_did_check'] or 0
            if (current_time - last_did_check) > config['did_verification_interval']:
                return jsonify({
                    'success': True,
                    'shield_action': 'verify_did',
                    'message': 'DID verification required',
                    'data': {
                        'verified': True,
                        'needs_did_check': True,
                        'security_level': security_level,
                        'credential_id': user_session_data['credential_id']
                    }
                })
            
            # Check if we need fresh revocation check
            last_revocation_check = user_session_data['last_revocation_check'] or 0
            if (current_time - last_revocation_check) > config['revocation_check_interval']:
                return jsonify({
                    'success': True,
                    'shield_action': 'check_revocation',
                    'message': 'Revocation check required',
                    'data': {
                        'verified': True,
                        'needs_revocation_check': True,
                        'security_level': security_level,
                        'credential_id': user_session_data['credential_id']
                    }
                })
            
            # All checks passed
            return jsonify({
                'success': True,
                'shield_action': 'allow_access',
                'message': 'User verified and current',
                'data': {
                    'verified': True,
                    'verification_age_hours': round(verification_age / 3600, 1),
                    'credential_id': user_session_data['credential_id'],
                    'security_level': security_level,
                    'next_did_check_in': config['did_verification_interval'] - (current_time - last_did_check),
                    'next_revocation_check_in': config['revocation_check_interval'] - (current_time - last_revocation_check)
                }
            })
        
        # No valid session verification found - BUT check if user has credentials in wallet
        # This handles the case when user returns to page and session expired but credentials exist
        
        # Check if there's a credential available for verification
        if credential_data:
            # Get credential service instance
            from lemma.core.credential_service import LemmaCredentialService
            credential_service = LemmaCredentialService()
            
            # Check if credential supports offline verification
            if credential_data.get('offline_capable', False):
                # Use offline verification - no API calls needed!
                verification_result = credential_service.verify_credential_offline(credential_data)
            else:
                # Fall back to online verification
                verification_result = credential_service.verify_credential(credential_data)
            
            if verification_result.get('valid'):
                # Store verification status in session
                current_time = time.time()
                session['verified_human'] = True
                session['verification_time'] = current_time
                session['user_id'] = extract_user_id_from_credential(credential_data)
                session['credential_id'] = credential_data.get('id', f"credential-{session['user_id']}")
                session['last_did_check'] = current_time
                session['last_revocation_check'] = current_time
                
                # Include verification mode in response
                verification_mode = verification_result.get('verification_mode', 'online')
                offline_verified = verification_result.get('offline_verification', False)
                
                return jsonify({
                    'success': True,
                    'shield_action': 'allow_access',
                    'message': f'User verified via {verification_mode}',
                    'verification_mode': verification_mode,
                    'offline_verification': offline_verified,
                    'verification_time_ms': verification_result.get('verification_time_ms'),
                    'witness_valid_until': verification_result.get('witness_valid_until'),
                    'sync_required': verification_result.get('sync_required', False),
                    'user_id': session.get('user_id'),
                    'credential': credential_data if credential_data.get('offline_capable') else None
                })
            else:
                # Verification failed
                verification_mode = verification_result.get('verification_mode', 'unknown')
                sync_required = verification_result.get('sync_required', False)
                
                return jsonify({
                    'success': False,
                    'shield_action': 'verify_did' if not sync_required else 'sync_required',
                    'message': f'Verification failed: {verification_result.get("error", "Unknown error")}',
                    'verification_mode': verification_mode,
                    'sync_required': sync_required,
                    'error': verification_result.get('error')
                }), 400
                
        else:
            # No credential provided in request, suggest checking wallet
            return jsonify({
                'success': True,
                'shield_action': 'check_credentials',  # This will trigger wallet check
                'message': 'Need to check user credentials or wallet',
                'data': {
                    'verified': False,
                    'session_expired': user_session_data['verification_time'] is not None,
                    'security_level': security_level,
                    'check_wallet': True  # Signal to check wallet for existing credentials
                }
            })
        
    except Exception as e:
        current_app.logger.error(f"shield status check error: {e}")
        return jsonify({
            'success': False,
            'shield_action': 'show_shield',
            'error': 'Status check failed'
        }), 500

@shield_api.route('/api/shield/verify-credentials', methods=['POST'])
@csrf_protect()
@rate_limit
def verify_credentials():
    """
    Verify user credentials and perform background verification
    Enhanced with configurable security levels and comprehensive checks
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'shield_action': 'show_shield',
                'error': 'No data provided'
            }), 400
        
        # Handle inline verification status check first
        if data.get('check_inline_verification'):
            user_id = data.get('user_id')
            session_id = data.get('session_id')
            
            if not user_id:
                return jsonify({
                    'success': False,
                    'error': 'User ID required for inline verification check'
                }), 400
            
            # Check if verification was completed via Stripe callback
            verification_result = check_stripe_verification_completion(user_id, session_id)
            
            if verification_result['success']:
                # Store verification status in session
                current_time = time.time()
                session['lemma_verified'] = True
                session['lemma_verification_time'] = current_time
                session['lemma_user_id'] = user_id
                session['verified_user'] = True
                session['verified_human'] = True
                session['verification_time'] = current_time
                session['user_id'] = user_id
                
                # CRITICAL FIX: Get the credential and include it in the response
                credential_service = get_credential_service()
                try:
                    # Get the credential for this user
                    user_credential = credential_service.get_user_credential(user_id)
                    
                    if user_credential:
                        # Format credential for wallet storage
                        wallet_credential = {
                            "credential": user_credential,
                            "wallet_metadata": {
                                "added_at": user_credential.get('issuanceDate', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                                "holder_id": user_id,
                                "status": "active",
                                "display_name": "Lemma Human Verification",
                                "fingerprint": user_credential.get('id', f"credential-{user_id}")
                            }
                        }
                        
                        # Include credential in response for immediate wallet storage
                        return jsonify({
                            'success': True,
                            'verified': True,
                            'shield_action': 'allow_access',
                            'verification_status': 'verified',
                            'credential': wallet_credential,  # Include credential for wallet storage
                            'data': verification_result.get('claims', {}),
                            'message': 'Inline verification completed successfully'
                        })
                    else:
                        current_app.logger.warning(f"No credential found for verified user {user_id}")
                        
                except Exception as e:
                    current_app.logger.error(f"Error retrieving credential for user {user_id}: {e}")
                
                # Fallback response without credential (should not happen if verification succeeded)
                return jsonify({
                    'success': True,
                    'verified': True,
                    'shield_action': 'allow_access',
                    'verification_status': 'verified',
                    'data': verification_result.get('claims', {}),
                    'message': 'Inline verification completed successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'verified': False,
                    'shield_action': 'show_shield',
                    'verification_status': 'pending',
                    'error': verification_result.get('error', 'Verification incomplete'),
                    'message': 'Inline verification not yet completed'
                })
        
        # Validate input for credential verification (only if not doing inline check)
        try:
            credentials = InputValidator.validate_dict(data.get('credentials'), 'credentials')
            challenge = InputValidator.validate_string(data.get('challenge'), 'challenge', min_length=16, max_length=128)
            domain = InputValidator.validate_string(data.get('domain', ''), 'domain', min_length=0, max_length=255)
            security_level = InputValidator.validate_string(data.get('security_level', 'standard'), 'security_level', min_length=1, max_length=20)
            force_reverification = data.get('force_reverification', False)
        except ValidationError as e:
            return jsonify({
                'success': False,
                'shield_action': 'show_shield',
                'error': f'Invalid input: {str(e)}'
            }), 400
        
        # Validate security level
        if security_level not in SECURITY_LEVELS:
            security_level = 'standard'
        
        config = SECURITY_LEVELS[security_level]
        
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
                'shield_action': 'show_shield',
                'error': 'Invalid credential format'
            }), 400
        
        credential_id = actual_credential.get('id')
        
        # Step 2: Check if credential is revoked
        revocation_status = check_credential_revocation(credential_id)
        if not revocation_status['revoked']:
            SecurityLogger.log_security_event('revoked_credential_shield_attempt', {
                'credential_id': credential_id,
                'ip': request.remote_addr,
                'security_level': security_level
            }, 'WARNING')
            
            return jsonify({
                'success': False,
                'shield_action': 'credential_revoked',
                'error': 'Credential has been revoked',
                'details': revocation_status.get('reason'),
                'data': {
                    'credential_id': credential_id,
                    'revocation_reason': revocation_status.get('reason'),
                    'revocation_time': revocation_status.get('revocation_time'),
                    'source': revocation_status.get('source')
                }
            }), 401
        
        # Step 3: Check if we need fresh verification for high security
        if config['require_fresh_verification'] or force_reverification:
            existing_verification_time = session.get('verification_time')
            if existing_verification_time:
                verification_age = time.time() - existing_verification_time
                if verification_age < 300:  # Less than 5 minutes old
                    # Recent verification exists, but high security requires fresh verification
                    return jsonify({
                        'success': False,
                        'shield_action': 'require_fresh_verification',
                        'error': 'Fresh verification required for security level',
                        'data': {
                            'security_level': security_level,
                            'last_verification_age': verification_age,
                            'credential_id': credential_id
                        }
                    }), 401
        
        # Step 4: Create and verify presentation
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
                "domain": domain or request.headers.get('Host', 'localhost'),
                "securityLevel": security_level
            }
        }
        
        # Step 5: Verify presentation
        verification_result = credential_service.verify_presentation(presentation, challenge)
        
        if not verification_result.get('valid'):
            SecurityLogger.log_security_event('shield_verification_failed', {
                'credential_id': credential_id,
                'reason': verification_result.get('reason', 'Unknown'),
                'ip': request.remote_addr,
                'security_level': security_level
            }, 'WARNING')
            
            return jsonify({
                'success': False,
                'shield_action': 'show_shield',
                'error': 'Credential verification failed',
                'details': verification_result.get('reason')
            }), 401
        
        # Step 6: Set secure session with security level tracking
        user_id = extract_user_id_from_credential(actual_credential)
        current_time = time.time()
        
        # Regenerate session to prevent fixation
        if hasattr(session, 'regenerate'):
            session.regenerate()
            
        session['verified_user'] = True
        session['verified_human'] = True
        session['verification_time'] = current_time
        session['last_did_check'] = current_time
        session['last_revocation_check'] = current_time
        session['credential_id'] = credential_id
        session['user_id'] = user_id
        session['verification_ip'] = request.remote_addr
        session['verification_method'] = 'shield_api'
        session['security_level'] = security_level
        session['verification_config'] = config
        
        # Step 7: Log successful verification
        SecurityLogger.log_security_event('shield_verification_success', {
            'credential_id': credential_id,
            'user_id': user_id,
            'ip': request.remote_addr,
            'verification_time': current_time,
            'security_level': security_level
        })
        
        return jsonify({
            'success': True,
            'shield_action': 'allow_access',
            'message': 'Verification successful',
            'data': {
                'verified': True,
                'user_id': user_id,
                'credential_id': credential_id,
                'verification_time': current_time,
                'security_level': security_level,
                'session_timeout': config['session_timeout'],
                'next_checks': {
                    'did_verification_in': config['did_verification_interval'],
                    'revocation_check_in': config['revocation_check_interval']
                }
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"shield credential verification error: {e}")
        SecurityLogger.log_security_event('shield_verification_error', {
            'error': str(e),
            'ip': request.remote_addr
        }, 'ERROR')
        
        return jsonify({
            'success': False,
            'shield_action': 'show_shield',
            'error': 'Verification system error'
        }), 500

@shield_api.route('/api/shield/revoke-credential', methods=['POST'])
@rate_limit
def revoke_credential():
    """
    Revoke a credential - supports both API key auth and test mode
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Check if this is test mode (allows bypassing some security checks)
        is_test_mode = data.get('revoked_by') == 'user_self_test'
        
        # CSRF protection (but skip for test mode)
        if not is_test_mode:
            from lemma.auth.csrf_config import csrf
            try:
                csrf.protect()
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': 'CSRF validation failed'
                }), 400
        
        # Check authentication - require API key for production use, allow test mode
        api_key = request.headers.get('X-API-Key')
        
        if not is_test_mode and not api_key:
            return jsonify({
                'success': False,
                'error': 'API key required for credential revocation'
            }), 401
        
        # Validate API key if provided (but skip for test mode)
        if api_key and not is_test_mode:
            from lemma.auth.security import validate_api_key
            try:
                if not validate_api_key(api_key):
                    return jsonify({
                        'success': False,
                        'error': 'Invalid API key'
                    }), 401
            except Exception:
                return jsonify({
                    'success': False,
                    'error': 'API key validation failed'
                }), 401
        
        # Validate input
        try:
            credential_id = InputValidator.validate_string(data.get('credential_id'), 'credential_id', min_length=10)
            reason = InputValidator.validate_string(data.get('reason', 'Administrative revocation'), 'reason', min_length=1, max_length=500)
            revoked_by = InputValidator.validate_string(data.get('revoked_by', 'system'), 'revoked_by', min_length=1, max_length=100)
        except ValidationError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid input: {str(e)}'
            }), 400
        
        # Perform revocation
        revocation_result = revoke_credential_internal(credential_id, reason, revoked_by)
        
        if revocation_result['success']:
            # Log revocation event
            SecurityLogger.log_security_event('credential_revoked', {
                'credential_id': credential_id,
                'reason': reason,
                'revoked_by': revoked_by,
                'revocation_time': revocation_result['revocation_time'],
                'ip': request.remote_addr
            })
            
            # Invalidate any active sessions for this credential
            invalidate_sessions_for_credential(credential_id)
            
            return jsonify({
                'success': True,
                'message': 'Credential revoked successfully',
                'data': {
                    'credential_id': credential_id,
                    'revocation_time': revocation_result['revocation_time'],
                    'reason': reason,
                    'revoked_by': revoked_by
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': revocation_result['error']
            }), 400
        
    except Exception as e:
        current_app.logger.error(f"Credential revocation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Revocation system error'
        }), 500

@shield_api.route('/api/shield/force-reverification', methods=['POST'])
@csrf_protect()
@require_api_key
@rate_limit
def force_reverification():
    """
    Force re-verification for a user or credential - requires API key
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Validate input
        try:
            credential_id = InputValidator.validate_string(data.get('credential_id', ''), 'credential_id', min_length=0, max_length=200) if data.get('credential_id') else ''
            user_id = InputValidator.validate_string(data.get('user_id', ''), 'user_id', min_length=0, max_length=100) if data.get('user_id') else ''
            reason = InputValidator.validate_string(data.get('reason', 'Administrative re-verification'), 'reason', min_length=1, max_length=500)
        except ValidationError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid input: {str(e)}'
            }), 400
        
        if not credential_id and not user_id:
            return jsonify({
                'success': False,
                'error': 'Either credential_id or user_id must be provided'
            }), 400
        
        # Mark for re-verification
        reverification_result = mark_for_reverification(credential_id, user_id, reason)
        
        if reverification_result['success']:
            # Log re-verification requirement
            SecurityLogger.log_security_event('reverification_required', {
                'credential_id': credential_id,
                'user_id': user_id,
                'reason': reason,
                'marked_time': reverification_result['marked_time'],
                'ip': request.remote_addr
            })
            
            return jsonify({
                'success': True,
                'message': 'Re-verification required successfully',
                'data': {
                    'credential_id': credential_id,
                    'user_id': user_id,
                    'marked_time': reverification_result['marked_time'],
                    'reason': reason
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': reverification_result['error']
            }), 400
        
    except Exception as e:
        current_app.logger.error(f"Force re-verification error: {e}")
        return jsonify({
            'success': False,
            'error': 'Re-verification system error'
        }), 500

@shield_api.route('/api/shield/security-levels', methods=['GET'])
@rate_limit
def get_security_levels():
    """
    Get available security levels and their configurations
    """
    try:
        return jsonify({
            'success': True,
            'security_levels': SECURITY_LEVELS,
            'default_level': 'standard',
            'descriptions': {
                'basic': 'Low security - suitable for general content',
                'standard': 'Balanced security - recommended for most sites',
                'high': 'High security - for sensitive content',
                'maximum': 'Maximum security - for critical applications'
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Security levels error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get security levels'
        }), 500

@shield_api.route('/api/shield/challenge', methods=['GET'])
@rate_limit
def generate_shield_challenge():
    """
    Generate a cryptographically secure challenge for credential verification
    """
    try:
        # Generate secure random challenge
        challenge = secrets.token_hex(32)  # 64 character hex string
        
        # Store challenge in session for validation
        session['shield_challenge'] = challenge
        session['shield_challenge_time'] = time.time()
        
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

@shield_api.route('/api/shield/start-verification', methods=['POST'])
@csrf_protect()
@rate_limit
def start_verification():
    """
    Start the inline verification process for users without credentials
    Returns Stripe Identity session for inline verification
    """
    try:
        data = request.get_json() or {}
        return_url = data.get('return_url', request.referrer or '/')
        security_level = data.get('security_level', 'standard')
        inline_mode = data.get('inline_mode', True)  # Default to inline verification
        
        # Validate return URL for security
        if not is_safe_url(return_url):
            return_url = '/'
        
        # Validate security level
        if security_level not in SECURITY_LEVELS:
            security_level = 'standard'
        
        # Generate user ID and verification session
        user_id = f"user_{int(time.time() * 1000)}"
        verification_session_id = secrets.token_urlsafe(32)
        session['verification_session_id'] = verification_session_id
        session['verification_return_url'] = return_url
        session['verification_started'] = time.time()
        session['requested_security_level'] = security_level
        session['inline_verification'] = inline_mode
        
        if inline_mode:
            # For inline verification, start Stripe Identity session
            try:
                # Import and configure Stripe properly
                import stripe
                
                # Get Stripe secret key from environment or config
                stripe_secret_key = (
                    current_app.config.get('STRIPE_SECRET_KEY') or 
                    os.environ.get('STRIPE_SECRET_KEY')
                )
                
                if not stripe_secret_key:
                    current_app.logger.error("No Stripe secret key found in config or environment")
                    raise Exception("Stripe not configured")
                
                # Set the API key
                stripe.api_key = stripe_secret_key
                current_app.logger.info(f"Stripe API key configured: {stripe_secret_key[:7]}...")
                
                # Create Stripe Identity verification session
                stripe_session = stripe.identity.VerificationSession.create(
                    type='document',
                    metadata={
                        'user_id': user_id,
                        'lemma_session': verification_session_id,
                        'return_url': return_url,
                        'security_level': security_level
                    }
                )
                
                # Store Stripe session info
                session[f'stripe_session_{user_id}'] = stripe_session.id
                session['current_verification_user_id'] = user_id
                
                return jsonify({
                    'success': True,
                    'shield_action': 'inline_verification',
                    'verification_type': 'stripe_identity',
                    'stripe_client_secret': stripe_session.client_secret,
                    'user_id': user_id,
                    'session_id': verification_session_id,
                    'security_level': security_level,
                    'message': 'Inline verification session created'
                })
                
            except Exception as stripe_error:
                current_app.logger.error(f"Stripe Identity session creation failed: {stripe_error}")
                # Fallback to redirect mode if Stripe fails
                inline_mode = False
        
        if not inline_mode:
            # Fallback to redirect mode for compatibility
            onboarding_url = f"/onboarding/start?return_url={return_url}&security_level={security_level}&session_id={verification_session_id}"
            
            return jsonify({
                'success': True,
                'shield_action': 'redirect_verification',
                'verification_url': onboarding_url,
                'session_id': verification_session_id,
                'security_level': security_level,
                'message': 'Verification redirect created'
            })
        
    except Exception as e:
        current_app.logger.error(f"Start verification error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to start verification'
        }), 500

@shield_api.route('/api/shield/get-credential', methods=['GET'])
@rate_limit
def get_stored_credential():
    """
    Get the credential that was stored in session after successful verification
    Used by Shield Widget to retrieve credential for wallet storage
    """
    try:
        # Check if there's a credential stored in session
        stored_credential = session.get('store_credential')
        if stored_credential:
            # Clear the credential from session after retrieving
            session.pop('store_credential', None)
            
            return jsonify({
                'success': True,
                'credential': stored_credential,
                'message': 'Credential retrieved successfully'
            })
        else:
            # No credential in session, check if user has an existing one
            user_id = session.get('verified_user_id') or session.get('user_id')
            if user_id:
                credential_service = get_credential_service()
                existing_credential = credential_service.get_user_credential(user_id)
                
                if existing_credential:
                    # Format existing credential for wallet storage
                    wallet_credential = {
                        "credential": existing_credential,
                        "wallet_metadata": {
                            "added_at": existing_credential.get('issuanceDate', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                            "holder_id": user_id,
                            "status": "active",
                            "display_name": "Lemma Human Verification",
                            "fingerprint": existing_credential.get('id', f"credential-{user_id}")
                        }
                    }
                    
                    return jsonify({
                        'success': True,
                        'credential': wallet_credential,
                        'message': 'Existing credential retrieved successfully'
                    })
            
            return jsonify({
                'success': False,
                'error': 'No credential available',
                'message': 'No credential found in session or for user'
            }), 404
            
    except Exception as e:
        current_app.logger.error(f"Get stored credential error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve credential'
        }), 500

# Helper functions

def check_credential_revocation(credential_id):
    """
    Fast revocation check using in-memory cache first, then file fallback
    OPTIMIZED FOR SPEED - checks memory first for immediate response
    """
    try:
        # SPEED OPTIMIZATION 1: Check in-memory cache first (fastest)
        if hasattr(current_app, '_revoked_credentials_cache'):
            if credential_id in current_app._revoked_credentials_cache:
                revocation_data = current_app._revoked_credentials_cache[credential_id]
                return {
                    'revoked': True,
                    'reason': revocation_data['reason'],
                    'revocation_time': revocation_data['revocation_time'],
                    'source': 'memory_cache'
                }
        
        # SPEED OPTIMIZATION 2: Check Flask session (also very fast)
        if 'revoked_credentials' in session:
            if credential_id in session['revoked_credentials']:
                revocation_data = session['revoked_credentials'][credential_id]
                return {
                    'revoked': True,
                    'reason': revocation_data['reason'],
                    'revocation_time': revocation_data['revocation_time'],
                    'source': 'session_cache'
                }
        
        # FALLBACK: Check file system (slower, but comprehensive)
        revocation_dir = os.path.join(current_app.instance_path, 'data', 'revocation')
        revocation_file = os.path.join(revocation_dir, 'revoked_credentials.json')
        
        if os.path.exists(revocation_file):
            try:
                with open(revocation_file, 'r') as f:
                    revoked_credentials = json.load(f)
                
                if credential_id in revoked_credentials:
                    revocation_data = revoked_credentials[credential_id]
                    
                    # Cache in memory for future fast access
                    if not hasattr(current_app, '_revoked_credentials_cache'):
                        current_app._revoked_credentials_cache = {}
                    current_app._revoked_credentials_cache[credential_id] = revocation_data
                    
                    return {
                        'revoked': True,
                        'reason': revocation_data['reason'],
                        'revocation_time': revocation_data['revocation_time'],
                        'source': 'file_system'
                    }
            except Exception as e:
                current_app.logger.warning(f"File revocation check failed: {e}")
        
        # Not revoked
        return {
            'revoked': False,
            'credential_id': credential_id,
            'source': 'comprehensive_check'
        }
        
    except Exception as e:
        current_app.logger.error(f"Revocation check error: {e}")
        # Default to not revoked if check fails
        return {
            'revoked': False,
            'error': str(e),
            'source': 'error_fallback'
        }

def revoke_credential_internal(credential_id, reason, revoked_by):
    """
    Internal function to revoke a credential - OPTIMIZED FOR SPEED
    """
    try:
        # SPEED OPTIMIZATION: Use in-memory revocation for immediate response
        # Store in session for immediate effect, persist to file asynchronously
        
        revocation_time = time.time()
        revocation_entry = {
            'reason': reason,
            'revoked_by': revoked_by,
            'revocation_time': revocation_time,
            'revocation_timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(revocation_time))
        }
        
        # IMMEDIATE: Store in Flask session for instant access
        if 'revoked_credentials' not in session:
            session['revoked_credentials'] = {}
        session['revoked_credentials'][credential_id] = revocation_entry
        session.permanent = True
        
        # IMMEDIATE: Store in current app context for instant Shield detection
        if not hasattr(current_app, '_revoked_credentials_cache'):
            current_app._revoked_credentials_cache = {}
        current_app._revoked_credentials_cache[credential_id] = revocation_entry
        
        # ASYNC: Persist to file in background (don't wait for this)
        try:
            revocation_dir = os.path.join(current_app.instance_path, 'data', 'revocation')
            os.makedirs(revocation_dir, exist_ok=True)
            revocation_file = os.path.join(revocation_dir, 'revoked_credentials.json')
            
            # Load existing (quick operation)
            revoked_credentials = {}
            if os.path.exists(revocation_file):
                try:
                    with open(revocation_file, 'r') as f:
                        revoked_credentials = json.load(f)
                except Exception:
                    pass  # Don't let file errors slow down immediate response
            
            # Add new revocation
            revoked_credentials[credential_id] = revocation_entry
            
            # Save (but don't wait for completion - fire and forget)
            with open(revocation_file, 'w') as f:
                json.dump(revoked_credentials, f, indent=2)
        except Exception as file_error:
            # File operations failed, but we still have in-memory revocation
            current_app.logger.warning(f"File persistence failed (non-critical): {file_error}")
        
        return {
            'success': True,
            'revocation_time': revocation_time,
            'immediate_effect': True  # Indicate immediate revocation is active
        }
        
    except Exception as e:
        current_app.logger.error(f"Internal revocation error: {e}")
        return {
            'success': False,
            'error': f'Revocation failed: {str(e)}'
        }

def invalidate_sessions_for_credential(credential_id):
    """
    Invalidate all active sessions for a revoked credential
    Note: This is a simplified implementation. In production, you'd want
    a more sophisticated session management system.
    """
    try:
        # For now, we'll just log the invalidation
        # In a full implementation, you'd iterate through active sessions
        # and invalidate any that match the credential_id
        
        SecurityLogger.log_security_event('sessions_invalidated', {
            'credential_id': credential_id,
            'invalidation_time': time.time()
        })
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Session invalidation error: {e}")
        return False

def mark_for_reverification(credential_id, user_id, reason):
    """
    Mark a credential or user for re-verification
    """
    try:
        # Get reverification data directory
        reverification_dir = os.path.join(current_app.instance_path, 'data', 'reverification')
        os.makedirs(reverification_dir, exist_ok=True)
        
        reverification_file = os.path.join(reverification_dir, 'reverification_required.json')
        
        # Load existing reverification requirements
        reverification_data = {}
        if os.path.exists(reverification_file):
            try:
                with open(reverification_file, 'r') as f:
                    reverification_data = json.load(f)
            except Exception as e:
                current_app.logger.error(f"Error loading reverification file: {e}")
        
        # Add reverification requirement
        marked_time = time.time()
        key = credential_id or user_id
        reverification_data[key] = {
            'credential_id': credential_id,
            'user_id': user_id,
            'reason': reason,
            'marked_time': marked_time,
            'marked_timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(marked_time))
        }
        
        # Save updated reverification file
        with open(reverification_file, 'w') as f:
            json.dump(reverification_data, f, indent=2)
        
        return {
            'success': True,
            'marked_time': marked_time
        }
        
    except Exception as e:
        current_app.logger.error(f"Mark for reverification error: {e}")
        return {
            'success': False,
            'error': f'Reverification marking failed: {str(e)}'
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

def check_stripe_verification_completion(user_id, session_id):
    """
    Check if Stripe Identity verification was completed for a given user
    """
    try:
        # Check if verification was completed in session
        if session.get('current_verification_user_id') == user_id:
            stripe_session_id = session.get(f'stripe_session_{user_id}')
            if stripe_session_id:
                try:
                    # Try to import stripe
                    try:
                        import stripe as stripe_module
                        stripe_module.api_key = current_app.config.get('STRIPE_SECRET_KEY')
                    except ImportError:
                        stripe_module = None
                    
                    if stripe_module and stripe_module.api_key:
                        # Check Stripe session status
                        stripe_session = stripe_module.identity.VerificationSession.retrieve(stripe_session_id)
                        
                        if stripe_session.status == 'verified':
                            # CRITICAL FIX: Issue credential when verification is confirmed
                            credential_service = get_credential_service()
                            try:
                                # Check if credential already exists to avoid duplicates
                                existing_credential = credential_service.get_user_credential(user_id)
                                if not existing_credential:
                                    # Issue new credential
                                    new_credential = credential_service.issue_credential(user_id)
                                    current_app.logger.info(f"Issued credential for Stripe-verified user {user_id}: {new_credential.get('id')}")
                                    
                                    # Format credential for wallet storage
                                    wallet_credential = {
                                        "credential": new_credential,
                                        "wallet_metadata": {
                                            "added_at": new_credential.get('issuanceDate', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                                            "holder_id": user_id,
                                            "status": "active",
                                            "display_name": "Lemma Human Verification",
                                            "fingerprint": new_credential.get('id', f"credential-{user_id}")
                                        }
                                    }
                                    
                                    # Store credential in session for wallet to pick up
                                    session['store_credential'] = wallet_credential
                                    session['verified_credential'] = new_credential
                                    session['verified_credential_id'] = new_credential.get('id')
                                else:
                                    current_app.logger.info(f"User {user_id} already has credential, using existing one")
                                    # Format existing credential for wallet storage
                                    wallet_credential = {
                                        "credential": existing_credential,
                                        "wallet_metadata": {
                                            "added_at": existing_credential.get('issuanceDate', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                                            "holder_id": user_id,
                                            "status": "active",
                                            "display_name": "Lemma Human Verification",
                                            "fingerprint": existing_credential.get('id', f"credential-{user_id}")
                                        }
                                    }
                                    session['store_credential'] = wallet_credential
                                    
                            except Exception as credential_error:
                                current_app.logger.error(f"Failed to issue credential for verified user {user_id}: {credential_error}")
                                # Still return success for verification, but note the credential issue
                                return {
                                    'success': True,
                                    'verified': True,
                                    'claims': {
                                        'isHuman': True,
                                        'verification_method': 'stripe_identity',
                                        'verified_at': time.time()
                                    },
                                    'warning': 'Verification successful but credential issuance failed'
                                }
                            
                            return {
                                'success': True,
                                'verified': True,
                                'claims': {
                                    'isHuman': True,
                                    'verification_method': 'stripe_identity',
                                    'verified_at': time.time()
                                }
                            }
                        elif stripe_session.status in ['requires_input', 'processing']:
                            return {
                                'success': False,
                                'error': 'Verification still in progress'
                            }
                        else:
                            return {
                                'success': False,
                                'error': f'Verification failed with status: {stripe_session.status}'
                            }
                    else:
                        # No Stripe configured, check if session marked as complete
                        if session.get('stripe_verification_success') and session.get('verified_user_id') == user_id:
                            # Also issue credential for session-based verification
                            credential_service = get_credential_service()
                            try:
                                existing_credential = credential_service.get_user_credential(user_id)
                                if not existing_credential:
                                    new_credential = credential_service.issue_credential(user_id)
                                    current_app.logger.info(f"Issued credential for session-verified user {user_id}: {new_credential.get('id')}")
                                    
                                    wallet_credential = {
                                        "credential": new_credential,
                                        "wallet_metadata": {
                                            "added_at": new_credential.get('issuanceDate', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                                            "holder_id": user_id,
                                            "status": "active",
                                            "display_name": "Lemma Human Verification",
                                            "fingerprint": new_credential.get('id', f"credential-{user_id}")
                                        }
                                    }
                                    session['store_credential'] = wallet_credential
                            except Exception as credential_error:
                                current_app.logger.error(f"Failed to issue credential for session-verified user {user_id}: {credential_error}")
                                
                            return {
                                'success': True,
                                'verified': True,
                                'claims': {
                                    'isHuman': True,
                                    'verification_method': 'manual_override',
                                    'verified_at': time.time()
                                }
                            }
                        else:
                            return {
                                'success': False,
                                'error': 'Stripe not configured and no manual verification found'
                            }
                        
                except ImportError:
                    current_app.logger.warning("Stripe not available for verification check")
                    # Fallback to session-based check
                    if session.get('stripe_verification_success') and session.get('verified_user_id') == user_id:
                        # Also issue credential for session-based verification
                        credential_service = get_credential_service()
                        try:
                            existing_credential = credential_service.get_user_credential(user_id)
                            if not existing_credential:
                                new_credential = credential_service.issue_credential(user_id)
                                current_app.logger.info(f"Issued credential for fallback-verified user {user_id}: {new_credential.get('id')}")
                                
                                wallet_credential = {
                                    "credential": new_credential,
                                    "wallet_metadata": {
                                        "added_at": new_credential.get('issuanceDate', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                                        "holder_id": user_id,
                                        "status": "active",
                                        "display_name": "Lemma Human Verification",
                                        "fingerprint": new_credential.get('id', f"credential-{user_id}")
                                    }
                                }
                                session['store_credential'] = wallet_credential
                        except Exception as credential_error:
                            current_app.logger.error(f"Failed to issue credential for fallback-verified user {user_id}: {credential_error}")
                            
                        return {
                            'success': True,
                            'verified': True,
                            'claims': {
                                'isHuman': True,
                                'verification_method': 'session_based',
                                'verified_at': time.time()
                            }
                        }
                    else:
                        return {
                            'success': False,
                            'error': 'Stripe not available and no session verification found'
                        }
                except Exception as e:
                    current_app.logger.error(f"Stripe verification check error: {e}")
                    return {
                        'success': False,
                        'error': f'Verification check failed: {str(e)}'
                    }
        
        return {
            'success': False,
            'error': 'No verification session found for user'
        }
        
    except Exception as e:
        current_app.logger.error(f"Verification completion check error: {e}")
        return {
            'success': False,
            'error': f'Failed to check verification status: {str(e)}'
        } 
