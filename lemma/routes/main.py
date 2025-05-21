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
from datetime import datetime
import sys
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
    """Redirect to the API widget demo page for verification."""
    # Check for user_id parameter - try both user_id and user for backward compatibility
    user_id = request.args.get('user_id') or request.args.get('user')
    
    if not user_id:
        # Generate a random user ID if none provided
        user_id = f"user_{secrets.token_hex(8)}"
    
    # Store user ID in session for later use
    session['verification_user_id'] = user_id
    
    # Redirect to the API widget demo page
    return redirect(url_for('main.api_widget_demo', user_id=user_id))

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
    # Extract session ID and user ID from request
    stripe_session_id = request.args.get('session_id')
    user_id = request.args.get('user_id') or session.get('verification_user_id')
    
    # Validate required parameters
    if not stripe_session_id:
        flash("Missing verification session ID", "error")
        return redirect(url_for('main.verify'))
    
    if not user_id:
        flash("Missing user ID for verification", "error")
        return redirect(url_for('main.verify'))
    
    # Log verification callback details
    current_app.logger.info(f"Verification callback received for session {stripe_session_id} and user {user_id}")
    
    try:
        # Retrieve verification status from Stripe
        current_app.logger.info("Checking verification status with Stripe Identity")
        verification_status = check_verification_status(stripe_session_id)
        
        # Process verification result
        if verification_status.get("verified", False):
            current_app.logger.info(f"User {user_id} verified successfully through Stripe Identity")
            
            # Get credential service
            credential_service = get_credential_service()
            
            # Issue a credential to the user
            credential = credential_service.get_user_credential(user_id)
            if not credential:
                credential = credential_service.issue_credential(user_id)
                current_app.logger.info(f"Issued new credential for user {user_id}")
            else:
                current_app.logger.info(f"Using existing credential for user {user_id}")
            
            # Format the credential for wallet storage
            wallet_credential = {
                "credential": credential,
                "wallet_metadata": {
                    "added_at": credential.get('issuanceDate', datetime.now().isoformat()),
                    "holder_id": user_id,
                    "status": "active",
                    "display_name": "Lemma Human Verification",
                    "fingerprint": credential.get('id', f"credential-{user_id}")
                }
            }
            
            # Make sure the session is properly set up for verification success
            session.clear()  # Clear the session to avoid any conflicts
            session.permanent = True  # Make the session permanent
            
            # Set all required session variables
            session['verified_human'] = True
            session['verified_user_id'] = user_id
            session['verified_credential'] = credential
            session['verified_credential_id'] = credential.get('id')
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
            secure = not current_app.config.get('TESTING', False) and not current_app.debug  # Secure in production, not in testing/debug
            response.set_cookie(
                'lemma_wallet_enabled', 
                'true', 
                max_age=31536000,  # 1 year
                secure=secure, 
                httponly=False,  # JavaScript needs access
                samesite='Lax'
            )
            
            # Clear any old session data
            session.pop('stripe_verification_session', None)
            session.pop(f'stripe_session_{user_id}', None)
            
            # Store a debug flag and force redirect to protected page
            session['verification_success'] = True
            session['redirect_to_protected'] = True
            
            # Store additional debug info for troubleshooting
            session['callback_timestamp'] = datetime.now().isoformat()
            session['session_id'] = stripe_session_id
            
            current_app.logger.info(f"Redirecting verified user {user_id} to protected page")
            
            return response
        else:
            # Handle verification failure
            error_message = verification_status.get("error_message", "Unknown error")
            current_app.logger.warning(f"Verification failed for session {stripe_session_id}: {error_message}")
            
            flash(f"Verification failed: {error_message}", "error")
            return redirect(url_for('main.verify', user_id=user_id))
            
    except Exception as e:
        # Handle exceptions
        current_app.logger.error(f"Error processing verification callback: {str(e)}")
        
        flash(f"Error processing verification: {str(e)}", "error")
        return redirect(url_for('main.verify', user_id=user_id))

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
    credential_id = session.get('verified_credential_id')
    is_verified_human = session.get('verified_human', False)
    
    # Log detailed session state for debugging
    current_app.logger.info(f"Protected page access - Session state: user_id={user_id}, credential_id={credential_id}, is_verified_human={is_verified_human}, verification_success={session.get('verification_success')}")
    
    # Check if we were directly redirected from successful verification
    is_verification_redirect = session.get('redirect_to_protected', False)
    if is_verification_redirect:
        current_app.logger.info("Accessed via direct redirect from verification_callback")
        # Remove the flag to prevent infinite redirects
        session.pop('redirect_to_protected', None)
    
    # Strict verification check - require user_id and verification status
    if not user_id or not is_verified_human:
        # Log the unauthorized access attempt
        current_app.logger.warning(f"Unauthorized protected page access attempt. Session data: user_id={user_id}, credential_id={credential_id}, is_verified_human={is_verified_human}")
        
        # Redirect to API widget demo page with a clear message
        flash("Please verify your Lemma to access this page", "warning")
        return redirect(url_for('main.api_widget_demo'))
    
    # Get the wallet credential from session if available (only available right after verification)
    wallet_credential = session.get('store_credential')
    
    # Get just the necessary credential data to pass to template
    credential_data = None
    if wallet_credential and isinstance(wallet_credential, dict) and 'credential' in wallet_credential:
        credential_data = {
            'id': wallet_credential['credential'].get('id'),
            'issuanceDate': wallet_credential['credential'].get('issuanceDate'),
            'expirationDate': wallet_credential['credential'].get('expirationDate'),
        }
    
    # Create response with wallet cookie
    response = make_response(render_template(
        'protected.html',
        user_id=user_id,
        credential_id=credential_id,
        credential=credential_data,
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
        
        # Redirect to API widget demo page with a clear message
        flash("Please verify your Lemma to access this page", "warning")
        return redirect(url_for('main.api_widget_demo'))
    
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
        
        # Redirect to API widget demo page with a clear message
        flash("Please verify your Lemma to access the API documentation", "warning")
        return redirect(url_for('main.api_widget_demo'))
    
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

@main_bp.route('/api/clear-session-credential', methods=['POST'])
@csrf_protect()
def clear_session_credential():
    """Clear credential from session after it's stored in wallet.
    This is a security enhancement to minimize credential storage locations."""
    try:
        # Clear store_credential from session
        if 'store_credential' in session:
            session.pop('store_credential', None)
            current_app.logger.info("Cleared store_credential from session after wallet storage")
        
        return jsonify({"success": True, "message": "Session credential cleared"})
    except Exception as e:
        current_app.logger.error(f"Error clearing session credential: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@main_bp.route('/api/debug-session', methods=['GET'])
def debug_session():
    """Debug endpoint to show current session state.
    
    This endpoint is particularly useful for Windows development environments
    where CSRF validation might be problematic.
    """
    try:
        # Only allow in debug mode
        if not current_app.config.get('DEBUG', False) and not current_app.config.get('TESTING', False):
            return jsonify({"error": "Debug endpoints only available in debug/test mode"}), 403
        
        # Get all session data
        session_data = {key: session.get(key) for key in session}
        
        # Add CSRF token from cookie if available
        csrf_cookie = request.cookies.get('_csrf_token')
        if csrf_cookie:
            session_data['csrf_cookie'] = csrf_cookie[:10] + '...'  # Show only part of the token
        
        # Get cookie settings
        cookie_config = {
            'SESSION_COOKIE_SECURE': current_app.config.get('SESSION_COOKIE_SECURE'),
            'SESSION_COOKIE_HTTPONLY': current_app.config.get('SESSION_COOKIE_HTTPONLY'),
            'SESSION_COOKIE_SAMESITE': current_app.config.get('SESSION_COOKIE_SAMESITE'),
            'SERVER_NAME': current_app.config.get('SERVER_NAME')
        }
        
        # Get environment info
        env_info = {
            'FLASK_ENV': current_app.config.get('ENV'),
            'FLASK_DEBUG': current_app.config.get('DEBUG'),
            'TESTING': current_app.config.get('TESTING'),
            'PLATFORM': sys.platform,
            'IS_HEROKU': "DYNO" in os.environ
        }
        
        return jsonify({
            'session': session_data,
            'cookie_config': cookie_config,
            'env_info': env_info,
            'request_headers': dict(request.headers)
        })
    except Exception as e:
        current_app.logger.error(f"Error in debug-session endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api-widget-demo')
def api_widget_demo():
    """Render the API widget demo page with verification functionality."""
    # Check for user_id parameter
    user_id = request.args.get('user_id')
    
    if not user_id:
        # Generate a random user ID if none provided
        user_id = f"user_{secrets.token_hex(8)}"
        return redirect(url_for('main.api_widget_demo', user_id=user_id))
    
    # Check if the user is already verified in the session
    is_verified = session.get('verified_user_id') == user_id and session.get('verified_human', False)
    
    # If user is already verified, redirect them to the protected page
    if is_verified:
        current_app.logger.info(f"User {user_id} is already verified, redirecting to protected page")
        return redirect(url_for('main.protected'))
    
    # Store user ID in session for later use
    session['verification_user_id'] = user_id
    
    # Log debug info
    current_app.logger.info(f"Rendering API widget demo page for user {user_id}")
    
    return render_template('api_widget_demo.html', user_id=user_id)
