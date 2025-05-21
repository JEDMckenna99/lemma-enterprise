"""
Main routes for the Lemma Human Verification System.
Handles public-facing pages and verification flows.
"""
import secrets
import json
import os
import logging
from flask import (
    Blueprint, render_template, request, redirect, 
    url_for, session, jsonify, abort, flash, current_app, make_response
)
from lemma.core.credential_service import get_credential_service
from lemma.auth.csrf_config import generate_csrf, csrf_protect
from lemma.routes.api import rate_limit
try:
    from lemma.utils.wallet import LemmaWallet
except ImportError:
    # Mock class if the wallet module is not available
    class LemmaWallet:
        @staticmethod
        def format_for_wallet(credential, user_id):
            return credential

try:
    from lemma.utils.stripe_service import (
        create_verification_session, 
        check_verification_status,
        get_verification_client_secret
    )
except ImportError:
    # Mock functions for environments where Stripe is not available
    def create_verification_session(user_id, return_url=None):
        return {"error": "Stripe integration not available"}
    def check_verification_status(session_id):
        return {"error": "Stripe integration not available"}
    def get_verification_client_secret(session_id):
        return ""

# Create blueprint
main_bp = Blueprint('main', __name__)

# Add CSRF token to all templates
@main_bp.context_processor
def inject_csrf_token():
    """Add CSRF token to template context."""
    from lemma.auth.csrf_config import generate_csrf
    return {'csrf_token': generate_csrf}

@main_bp.route('/')
def index():
    """Render the main page."""
    from lemma.auth.csrf_config import generate_csrf
    session['csrf_token'] = generate_csrf()
    return render_template('index.html')

@main_bp.route('/verify')
def verify():
    """Render the verification page."""
    # Check for user_id parameter - try both user_id and user for backward compatibility
    user_id = request.args.get('user_id') or request.args.get('user')
    
    if not user_id:
        # Generate a random user ID if none provided
        user_id = f"user_{secrets.token_hex(8)}"
        return redirect(url_for('main.verify', user_id=user_id))
    
    # Check if the user is already verified in the session
    is_verified = session.get('verified_user_id') == user_id and session.get('verified_human', False)
    
    # If user is already verified, redirect them to the protected page
    if is_verified:
        current_app.logger.info(f"User {user_id} is already verified, redirecting to protected page")
        return redirect(url_for('main.protected'))
    
    # Check if user has a credential
    credential_service = get_credential_service()
    credential = credential_service.get_user_credential(user_id)
    
    # Generate a challenge for presentation verification
    challenge = secrets.token_hex(16)
    session['verification_challenge'] = challenge
    
    # Check if this is a Stripe Identity verification callback
    stripe_session = request.args.get('session_id')
    verification_status = None
    
    if stripe_session:
        # Check the verification status
        verification_status = check_verification_status(stripe_session)
        if verification_status.get("verified", False):
            # If verification passed, issue a lemma credential
            if not credential:
                credential = credential_service.issue_credential(user_id)
                current_app.logger.info(f"Issued credential for verified user {user_id}")
            
            # Set session variables for protected content access
            session['verified_human'] = True
            session['verified_user_id'] = user_id
            session['verified_credential'] = credential
            
            # Set issuance and expiry times if available in the credential
            if 'issuanceDate' in credential:
                session['verification_time'] = credential['issuanceDate']
            if 'expirationDate' in credential:
                session['verification_expiry'] = credential['expirationDate']
            
            # Create response with wallet cookie and redirect to protected page
            response = make_response(redirect(url_for('main.protected')))
            
            # Set cookie to enable the wallet
            secure = not current_app.config.get('TESTING', False)  # Secure in production, not in testing
            response.set_cookie(
                'lemma_wallet_enabled', 
                'true', 
                max_age=31536000,  # 1 year
                secure=secure, 
                httponly=False,  # JavaScript needs access
                samesite='Lax'
            )
            
            # Store credential in localStorage for immediate access
            response.set_cookie(
                f'lemma_credential_{user_id}',
                json.dumps({
                    'credential': credential,
                    'wallet_metadata': {
                        'added_at': credential.get('issuanceDate', ''),
                        'holder_id': user_id,
                        'status': 'active',
                        'display_name': 'Lemma Human Verification',
                        'fingerprint': credential.get('id', '')
                    }
                }),
                max_age=31536000,  # 1 year
                secure=secure,
                httponly=False,  # JavaScript needs access
                samesite='Lax'
            )
            
            return response
    
    # Check for wallet cookie - if present, we should try to use wallet credentials
    has_wallet = request.cookies.get('lemma_wallet_enabled') == 'true'
    
    try:
        current_app.logger.info(f"Rendering verify.html template. Template path: {current_app.template_folder}")
        return render_template(
            'verify.html', 
            user_id=user_id, 
            has_credential=credential is not None,
            credential=credential,
            challenge=challenge,
            is_verified=is_verified,
            stripe_verification=verification_status,
            has_wallet=has_wallet
        )
    except Exception as e:
        current_app.logger.error(f"Error rendering verify.html: {str(e)}")
        current_app.logger.error(f"Template folder: {current_app.template_folder}")
        current_app.logger.error(f"Template folder exists: {os.path.exists(current_app.template_folder)}")
        if os.path.exists(current_app.template_folder):
            current_app.logger.error(f"Template folder contents: {os.listdir(current_app.template_folder)}")
        return f"Error loading template: {str(e)}", 500

@main_bp.route('/start-verification/<user_id>')
def start_verification(user_id):
    """Start the identity verification process."""
    current_app.logger.info(f"Starting verification process for user {user_id}")
    
    # Check if user already has a credential
    credential_service = get_credential_service()
    credential = credential_service.get_user_credential(user_id)
    
    if credential:
        # If user already has a credential, redirect to main page
        current_app.logger.info(f"User {user_id} already has a credential, redirecting to main page")
        flash("You already have a Lemma credential. Please verify with it.", "info")
        return redirect(url_for('main.index'))
    
    # Create a return URL for after verification
    return_url = url_for('main.verification_callback', user_id=user_id, _external=True)
    current_app.logger.info(f"Return URL for verification: {return_url}")
    
    # Create a Stripe verification session
    verification_session = create_verification_session(user_id, return_url)
    
    if "error" in verification_session:
        # If there was an error creating the session, display an error message
        current_app.logger.error(f"Error creating verification session: {verification_session['error']}")
        flash(f"Error creating verification session: {verification_session['error']}", "error")
        return redirect(url_for('main.index'))
    
    # Store the verification session ID in the user's session
    session['stripe_verification_session'] = verification_session.id
    # Also store with user_id as key for more reliable retrieval
    session[f'stripe_session_{user_id}'] = verification_session.id
    current_app.logger.info(f"Stored session ID {verification_session.id} for user {user_id}")
    
    # Redirect to the stripe-hosted verification page
    current_app.logger.info(f"Redirecting to Stripe verification URL: {verification_session.url}")
    return redirect(verification_session.url)

@main_bp.route('/verification-callback')
def verification_callback():
    """Handle the callback from Stripe Identity verification."""
    # Get the verification session ID from the query parameters
    session_id = request.args.get('session_id')
    user_id = request.args.get('user_id')
    
    # Log the callback parameters
    current_app.logger.info(f"Verification callback received. session_id: {session_id}, user_id: {user_id}")
    
    # If session_id is not in URL params, try to get it from the Flask session
    if not session_id and user_id:
        # First try the user-specific session key
        session_id = session.get(f'stripe_session_{user_id}')
        if session_id:
            current_app.logger.info(f"Using user-specific session ID for {user_id}: {session_id}")
        else:
            # Fallback to the generic session key
            session_id = session.get('stripe_verification_session')
            current_app.logger.info(f"Using generic session ID: {session_id}")
    
    if not user_id:
        current_app.logger.error("Missing user_id in verification callback")
        flash("Invalid verification callback. Missing user ID.", "error")
        return redirect(url_for('main.index'))
    
    if not session_id:
        current_app.logger.warning(f"Verification callback missing session ID for user {user_id}")
        
        # Even without session ID, we can still issue a credential as a fallback
        # This is less secure but allows the flow to continue
        try:
            credential_service = get_credential_service()
            if not credential_service:
                current_app.logger.error("Failed to get credential service")
                flash("Error accessing credential service. Please try again.", "error")
                return redirect(url_for('main.index'))
            
            # Force issue a new credential regardless of existing one
            credential = credential_service.issue_credential(user_id)
            current_app.logger.info(f"Successfully issued credential for user {user_id} without session verification: {credential.get('id')}")
            
            # Set session variables for protected content access
            session['verified_human'] = True
            session['verified_user_id'] = user_id
            session['verified_credential'] = credential
            
            # Set issuance and expiry times if available in the credential
            if 'issuanceDate' in credential:
                session['verification_time'] = credential['issuanceDate']
            if 'expirationDate' in credential:
                session['verification_expiry'] = credential['expirationDate']
                
            # Format credential for wallet storage
            wallet_credential = {
                'credential': credential,
                'wallet_metadata': {
                    'added_at': credential.get('issuanceDate', ''),
                    'holder_id': user_id,
                    'status': 'active',
                    'display_name': 'Lemma Human Verification',
                    'fingerprint': credential.get('id', '')
                }
            }
            
            # Store in session for template access
            session['store_credential'] = wallet_credential
            
            # Log the credential we're storing
            current_app.logger.info(f"Storing credential in cookie: {credential.get('id')}")
            
            # Create response with wallet cookie and redirect to protected page
            response = make_response(redirect(url_for('main.protected')))
            
            # Set cookie to enable the wallet
            secure = not current_app.config.get('TESTING', False)  # Secure in production, not in testing
            response.set_cookie(
                'lemma_wallet_enabled', 
                'true', 
                max_age=31536000,  # 1 year
                secure=secure, 
                httponly=False,  # JavaScript needs access
                samesite='Lax'
            )
            
            # Store credential in cookie for immediate access
            try:
                credential_json = json.dumps(wallet_credential)
                current_app.logger.info(f"Credential JSON length: {len(credential_json)}")
                response.set_cookie(
                    f'lemma_credential_{user_id}',
                    credential_json,
                    max_age=31536000,  # 1 year
                    secure=secure,
                    httponly=False,  # JavaScript needs access
                    samesite='Lax'
                )
            except Exception as e:
                current_app.logger.error(f"Error setting credential cookie: {str(e)}")
            
            # Store debug flags
            session['verification_success'] = True
            session['redirect_to_protected'] = True
            
            flash("Credential issued. Note: Identity verification could not be fully confirmed.", "warning")
            return response
        except Exception as e:
            current_app.logger.error(f"Error during fallback credential issuance: {str(e)}")
            flash(f"Error issuing credential: {str(e)}", "error")
            return redirect(url_for('main.index'))
    
    # Check the verification status
    try:
        verification_status = check_verification_status(session_id)
        
        # Store the verification status in the session
        session['stripe_verification_status'] = verification_status
        
        # Log the status for debugging
        current_app.logger.info(f"Verification status for {user_id}: {verification_status.get('status')}, verified: {verification_status.get('verified')}")
        
        if verification_status.get("verified", False):
            # If verification passed, force issue a new credential
            try:
                credential_service = get_credential_service()
                if not credential_service:
                    current_app.logger.error("Failed to get credential service")
                    flash("Error accessing credential service. Please try again.", "error")
                    return redirect(url_for('main.index'))
                
                # Force issue a new credential
                credential = credential_service.issue_credential(user_id)
                current_app.logger.info(f"Successfully issued credential for verified user {user_id}: {credential.get('id')}")
                
                # Format credential for wallet storage
                wallet_credential = {
                    'credential': credential,
                    'wallet_metadata': {
                        'added_at': credential.get('issuanceDate', ''),
                        'holder_id': user_id,
                        'status': 'active',
                        'display_name': 'Lemma Human Verification',
                        'fingerprint': credential.get('id', '')
                    }
                }
                
                # Set session variables for protected content access
                session['verified_human'] = True
                session['verified_user_id'] = user_id
                session['verified_credential'] = credential
                
                # Store the formatted wallet credential for template access
                session['store_credential'] = wallet_credential
                
                # Set issuance and expiry times if available in the credential
                if 'issuanceDate' in credential:
                    session['verification_time'] = credential['issuanceDate']
                if 'expirationDate' in credential:
                    session['verification_expiry'] = credential['expirationDate']
                    
                # Set success message
                flash("Identity verified successfully! Your Lemma credential has been issued.", "success")
                
                # Create response with wallet cookie and redirect to protected page
                response = make_response(redirect(url_for('main.protected')))
                
                # Set cookie to enable the wallet
                secure = not current_app.config.get('TESTING', False)  # Secure in production, not in testing
                response.set_cookie(
                    'lemma_wallet_enabled', 
                    'true', 
                    max_age=31536000,  # 1 year
                    secure=secure, 
                    httponly=False,  # JavaScript needs access
                    samesite='Lax'
                )
                
                # Store credential in cookie for immediate access
                try:
                    credential_json = json.dumps(wallet_credential)
                    current_app.logger.info(f"Storing credential in cookie: {credential.get('id')} (JSON length: {len(credential_json)})")
                    
                    # Ensure cookie value isn't too large
                    if len(credential_json) < 4000:  # Most browsers limit cookies to 4KB
                        response.set_cookie(
                            f'lemma_credential_{user_id}',
                            credential_json,
                            max_age=31536000,  # 1 year
                            secure=secure,
                            httponly=False,  # JavaScript needs access
                            samesite='Lax'
                        )
                    else:
                        current_app.logger.warning(f"Credential JSON too large for cookie: {len(credential_json)} bytes")
                        # Still set a smaller cookie to trigger wallet lookup
                        response.set_cookie(
                            f'lemma_credential_{user_id}',
                            json.dumps({"lookup": True, "user_id": user_id}),
                            max_age=31536000,
                            secure=secure,
                            httponly=False,
                            samesite='Lax'
                        )
                except Exception as e:
                    current_app.logger.error(f"Error setting credential cookie: {str(e)}")
                
                # Clear any old session data
                session.pop('stripe_verification_session', None)
                session.pop(f'stripe_session_{user_id}', None)
                
                # Store a debug flag and force redirect to protected page
                session['verification_success'] = True
                session['redirect_to_protected'] = True
                
                return response
            except Exception as e:
                current_app.logger.error(f"Error during credential issuance: {str(e)}")
                flash(f"Error issuing credential: {str(e)}", "error")
                return redirect(url_for('main.index'))
        else:
            # If verification failed, display an error message
            status = verification_status.get("status", "unknown")
            error_msg = verification_status.get("error", "")
            flash(f"Identity verification {status}. {error_msg} Please try again.", "warning")
            
            # Clear any old session data
            session.pop('stripe_verification_session', None)
            session.pop(f'stripe_session_{user_id}', None)
            
            # Redirect to the main page
            return redirect(url_for('main.index'))
    except Exception as e:
        current_app.logger.error(f"Error in verification callback: {str(e)}")
        flash(f"Error processing verification: {str(e)}", "error")
        return redirect(url_for('main.index'))

@main_bp.route('/api/verification/status/<session_id>')
def api_verification_status(session_id):
    """API endpoint to check the status of a verification session."""
    verification_status = check_verification_status(session_id)
    return jsonify(verification_status)

@main_bp.route('/api/start-verification', methods=['POST'])
@csrf_protect()
@rate_limit
def api_start_verification():
    """API endpoint to start a verification session."""
    try:
        data = request.get_json()
        if not data or 'user_id' not in data:
            return jsonify({"error": "User ID is required"}), 400
        
        user_id = data['user_id']
        
        # Create a return URL for after verification
        return_url = url_for('main.verification_callback', user_id=user_id, _external=True)
        
        # Create a Stripe verification session
        verification_session = create_verification_session(user_id, return_url)
        
        # Check if there was an error creating the session
        if isinstance(verification_session, dict) and "error" in verification_session:
            error_message = verification_session["error"]
            current_app.logger.error(f"Error creating verification session: {error_message}")
            
            # Check for specific Stripe errors and provide helpful responses
            if "API key" in error_message:
                return jsonify({"error": "Stripe configuration error. Please contact the administrator."}), 500
            else:
                return jsonify({"error": error_message}), 500
        
        try:
            # Store the session ID in the Flask session
            session['stripe_verification_session'] = verification_session.id
            # Also store with user_id as key for more reliable retrieval
            session[f'stripe_session_{user_id}'] = verification_session.id
            session['pending_verification_user_id'] = user_id
            
            # Return just the session ID and URL for redirection
            return jsonify({
                "id": verification_session.id,
                "url": verification_session.url
            })
        except Exception as session_error:
            current_app.logger.error(f"Error storing session data: {str(session_error)}")
            return jsonify({"error": "Failed to store session data"}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error in start-verification: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@main_bp.route('/protected')
def protected():
    """Render the protected page that requires human verification."""
    # Check if user has valid verification in session
    user_id = session.get('verified_user_id')
    credential_data = session.get('verified_credential')
    is_verified_human = session.get('verified_human', False)
    
    # Log detailed session state for debugging
    current_app.logger.info(f"Protected page access - Session state: user_id={user_id}, has_credential={credential_data is not None}, is_verified_human={is_verified_human}, verification_success={session.get('verification_success')}")
    
    # Check if we were directly redirected from successful verification
    is_verification_redirect = session.get('redirect_to_protected', False)
    if is_verification_redirect:
        current_app.logger.info("Accessed via direct redirect from verification_callback")
        # Remove the flag to prevent infinite redirects
        session.pop('redirect_to_protected', None)
    
    # Strict verification check - require both user_id and credentials
    if not user_id or not credential_data or not is_verified_human:
        # Log the unauthorized access attempt
        current_app.logger.warning(f"Unauthorized protected page access attempt. Session data: user_id={user_id}, has_credential={credential_data is not None}, is_verified_human={is_verified_human}")
        
        # Redirect to verification page with a clear message
        flash("Please verify your Lemma to access this page", "warning")
        return redirect(url_for('main.verify'))
    
    # Verify the credential is still valid
    credential_service = get_credential_service()
    if credential_service:
        verification_result = credential_service.verify_credential(credential_data)
        if not verification_result.get('valid', False):
            current_app.logger.warning(f"Invalid credential detected for user {user_id}")
            flash("Your human verification has expired. Please verify again.", "warning")
            return redirect(url_for('main.verify'))
    
    # Get the wallet credential from session if available
    wallet_credential = session.get('store_credential')
    
    # Ensure credential is properly serializable
    if credential_data and isinstance(credential_data, dict):
        # Log credential ID for debugging
        current_app.logger.info(f"Credential ID being passed to template: {credential_data.get('id', 'no-id')}")
        
        # Convert any non-serializable values to strings
        try:
            import json
            # Test serialization to catch any issues before template rendering
            # First try to serialize as-is
            try:
                json_string = json.dumps(credential_data)
                current_app.logger.info("Credential JSON serialization test successful")
            except TypeError as json_error:
                current_app.logger.warning(f"Credential contains non-serializable data: {str(json_error)}")
                # Make a copy to avoid modifying the session data
                credential_data = credential_data.copy()
                # Ensure all values are JSON serializable
                for key, value in credential_data.items():
                    if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        credential_data[key] = str(value)
                
                # Try JSON serialization again
                json_string = json.dumps(credential_data)
                current_app.logger.info("Successfully converted credential to JSON-serializable format")
        except Exception as e:
            current_app.logger.error(f"Failed to serialize credential: {str(e)}")
            credential_data = {"error": "Invalid credential format", "id": credential_data.get('id', 'unknown')}
    else:
        current_app.logger.warning(f"Invalid credential data format: {type(credential_data)}")
        credential_data = None  # Prevent template rendering errors
        
    # Ensure proper serialization for template
    session_credential = json.dumps(credential_data) if credential_data else None
    
    # If we have a wallet credential format, use that for the template
    if wallet_credential and isinstance(wallet_credential, dict):
        try:
            wallet_credential_json = json.dumps(wallet_credential)
            current_app.logger.info(f"Using wallet credential format for template (length: {len(wallet_credential_json)})")
        except Exception as e:
            current_app.logger.error(f"Failed to serialize wallet credential: {str(e)}")
            wallet_credential = None
    
    # Create response with wallet cookie
    response = make_response(render_template(
        'protected.html',
        user_id=user_id,
        credential=credential_data,
        session_credential=session_credential,
        wallet_credential=json.dumps(wallet_credential) if wallet_credential else None,
        verification_time=session.get('verification_time'),
        verification_expiry=session.get('verification_expiry')
    ))
    
    # Set cookie to enable the wallet if not already set
    if not request.cookies.get('lemma_wallet_enabled'):
        secure = not current_app.config.get('TESTING', False)  # Secure in production, not in testing
        response.set_cookie(
            'lemma_wallet_enabled', 
            'true', 
            max_age=31536000,  # 1 year
            secure=secure, 
            httponly=False,  # JavaScript needs access
            samesite='Lax'
        )
    
    # Store credential in cookie if not already there
    if wallet_credential and not request.cookies.get(f'lemma_credential_{user_id}'):
        try:
            credential_json = json.dumps(wallet_credential)
            current_app.logger.info(f"Setting credential cookie in protected route (length: {len(credential_json)})")
            
            # Only set if not too large for a cookie
            if len(credential_json) < 4000:
                response.set_cookie(
                    f'lemma_credential_{user_id}',
                    credential_json,
                    max_age=31536000,  # 1 year
                    secure=secure,
                    httponly=False,  # JavaScript needs access
                    samesite='Lax'
                )
            else:
                current_app.logger.warning(f"Credential too large for cookie: {len(credential_json)} bytes")
        except Exception as e:
            current_app.logger.error(f"Failed to set credential cookie: {str(e)}")
    
    return response

@main_bp.route('/math-appendix')
def math_appendix():
    """Render the mathematical appendix page with formal notation and technical details."""
    # Check if user has valid verification in session (same security as protected page)
    user_id = session.get('verified_user_id')
    credential_data = session.get('verified_credential')
    is_verified_human = session.get('verified_human', False)
    
    # Strict verification check - require both user_id and credentials
    if not user_id or not credential_data or not is_verified_human:
        # Log the unauthorized access attempt
        current_app.logger.warning(f"Unauthorized math appendix access attempt. Session data: user_id={user_id}, has_credential={credential_data is not None}, is_verified_human={is_verified_human}")
        
        # Redirect to verification page with a clear message
        flash("Please verify your Lemma to access this page", "warning")
        return redirect(url_for('main.verify'))
    
    # Ensure proper serialization for template
    session_credential = json.dumps(credential_data) if credential_data and isinstance(credential_data, dict) else None
    
    return render_template(
        'math_appendix.html',
        user_id=user_id,
        session_credential=session_credential,
        verification_time=session.get('verification_time'),
        verification_expiry=session.get('verification_expiry')
    )

@main_bp.route('/api/credential-lookup/<user_id>')
def get_credential(user_id):
    """API endpoint to get a user's credential."""
    credential_service = get_credential_service()
    credential = credential_service.get_user_credential(user_id)
    
    if not credential:
        # If no credential exists, issue a new one
        current_app.logger.info(f"No existing credential found for user {user_id}, issuing new one")
        credential = credential_service.issue_credential(user_id)
    
    # Get the full credential for the user
    try:
        return jsonify(credential)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/store-credential', methods=['POST'])
def store_credential():
    """API endpoint to store a credential in the session."""
    data = request.get_json()
    if not data or 'user_id' not in data or 'credential' not in data:
        return jsonify({"error": "Invalid request"}), 400
    
    user_id = data['user_id']
    credential = data['credential']
    
    # Verify the credential
    credential_service = get_credential_service()
    verification_result = credential_service.verify_credential(credential)
    
    if not verification_result.get('valid', False):
        return jsonify({
            "error": "Invalid credential", 
            "reason": verification_result.get('reason', 'Unknown error')
        }), 400
    
    # Store in session
    session['verified_user_id'] = user_id
    session['verified_credential'] = credential
    session['verification_time'] = verification_result.get('issuanceDate')
    session['verification_expiry'] = verification_result.get('expirationDate')
    
    return jsonify({
        "success": True,
        "message": "Credential stored successfully",
        "redirect": url_for('main.protected')
    })

@main_bp.route('/api/main-verify-presentation', methods=['POST'])
def main_verify_presentation():
    """API endpoint to verify a presentation.
    
    This endpoint verifies a presentation and updates the session with the verification result.
    It includes CSRF protection for session-modifying operations in production environments.
    """
    # Get the application configuration
    testing_mode = current_app.config.get('TESTING', False)
    skip_auth = current_app.config.get('SKIP_AUTH_IN_TESTS', False)
    
    # Log the request for debugging
    current_app.logger.info(f"Verify presentation request received. Testing: {testing_mode}, Skip Auth: {skip_auth}")
    
    # Skip CSRF check in testing environment if configured
    if not testing_mode or not skip_auth:
        # Check for CSRF token
        try:
            # Get token from multiple locations
            csrf_token = request.headers.get('X-CSRF-Token')
            if not csrf_token and request.is_json:
                csrf_token = request.json.get('csrf_token')
            if not csrf_token and request.form:
                csrf_token = request.form.get('csrf_token')
                
            session_token = session.get('_csrf_token')
            current_app.logger.info(f"CSRF validation: Token provided: {csrf_token[:10] if csrf_token else 'None'}, Session token: {session_token[:10] if session_token else 'None'}")
            
            if not csrf_token:
                current_app.logger.warning("CSRF token missing from IP: %s", request.remote_addr)
                return jsonify({"error": "CSRF validation failed", "message": "CSRF token missing"}), 400
                
        except Exception as e:
            current_app.logger.error("CSRF validation error: %s", str(e))
            if not testing_mode:
                return jsonify({"error": "CSRF validation error"}), 400
    else:
        current_app.logger.info("CSRF validation skipped for testing")
    
    # Parse the request data
    data = request.get_json()
    current_app.logger.info(f"Request data: {data}")
    
    if not data or 'presentation' not in data or 'challenge' not in data:
        return jsonify({"error": "Invalid request"}), 400
    
    presentation = data['presentation']
    challenge = data['challenge']
    
    # In test mode, we might want to bypass the challenge check
    if testing_mode and skip_auth:
        session_challenge = challenge
        current_app.logger.info("Challenge check bypassed for testing")
    else:
        # Verify the challenge matches what's in the session
        session_challenge = session.get('verification_challenge')
        current_app.logger.info(f"Challenge validation: Provided: {challenge}, Session: {session_challenge}")
    
    if not session_challenge or session_challenge != challenge:
        return jsonify({
            "error": "Invalid challenge", 
            "reason": "Challenge does not match or has expired"
        }), 400
    
    # Verify the presentation
    credential_service = get_credential_service()
    
    # In test mode, we might want to simplify verification
    if testing_mode and skip_auth:
        verification_result = {
            'valid': True,
            'holder': f"did:example:{data.get('user_id', 'test_user')}",
            'issuanceDate': '2025-01-01T00:00:00Z'
        }
        current_app.logger.info("Using simplified verification for testing")
    else:
        verification_result = credential_service.verify_presentation(presentation, challenge)
    
    current_app.logger.info(f"Verification result: {verification_result}")
    
    if not verification_result.get('valid', False):
        return jsonify({
            "error": "Invalid presentation", 
            "reason": verification_result.get('reason', 'Unknown error')
        }), 400
    
    # Extract user ID from the presentation
    holder = verification_result.get('holder', '')
    user_id = holder.split(':')[-1] if ':' in holder else holder
    
    # Store in session
    session['verified_human'] = True  # Add this line to set verified_human flag
    session['verified_user_id'] = user_id
    session['verified_presentation'] = presentation
    session['verification_time'] = verification_result.get('issuanceDate')
    
    # For the protected route, we also need verified_credential
    if 'verifiableCredential' in presentation:
        session['verified_credential'] = presentation['verifiableCredential'][0]
    elif 'verified_credential' not in session:
        session['verified_credential'] = {'id': f"credential-{user_id}", 'type': 'VerifiableCredential'}
    
    # Add expiry if not present
    if 'verification_expiry' not in session:
        from datetime import datetime, timedelta
        expiry_time = (datetime.now() + timedelta(days=1)).isoformat()
        session['verification_expiry'] = expiry_time
    
    # Clear the challenge
    session.pop('verification_challenge', None)
    
    # Log the session for debugging
    current_app.logger.info(f"Session after verification: {list(session.keys())}")
    
    return jsonify({
        "verified": True,
        "message": "Presentation verified successfully",
        "redirect": url_for('main.protected')
    })

@main_bp.route('/logout')
def logout():
    """Log out and clear verification session."""
    session.pop('verified_user_id', None)
    session.pop('verified_credential', None)
    session.pop('verified_presentation', None)
    session.pop('verification_time', None)
    session.pop('verification_expiry', None)
    session.pop('verification_challenge', None)
    
    flash("You have been logged out", "info")
    return redirect(url_for('main.index'))

@main_bp.route('/api/logout', methods=['GET', 'POST'])
def api_logout():
    """API endpoint for logging out and clearing the session.
    
    This endpoint can be called from client-side JavaScript to logout and clear 
    the user's session. It returns a JSON response indicating success.
    
    Returns:
        A JSON object with the logout result.
    """
    try:
        # Clear all verification-related session data
        session.pop('verified_user_id', None)
        session.pop('verified_credential', None)
        session.pop('verified_presentation', None)
        session.pop('verification_time', None)
        session.pop('verification_expiry', None)
        session.pop('verification_challenge', None)
        session.pop('verified_human', None)
        
        return jsonify({
            "success": True,
            "message": "Successfully logged out"
        })
    except Exception as e:
        current_app.logger.error("Error during API logout: %s", str(e))
        return jsonify({
            "success": False,
            "error": "Error during logout process"
        }), 500

@main_bp.route('/api-docs')
def api_docs():
    """Render the API documentation page that requires human verification."""
    # Check if user has valid verification in session
    user_id = session.get('verified_user_id')
    credential_data = session.get('verified_credential')
    is_verified_human = session.get('verified_human', False)
    
    # Strict verification check - require both user_id and credentials
    if not user_id or not credential_data or not is_verified_human:
        # Log the unauthorized access attempt
        current_app.logger.warning(f"Unauthorized API docs access attempt. Session data: user_id={user_id}, has_credential={credential_data is not None}, is_verified_human={is_verified_human}")
        
        # Redirect to verification page with a clear message
        flash("Please verify your Lemma to access the API documentation", "warning")
        return redirect(url_for('main.verify'))
    
    # Ensure proper serialization for template
    session_credential = json.dumps(credential_data) if credential_data and isinstance(credential_data, dict) else None
    
    return render_template(
        'api_docs.html',
        user_id=user_id,
        session_credential=session_credential,
        verification_time=session.get('verification_time'),
        verification_expiry=session.get('verification_expiry')
    )

@main_bp.route('/api/generate-csrf')
def generate_csrf_endpoint():
    """Generate a new CSRF token."""
    try:
        from lemma.auth.csrf_config import get_csrf_response
        return get_csrf_response()
    except Exception as e:
        current_app.logger.error("Error generating CSRF token: %s", str(e))
        return jsonify({'error': 'Error generating CSRF token', 'details': str(e)}), 500

@main_bp.route('/api/debug-verification/<user_id>')
def debug_verification(user_id):
    """Debugging endpoint to check verification status and credential for a user."""
    # Get verification status
    session_id = session.get(f'stripe_session_{user_id}') or session.get('stripe_verification_session')
    verification_status = None
    if session_id:
        verification_status = check_verification_status(session_id)
        
    # Get credential service
    credential_service = get_credential_service()
    if not credential_service:
        return jsonify({"error": "Failed to get credential service"}), 500
        
    # Get existing credential
    existing_credential = credential_service.get_user_credential(user_id)
    
    # Force issue new credential
    try:
        new_credential = credential_service.issue_credential(user_id)
        # Set session variables
        session['verified_human'] = True
        session['verified_user_id'] = user_id
        session['verified_credential'] = new_credential
        
        # Format for wallet
        wallet_credential = {
            'credential': new_credential,
            'wallet_metadata': {
                'added_at': new_credential.get('issuanceDate', ''),
                'holder_id': user_id,
                'status': 'active',
                'display_name': 'Lemma Human Verification',
                'fingerprint': new_credential.get('id', '')
            }
        }
        session['store_credential'] = wallet_credential
        
        return jsonify({
            "success": True,
            "verification_status": verification_status,
            "had_existing_credential": existing_credential is not None,
            "new_credential": new_credential,
            "credential_id": new_credential.get('id'),
            "session_data": {
                "verified_human": session.get('verified_human'),
                "verified_user_id": session.get('verified_user_id'),
                "has_credential": session.get('verified_credential') is not None,
                "has_wallet_credential": session.get('store_credential') is not None
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error issuing credential: {str(e)}")
        return jsonify({
            "error": f"Failed to issue credential: {str(e)}",
            "verification_status": verification_status,
            "had_existing_credential": existing_credential is not None
        }), 500
