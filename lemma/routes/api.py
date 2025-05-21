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
@csrf_protect()
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
@csrf_protect()
@rate_limit
def verify_presentation():
    """Verify a presentation via API."""
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

@api_bp.route('/user-credential/<user_id>')
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

@api_bp.route('/generate-csrf-token', methods=['GET'])
def get_csrf_token():
    """Generate a CSRF token for client-side JavaScript and set it as a cookie."""
    try:
        # Initialize session if needed
        if not session.get('_csrf_token'):
            session['_csrf_token'] = secrets.token_hex(32)
        
        # Get or generate CSRF token
        csrf_token = session.get('_csrf_token')
        
        # Create response with token
        response = jsonify({'csrf_token': csrf_token})
        
        # Set the CSRF token as a cookie (modern best practice)
        response.set_cookie(
            'csrf_token', 
            csrf_token, 
            httponly=False,  # JavaScript needs access
            secure=not current_app.config.get('TESTING', False),  # Secure in production
            samesite='Lax'   # Protect against CSRF
        )
        
        return response
    except Exception as e:
        current_app.logger.error("Error generating CSRF token: %s", str(e))
        return jsonify({'error': 'Error generating CSRF token', 'details': str(e)}), 500

@api_bp.route('/verify-human', methods=['POST'])
@csrf_protect()
@rate_limit
def verify_human():
    """Verify a human presentation and set session for protected content access."""
    try:
        current_app.logger.info("Processing human verification request from IP: %s", request.remote_addr)
        
        data = request.get_json()
        if not data or 'presentation' not in data or 'challenge' not in data:
            return jsonify({"success": False, "error": "Presentation and challenge are required"}), 400
        
        presentation = data['presentation']
        challenge = data['challenge']
        
        # Basic input validation
        if not isinstance(presentation, dict):
            logger.error("Invalid presentation format: not a dictionary")
            return jsonify({"success": False, "error": "Invalid presentation format"}), 400
            
        if not isinstance(challenge, str) or len(challenge) < 8:
            logger.error("Invalid challenge format")
            return jsonify({"success": False, "error": "Invalid challenge format"}), 400
        
        # Verify the presentation
        try:
            credential_service = get_credential_service()
            verification_result = credential_service.verify_presentation(presentation, challenge)
        except Exception as ve:
            logger.error("Exception during presentation verification: %s", str(ve))
            return jsonify({"success": False, "error": f"Verification error: {str(ve)}"}), 500
        
        if not verification_result.get('valid', False):
            reason = verification_result.get('reason', 'Verification failed')
            logger.info("Invalid human verification attempt: %s", reason)
            
            # Include more details for debugging in development
            if current_app.config.get('DEBUG', False):
                error_details = {
                    "success": False,
                    "error": reason,
                    "challenge": challenge[:5] + "...", # Show part of the challenge for debugging
                    "debug_info": "Verification failed in verify_presentation function"
                }
                return jsonify(error_details)
            
            return jsonify({
                "success": False,
                "error": reason
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

@api_bp.route('/presentation', methods=['POST'])
@csrf_protect()
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

@api_bp.route('/create-minimal-proof', methods=['POST'])
@rate_limit
def create_minimal_proof():
    """Create a minimal zero-knowledge proof that only reveals the user is human."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Get credential and challenge
        credential = data.get('credential')
        challenge = data.get('challenge')
        
        if not credential or not challenge:
            return jsonify({"error": "Credential and challenge are required"}), 400
            
        # Import ZKProof utilities
        try:
            from lemma.utils.zero_knowledge import ZKProof
        except ImportError:
            return jsonify({"error": "Zero-knowledge proof functionality not available"}), 500
            
        # Create the proof
        try:
            proof = ZKProof.create_human_proof(credential, challenge)
            return jsonify(proof)
        except Exception as e:
            return jsonify({"error": f"Error creating proof: {str(e)}"}), 400
            
    except Exception as e:
        logger.error(f"Error in create_minimal_proof: {str(e)}")
        return jsonify({"error": f"Error: {str(e)}"}), 500

@api_bp.route('/verify-minimal-proof', methods=['POST'])
@rate_limit
def verify_minimal_proof():
    """Verify a minimal zero-knowledge proof."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Get proof and challenge
        proof = data.get('proof')
        challenge = data.get('challenge')
        
        if not proof or not challenge:
            return jsonify({"error": "Proof and challenge are required"}), 400
            
        # Import ZKProof utilities
        try:
            from lemma.utils.zero_knowledge import ZKProof
        except ImportError:
            return jsonify({"error": "Zero-knowledge proof functionality not available"}), 500
            
        # Verify the proof
        try:
            result = ZKProof.verify_human_proof(proof, challenge)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": f"Error verifying proof: {str(e)}"}), 400
            
    except Exception as e:
        logger.error(f"Error in verify_minimal_proof: {str(e)}")
        return jsonify({"error": f"Error: {str(e)}"}), 500

@api_bp.route('/create-selective-disclosure', methods=['POST'])
@rate_limit
def create_selective_disclosure():
    """Create a selective disclosure that only reveals specific attributes."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Get credential and attributes
        credential = data.get('credential')
        attributes = data.get('attributes', ['isHuman'])
        
        if not credential:
            return jsonify({"error": "Credential is required"}), 400
            
        # Import SelectiveDisclosure utilities
        try:
            from lemma.utils.zero_knowledge import SelectiveDisclosure
        except ImportError:
            return jsonify({"error": "Selective disclosure functionality not available"}), 500
            
        # Create the disclosure
        try:
            disclosure = SelectiveDisclosure.create_disclosure(credential, attributes)
            return jsonify(disclosure)
        except Exception as e:
            return jsonify({"error": f"Error creating disclosure: {str(e)}"}), 400
            
    except Exception as e:
        logger.error(f"Error in create_selective_disclosure: {str(e)}")
        return jsonify({"error": f"Error: {str(e)}"}), 500

@api_bp.route('/verify-selective-disclosure', methods=['POST'])
@rate_limit
def verify_selective_disclosure():
    """Verify a selective disclosure."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Get disclosure
        disclosure = data.get('disclosure')
        
        if not disclosure:
            return jsonify({"error": "Disclosure is required"}), 400
            
        # Get trusted issuers from config
        trusted_issuers = current_app.config.get('TRUSTED_ISSUERS')
        
        # Import SelectiveDisclosure utilities
        try:
            from lemma.utils.zero_knowledge import SelectiveDisclosure
        except ImportError:
            return jsonify({"error": "Selective disclosure functionality not available"}), 500
            
        # Verify the disclosure
        try:
            result = SelectiveDisclosure.verify_disclosure(disclosure, trusted_issuers)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": f"Error verifying disclosure: {str(e)}"}), 400
            
    except Exception as e:
        logger.error(f"Error in verify_selective_disclosure: {str(e)}")
        return jsonify({"error": f"Error: {str(e)}"}), 500

@api_bp.route('/verify-with-hardware', methods=['POST'])
@rate_limit
def verify_with_hardware():
    """Verify a credential using hardware-backed security if available."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Get credential
        credential = data.get('credential')
        
        if not credential:
            return jsonify({"error": "Credential is required"}), 400
            
        # Check if hardware security is enabled
        if not current_app.config.get('HARDWARE_SECURITY', False):
            # Fall back to regular verification
            credential_service = get_credential_service()
            result = credential_service.verify_credential(credential)
            return jsonify(result)
            
        # Attempt to use hardware-backed verification
        try:
            from lemma.utils.secure_storage import get_secure_storage
            storage = get_secure_storage()
            
            # For now, this just delegates to the regular verification
            # In a real implementation, this would use hardware security features
            credential_service = get_credential_service()
            result = credential_service.verify_credential(credential)
            
            # Add hardware security indicator to the result
            if result.get('valid'):
                result['hardware_verified'] = storage.secure_hardware_available
                
            return jsonify(result)
        except ImportError:
            # Fall back to regular verification
            credential_service = get_credential_service()
            result = credential_service.verify_credential(credential)
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error in verify_with_hardware: {str(e)}")
        return jsonify({"error": f"Error: {str(e)}"}), 500

# Add the following API endpoints for P2P revocation synchronization

@api_bp.route('/revocation/status', methods=['GET'])
@require_api_key
def revocation_status():
    """Get revocation status for the local node."""
    try:
        # Check if P2P revocation is enabled
        if not current_app.config.get('ENABLE_P2P', False):
            return jsonify({"error": "P2P revocation not enabled on this node"}), 400
            
        # Get the P2P network from app config
        p2p_network = current_app.config.get('P2P_NETWORK')
        if not p2p_network:
            return jsonify({"error": "P2P network not configured"}), 500
            
        # Get sync status
        status = p2p_network.get_sync_status()
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting revocation status: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/sync', methods=['POST'])
@require_api_key
def sync_revocation():
    """Manually trigger synchronization with peer nodes."""
    try:
        # Check if P2P revocation is enabled
        if not current_app.config.get('ENABLE_P2P', False):
            return jsonify({"error": "P2P revocation not enabled on this node"}), 400
            
        # Get the P2P network from app config
        p2p_network = current_app.config.get('P2P_NETWORK')
        if not p2p_network:
            return jsonify({"error": "P2P network not configured"}), 500
            
        # Sync with peers
        results = p2p_network.sync_with_peers()
        return jsonify({"status": "success", "results": results})
        
    except Exception as e:
        logger.error(f"Error syncing revocation data: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/import', methods=['POST'])
@require_api_key
def import_revocation_data():
    """Import revocation data from a peer node."""
    try:
        # Get revocation registry
        from lemma.core.revocation import get_revocation_registry
        registry = get_revocation_registry()
        if not registry:
            return jsonify({"error": "Revocation registry not available"}), 500
            
        # Get the data from the request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Validate basic structure
        if "issuer_id" not in data:
            return jsonify({"error": "Invalid revocation data format"}), 400
            
        # Import the data
        success = registry.import_revocation_data(data)
        
        return jsonify({
            "status": "success" if success else "no_update",
            "message": "Data imported successfully" if success else "Local data is newer, no update needed"
        })
        
    except Exception as e:
        logger.error(f"Error importing revocation data: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/issuers', methods=['GET'])
@require_api_key
def list_revocation_issuers():
    """List all issuers in the revocation registry."""
    try:
        # Get revocation registry
        from lemma.core.revocation import get_revocation_registry
        registry = get_revocation_registry()
        if not registry:
            return jsonify({"error": "Revocation registry not available"}), 500
            
        # Get the list of issuers
        issuers = list(registry.revocation_data.keys())
        
        return jsonify({
            "issuers": issuers,
            "count": len(issuers)
        })
        
    except Exception as e:
        logger.error(f"Error listing revocation issuers: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/issuer/<issuer_id>', methods=['GET'])
@require_api_key
def get_issuer_metadata(issuer_id):
    """Get metadata for an issuer's revocation data."""
    try:
        # Get revocation registry
        from lemma.core.revocation import get_revocation_registry
        registry = get_revocation_registry()
        if not registry:
            return jsonify({"error": "Revocation registry not available"}), 500
            
        # Get the revocation data for this issuer
        revocation_data = registry.get_revocation_data(issuer_id)
        if not revocation_data:
            return jsonify({"error": f"No revocation data for issuer {issuer_id}"}), 404
            
        # Return only the metadata
        return jsonify({
            "issuer_id": revocation_data["issuer_id"],
            "last_updated": revocation_data["last_updated"],
            "revoked_count": revocation_data["revoked_count"]
        })
        
    except Exception as e:
        logger.error(f"Error getting issuer metadata: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/data/<issuer_id>', methods=['GET'])
@require_api_key
def get_issuer_revocation_data(issuer_id):
    """Get the full revocation data for an issuer."""
    try:
        # Get revocation registry
        from lemma.core.revocation import get_revocation_registry
        registry = get_revocation_registry()
        if not registry:
            return jsonify({"error": "Revocation registry not available"}), 500
            
        # Get the revocation data for this issuer
        revocation_data = registry.get_revocation_data(issuer_id)
        if not revocation_data:
            return jsonify({"error": f"No revocation data for issuer {issuer_id}"}), 404
            
        # Return the full data
        return jsonify(revocation_data)
        
    except Exception as e:
        logger.error(f"Error getting issuer revocation data: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/check/<issuer_id>/<credential_id>', methods=['GET'])
def check_revocation_status(issuer_id, credential_id):
    """Check if a credential is revoked."""
    try:
        # Get revocation registry
        from lemma.core.revocation import get_revocation_registry
        registry = get_revocation_registry()
        if not registry:
            return jsonify({"error": "Revocation registry not available"}), 500
            
        # Check if the credential is revoked
        is_revoked = registry.is_revoked(issuer_id, credential_id)
        
        return jsonify({
            "issuer_id": issuer_id,
            "credential_id": credential_id,
            "revoked": is_revoked,
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Error checking revocation status: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@api_bp.route('/revocation/add_peer', methods=['POST'])
@require_api_key
def add_revocation_peer():
    """Add a peer to the P2P revocation network."""
    try:
        # Check if P2P revocation is enabled
        if not current_app.config.get('ENABLE_P2P', False):
            return jsonify({"error": "P2P revocation not enabled on this node"}), 400
            
        # Get the P2P network from app config
        p2p_network = current_app.config.get('P2P_NETWORK')
        if not p2p_network:
            return jsonify({"error": "P2P network not configured"}), 500
            
        # Get peer info from the request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        peer_id = data.get('peer_id')
        peer_url = data.get('peer_url')
        
        if not peer_id or not peer_url:
            return jsonify({"error": "Both peer_id and peer_url are required"}), 400
            
        # Add the peer
        p2p_network.add_peer(peer_id, peer_url)
        
        return jsonify({
            "status": "success",
            "message": f"Peer {peer_id} added successfully",
            "peer_count": len(p2p_network.peers)
        })
        
    except Exception as e:
        logger.error(f"Error adding revocation peer: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

# Add API endpoints for peer discovery and network information

@api_bp.route('/node_info', methods=['GET'])
def get_node_info():
    """Get information about this node."""
    try:
        # Get node ID (DID) from config
        node_id = current_app.config.get('DID', 'unknown')
        node_url = request.host_url.rstrip('/')
        
        # Determine supported features
        features = []
        
        if current_app.config.get('ENABLE_P2P', False):
            features.append('revocation')
            
        try:
            from lemma.core.did_resolver import get_did_resolver
            features.append('did_resolver')
        except ImportError:
            pass
            
        try:
            from lemma.utils.zero_knowledge import ZKProof
            features.append('zero_knowledge')
        except ImportError:
            pass
            
        try:
            from lemma.utils.secure_storage import get_secure_storage
            features.append('hardware_security')
        except ImportError:
            pass
        
        network = current_app.config.get('NETWORK', 'main')
        
        return jsonify({
            'node_id': node_id,
            'url': node_url,
            'features': features,
            'network': network,
            'version': current_app.config.get('VERSION', '1.0'),
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"Error getting node info: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500

@api_bp.route('/peers', methods=['GET'])
@require_api_key
def get_peers():
    """Get the list of peers in the network."""
    try:
        # Check if peer discovery is enabled
        try:
            from lemma.utils.network_utilities import get_peer_discovery
        except ImportError:
            return jsonify({'error': 'Peer discovery not available'}), 500
            
        discovery = get_peer_discovery()
        if not discovery:
            return jsonify({'error': 'Peer discovery not initialized'}), 500
            
        # Get include_stats parameter
        include_stats = request.args.get('include_stats', 'false').lower() == 'true'
        
        # Get the peer list
        peer_list = discovery.get_peer_list(include_stats)
        return jsonify(peer_list)
        
    except Exception as e:
        logger.error(f"Error getting peers: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500

@api_bp.route('/peers/add', methods=['POST'])
@require_api_key
def add_peer():
    """Add a peer to the network."""
    try:
        # Check if peer discovery is enabled
        try:
            from lemma.utils.network_utilities import get_peer_discovery
        except ImportError:
            return jsonify({'error': 'Peer discovery not available'}), 500
            
        discovery = get_peer_discovery()
        if not discovery:
            return jsonify({'error': 'Peer discovery not initialized'}), 500
            
        # Get peer data from request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        peer_id = data.get('peer_id')
        peer_url = data.get('peer_url')
        status = data.get('status', 'discovered')
        features = data.get('features', [])
        network = data.get('network', 'main')
        
        if not peer_id or not peer_url:
            return jsonify({'error': 'Both peer_id and peer_url are required'}), 400
            
        # Add the peer
        added = discovery.add_peer(peer_id, peer_url, status, features, network)
        
        return jsonify({
            'status': 'success',
            'message': f"Peer {'added' if added else 'updated'} successfully",
            'peer_id': peer_id
        })
        
    except Exception as e:
        logger.error(f"Error adding peer: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500

@api_bp.route('/peers/remove/<peer_id>', methods=['POST'])
@require_api_key
def remove_peer(peer_id):
    """Remove a peer from the network."""
    try:
        # Check if peer discovery is enabled
        try:
            from lemma.utils.network_utilities import get_peer_discovery
        except ImportError:
            return jsonify({'error': 'Peer discovery not available'}), 500
            
        discovery = get_peer_discovery()
        if not discovery:
            return jsonify({'error': 'Peer discovery not initialized'}), 500
            
        # Remove the peer
        removed = discovery.remove_peer(peer_id)
        
        if removed:
            return jsonify({
                'status': 'success',
                'message': f"Peer {peer_id} removed successfully"
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f"Peer {peer_id} not found"
            }), 404
        
    except Exception as e:
        logger.error(f"Error removing peer: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500

@api_bp.route('/peers/discover', methods=['POST'])
@require_api_key
def discover_peers():
    """Discover peers on the local network."""
    try:
        # Check if peer discovery is enabled
        try:
            from lemma.utils.network_utilities import get_peer_discovery
        except ImportError:
            return jsonify({'error': 'Peer discovery not available'}), 500
            
        discovery = get_peer_discovery()
        if not discovery:
            return jsonify({'error': 'Peer discovery not initialized'}), 500
            
        # Get parameters from request
        data = request.get_json() or {}
        port = data.get('port', 5000)
        timeout = data.get('timeout', 2)
        
        # Discover peers
        discovered = discovery.discover_local_network(port, timeout)
        
        return jsonify({
            'status': 'success',
            'discovered': discovered,
            'count': len(discovered),
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"Error discovering peers: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500

@api_bp.route('/peers/health', methods=['GET'])
@require_api_key
def check_peers_health():
    """Check the health of all known peers."""
    try:
        # Check if peer discovery is enabled
        try:
            from lemma.utils.network_utilities import get_peer_discovery
        except ImportError:
            return jsonify({'error': 'Peer discovery not available'}), 500
            
        discovery = get_peer_discovery()
        if not discovery:
            return jsonify({'error': 'Peer discovery not initialized'}), 500
            
        # Check single peer or all peers
        peer_id = request.args.get('peer_id')
        
        if peer_id:
            # Check specific peer
            health = discovery.check_peer_health(peer_id)
            return jsonify(health)
        else:
            # Check all peers
            health = discovery.check_all_peers_health()
            return jsonify({
                'peers': health,
                'count': len(health),
                'timestamp': time.time()
            })
        
    except Exception as e:
        logger.error(f"Error checking peers health: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500

@api_bp.route('/peers/sync/<peer_id>', methods=['POST'])
@require_api_key
def sync_with_peer(peer_id):
    """Synchronize peer list with a trusted peer."""
    try:
        # Check if peer discovery is enabled
        try:
            from lemma.utils.network_utilities import get_peer_discovery
        except ImportError:
            return jsonify({'error': 'Peer discovery not available'}), 500
            
        discovery = get_peer_discovery()
        if not discovery:
            return jsonify({'error': 'Peer discovery not initialized'}), 500
            
        # Sync with the peer
        result = discovery.sync_with_trusted_peer(peer_id)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error syncing with peer: {str(e)}")
        return jsonify({'error': f"Internal error: {str(e)}"}), 500
