"""
API routes for the Lemma Human Verification System.
Provides endpoints for external integrations and mobile applications with enhanced security.
"""
import secrets
import time
import logging
from functools import wraps
from flask import Blueprint, request, jsonify, current_app, session

# Import credential service from the correct location
try:
    from lemma.core.credential_service import get_credential_service
except ImportError:
    # Fallback to wherever the credential service is actually located
    from lemma.services.credential_service import get_credential_service

# Import security and CSRF modules
try:
    from lemma.auth.security import admin_required
    from lemma.auth.csrf_config import csrf_protect, generate_csrf_token
except ImportError:
    # Fallback to wherever these modules are actually located
    from lemma.security import admin_required
    from lemma.csrf_config import csrf_protect, generate_csrf_token

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Set up logging
logger = logging.getLogger(__name__)

# Rate limiting implementation
request_history = {}

def rate_limit(f):
    """Decorator to apply rate limiting to API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip rate limiting in test environment
        if current_app.config.get('TESTING', False):
            return f(*args, **kwargs)
            
        # Rate limiting logic (per IP)
        ip = request.remote_addr
        now = time.time()
        
        # Clean up old requests
        for req_time in list(request_history.get(ip, [])):
            if now - req_time > 60:
                request_history[ip].remove(req_time)
        
        # Check if rate limit exceeded
        if len(request_history.get(ip, [])) >= 10:
            current_app.logger.warning("Rate limit exceeded for IP: %s", ip)
            return jsonify({
                "error": "Rate limit exceeded",
                "message": "Maximum 10 requests allowed per 60 seconds"
            }), 429
        
        # Add current request
        if ip not in request_history:
            request_history[ip] = []
        request_history[ip].append(now)
        
        return f(*args, **kwargs)
    return decorated_function

def require_api_key(f):
    """Decorator to require API key for endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip API key check in testing environment if configured
        testing_mode = current_app.config.get('TESTING', False)
        skip_auth = current_app.config.get('SKIP_AUTH_IN_TESTS', False)
        skip_api_key = current_app.config.get('SKIP_API_KEY_CHECK', False)
        
        if testing_mode and (skip_auth or skip_api_key):
            logger.info("Skipping API key check in test environment")
            return f(*args, **kwargs)
            
        api_key = request.headers.get('X-API-Key')
        expected_api_key = current_app.config.get('API_KEY')
        
        if not api_key or api_key != expected_api_key:
            logger.warning("Invalid API key attempt from IP: %s", request.remote_addr)
            return jsonify({"error": "Invalid or missing API key"}), 401
            
        return f(*args, **kwargs)
    return decorated

@api_bp.route('/health')
@rate_limit
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "ok", 
        "service": "lemma-human-verification",
        "version": "1.0.0",
        "timestamp": time.time()
    })

@api_bp.route('/issue-credential', methods=['POST'])
@require_api_key
@rate_limit
def issue_credential():
    """Issue a credential via API (requires API key)."""
    try:
        data = request.get_json()
        if not data or 'user_id' not in data:
            return jsonify({"error": "User ID is required"}), 400
        
        user_id = data['user_id']
        
        # Issue the credential
        credential_service = get_credential_service()
        credential = credential_service.issue_credential(user_id)
        
        # Log successful issuance
        logger.info("Credential issued for user: %s", user_id)
        
        return jsonify({
            "success": True,
            "message": "Credential issued successfully",
            "credential": credential
        })
    except ValueError as e:
        logger.error("Invalid data for credential issuance: %s", str(e))
        return jsonify({"error": f"Invalid data: {str(e)}"}), 400
    except KeyError as e:
        logger.error("Missing required field for credential issuance: %s", str(e))
        return jsonify({"error": f"Missing required field: {str(e)}"}), 400
    except Exception as e:
        logger.error("Error issuing credential: %s", str(e))
        return jsonify({"error": f"Error issuing credential: {str(e)}"}), 500

@api_bp.route('/verify-credential', methods=['POST'])
@rate_limit
def verify_credential():
    """Verify a credential via API."""
    try:
        data = request.get_json()
        if not data or 'credential' not in data:
            return jsonify({"error": "Credential is required"}), 400
        
        credential = data['credential']
        
        # Verify the credential
        credential_service = get_credential_service()
        verification_result = credential_service.verify_credential(credential)
        
        if not verification_result.get('valid', False):
            logger.info("Invalid credential verification attempt: %s", verification_result.get('reason'))
            return jsonify({
                "valid": False,
                "reason": verification_result.get('reason', 'Unknown error')
            })
        
        # Log successful verification
        subject_id = verification_result.get('subject', '').split(':')[-1]
        logger.info("Credential verified for subject: %s", subject_id)
        
        return jsonify({
            "valid": True,
            "issuer": verification_result.get('issuer'),
            "subject": verification_result.get('subject'),
            "issuanceDate": verification_result.get('issuanceDate'),
            "expirationDate": verification_result.get('expirationDate')
        })
    except ValueError as e:
        logger.error("Invalid credential format: %s", str(e))
        return jsonify({"error": f"Invalid credential format: {str(e)}"}), 400
    except KeyError as e:
        logger.error("Missing required field in credential: %s", str(e))
        return jsonify({"error": f"Missing required field: {str(e)}"}), 400
    except Exception as e:
        logger.error("Error verifying credential: %s", str(e))
        return jsonify({"error": f"Error verifying credential: {str(e)}"}), 500

@api_bp.route('/generate-challenge')
@rate_limit
def generate_challenge():
    """Generate a challenge for presentation verification."""
    challenge = secrets.token_hex(16)
    return jsonify({"challenge": challenge})

@api_bp.route('/verify-presentation', methods=['POST'])
@rate_limit
def verify_presentation():
    """Verify a presentation via API."""
    # Manual CSRF validation with more flexibility
    if not current_app.config.get('TESTING', False) or not current_app.config.get('SKIP_AUTH_IN_TESTS', False):
        # Try to get CSRF token from various places
        csrf_token = request.headers.get('X-CSRF-Token')
        if not csrf_token and request.is_json:
            csrf_token = request.json.get('csrf_token')
        if not csrf_token and request.form:
            csrf_token = request.form.get('csrf_token')
            
        # For development and debugging, allow requests without CSRF tokens
        if current_app.config.get('ENV') != 'production':
            current_app.logger.warning("CSRF validation skipped in development mode")
        else:
            # In production, validate the token if present
            if csrf_token:
                # Try to validate against various session keys where Flask-WTF might store the token
                valid = False
                
                # Check against different possible session keys
                for key in ['_csrf_token', 'csrf_token', 'csrf']:
                    if key in session and csrf_token == session[key]:
                        valid = True
                        break
                
                # If using Flask-WTF, try its validation method
                try:
                    from flask_wtf.csrf import validate_csrf
                    try:
                        validate_csrf(csrf_token)
                        valid = True
                    except Exception:
                        pass  # Fall back to our manual validation
                except ImportError:
                    pass  # Flask-WTF not available
                
                if not valid:
                    current_app.logger.warning("CSRF validation failed for request from IP: %s", request.remote_addr)
                    # Log token details for debugging
                    current_app.logger.debug("Received token: %s", csrf_token[:10] if csrf_token else None)
                    return jsonify({"valid": False, "error": "CSRF validation failed"}), 400
            elif not csrf_token:
                current_app.logger.warning("No CSRF token found in request from IP: %s", request.remote_addr)
                return jsonify({"valid": False, "error": "CSRF token missing"}), 400
    
    # Log that we're processing a presentation verification request
    current_app.logger.info("Processing presentation verification request from IP: %s", request.remote_addr)
    try:
        data = request.get_json()
        if not data or 'presentation' not in data or 'challenge' not in data:
            return jsonify({"error": "Presentation and challenge are required"}), 400
        
        presentation = data['presentation']
        challenge = data['challenge']
        
        # Verify the presentation
        credential_service = get_credential_service()
        verification_result = credential_service.verify_presentation(presentation, challenge)
        
        if not verification_result.get('valid', False):
            logger.info("Invalid presentation verification attempt: %s", verification_result.get('reason'))
            return jsonify({
                "valid": False,
                "reason": verification_result.get('reason', 'Unknown error')
            })
        
        # Log successful verification
        holder = verification_result.get('holder', '')
        logger.info("Presentation verified for holder: %s", holder)
        
        return jsonify({
            "valid": True,
            "holder": verification_result.get('holder'),
            "credentials": verification_result.get('credentials'),
            "challenge": verification_result.get('challenge')
        })
    except ValueError as e:
        logger.error("Invalid presentation format: %s", str(e))
        return jsonify({"error": f"Invalid presentation format: {str(e)}"}), 400
    except KeyError as e:
        logger.error("Missing required field in presentation: %s", str(e))
        return jsonify({"error": f"Missing required field: {str(e)}"}), 400
    except Exception as e:
        logger.error("Error verifying presentation: %s", str(e))
        return jsonify({"error": f"Error verifying presentation: {str(e)}"}), 500

@api_bp.route('/credentials/<user_id>')
@require_api_key
@rate_limit
def get_user_credential(user_id):
    """Get a user's credential via API."""
    try:
        credential_service = get_credential_service()
        credential = credential_service.get_user_credential(user_id)
        
        if not credential:
            return jsonify({"error": "No credential found for this user"}), 404
        
        return jsonify(credential)
    except FileNotFoundError as e:
        logger.error("Credential file not found for user %s: %s", user_id, str(e))
        return jsonify({"error": "No credential found for this user"}), 404
    except PermissionError as e:
        logger.error("Permission error accessing credential for user %s: %s", user_id, str(e))
        return jsonify({"error": "Access denied to credential"}), 403
    except Exception as e:
        logger.error("Error retrieving credential for user %s: %s", user_id, str(e))
        return jsonify({"error": f"Error retrieving credential: {str(e)}"}), 500

@api_bp.route('/credentials', methods=['GET'])
@require_api_key
@admin_required
@rate_limit
def list_credentials():
    """List all credentials via API (requires API key and admin authentication)."""
    try:
        credential_service = get_credential_service()
        credentials = credential_service.list_credentials()
        
        return jsonify(credentials)
    except PermissionError as e:
        logger.error("Permission error accessing credentials: %s", str(e))
        return jsonify({"error": "Access denied to credentials"}), 403
    except FileNotFoundError as e:
        logger.error("Credential directory not found: %s", str(e))
        return jsonify({"error": "Credential storage not initialized"}), 500
    except Exception as e:
        logger.error("Error listing credentials: %s", str(e))
        return jsonify({"error": f"Error listing credentials: {str(e)}"}), 500

@api_bp.route('/get-csrf-token', methods=['GET'])
def get_csrf_token():
    """Generate a CSRF token for client-side JavaScript."""
    try:
        # Get or generate a CSRF token
        token = generate_csrf_token()
        
        # Return the token in JSON format
        return jsonify({'csrf_token': token})
    except Exception as e:
        logger.error("Error generating CSRF token: %s", str(e))
        return jsonify({'error': 'Error generating CSRF token'}), 500

@api_bp.route('/verify-human', methods=['POST'])
@rate_limit
def verify_human():
    """Verify a human presentation and set session for protected content access."""
    try:
        # Manual CSRF validation with more flexibility
        if not current_app.config.get('TESTING', False) or not current_app.config.get('SKIP_AUTH_IN_TESTS', False):
            # Try to get CSRF token from various places
            csrf_token = request.headers.get('X-CSRF-Token')
            if not csrf_token and request.is_json:
                csrf_token = request.json.get('csrf_token')
            if not csrf_token and request.form:
                csrf_token = request.form.get('csrf_token')
            
            # For development and debugging, allow requests without CSRF tokens
            if current_app.config.get('ENV') != 'production':
                current_app.logger.warning("CSRF validation skipped in development mode")
            else:
                # In production, validate the token if present
                if csrf_token:
                    valid = False
                    
                    # Check against different possible session keys
                    for key in ['_csrf_token', 'csrf_token', 'csrf']:
                        if key in session and csrf_token == session[key]:
                            valid = True
                            break
                    
                    # If using Flask-WTF, try its validation method
                    try:
                        from flask_wtf.csrf import validate_csrf
                        try:
                            validate_csrf(csrf_token)
                            valid = True
                        except Exception:
                            pass  # Fall back to our manual validation
                    except ImportError:
                        pass  # Flask-WTF not available
                    
                    if not valid:
                        current_app.logger.warning("CSRF validation failed for human verification request from IP: %s", request.remote_addr)
                        # Log token details for debugging
                        current_app.logger.debug("Received token: %s", csrf_token[:10] if csrf_token else None)
                        return jsonify({"success": False, "error": "CSRF validation failed"}), 400
                elif not csrf_token:
                    current_app.logger.warning("No CSRF token found in human verification request from IP: %s", request.remote_addr)
                    return jsonify({"success": False, "error": "CSRF token missing"}), 400
        
        current_app.logger.info("Processing human verification request from IP: %s", request.remote_addr)
        
        data = request.get_json()
        if not data or 'presentation' not in data or 'challenge' not in data:
            return jsonify({"success": False, "error": "Presentation and challenge are required"}), 400
        
        presentation = data['presentation']
        challenge = data['challenge']
        
        # Verify the presentation
        credential_service = get_credential_service()
        verification_result = credential_service.verify_presentation(presentation, challenge)
        
        if not verification_result.get('valid', False):
            logger.info("Invalid human verification attempt: %s", verification_result.get('reason'))
            
            return jsonify({
                "success": False,
                "error": verification_result.get('reason', 'Verification failed')
            })
        
        # Extract DID from the holder
        holder = verification_result.get('holder', '')
        user_id = holder.split(':')[-1] if ':' in holder else holder
        
        # Set session variables for protected content access
        session['verified_human'] = True
        session['verified_user_id'] = user_id
        session['verified_presentation'] = presentation
        
        # Get credential info from the presentation
        if 'verifiableCredential' in presentation and presentation['verifiableCredential']:
            credential = presentation['verifiableCredential'][0] if isinstance(presentation['verifiableCredential'], list) else presentation['verifiableCredential']
            session['verified_credential'] = credential
            
            # Set issuance and expiry times if available
            if 'issuanceDate' in credential:
                session['verification_time'] = credential['issuanceDate']
            if 'expirationDate' in credential:
                session['verification_expiry'] = credential['expirationDate']
        
        # Log successful verification
        logger.info("Human verification successful for holder: %s", holder)
        
        return jsonify({
            "success": True,
            "message": "Human verification successful",
            "redirect": "/protected",
            "user_id": user_id
        })
        
    except ValueError as e:
        logger.error("Invalid presentation format in human verification: %s", str(e))
        return jsonify({"success": False, "error": f"Invalid presentation format: {str(e)}"}), 400
    except KeyError as e:
        logger.error("Missing required field in human verification: %s", str(e))
        return jsonify({"success": False, "error": f"Missing required field: {str(e)}"}), 400
    except Exception as e:
        logger.error("Error verifying human: %s", str(e))
        return jsonify({"success": False, "error": f"Error verifying human: {str(e)}"}), 500

@api_bp.route('/credential/<user_id>', methods=['GET'])
def get_credential(user_id):
    """Get a credential for a specific user ID."""
    try:
        credential_service = get_credential_service()
        credential = credential_service.get_user_credential(user_id)
        
        if not credential:
            return jsonify({"error": "No credential found for this user"}), 404
        
        return jsonify(credential)
    except Exception as e:
        logger.error("Error retrieving credential: %s", str(e))
        return jsonify({"error": f"Error retrieving credential: {str(e)}"}), 500

@api_bp.route('/presentation', methods=['POST'])
def create_presentation():
    """Create a presentation from a credential."""
    try:
        data = request.get_json()
        if not data or 'credential' not in data or 'challenge' not in data:
            return jsonify({"error": "Credential and challenge are required"}), 400
        
        credential = data['credential']
        challenge = data['challenge']
        
        # Create the presentation
        credential_service = get_credential_service()
        presentation = credential_service.create_presentation(credential, challenge)
        
        return jsonify(presentation)
    except ValueError as e:
        logger.error("Invalid credential format: %s", str(e))
        return jsonify({"error": f"Invalid credential format: {str(e)}"}), 400
    except Exception as e:
        logger.error("Error creating presentation: %s", str(e))
        return jsonify({"error": f"Error creating presentation: {str(e)}"}), 500
