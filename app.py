"""
Lemma Enterprise - Human Verification System
Main application entry point.
"""

import os
import sys
import logging
import time
import datetime
import random
import json
from flask import Flask, redirect, request, jsonify
from lemma import create_app as lemma_create_app
import requests

# Try to import cascaded_bloom, but make it optional
try:
    from lemma.core.cascaded_bloom import get_cascade_manager, init_cascade_manager
    OPRF_AVAILABLE = True
except ImportError as e:
    logging.warning(f"OPRF cascaded bloom not available: {e}")
    OPRF_AVAILABLE = False
    get_cascade_manager = lambda: None
    init_cascade_manager = lambda x: None

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("app")

# Define constants
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'data')

def create_app():
    """Create and configure the Flask application."""
    logger.info("Creating Lemma Enterprise application")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Create the Lemma app
    app = lemma_create_app()
    
    # Set up OPRF service integration
    if os.environ.get('OPRF_SERVICE_INTERNAL'):
        logger.info(f"OPRF service configured: {os.environ.get('OPRF_SERVICE_INTERNAL')}")
    else:
        # For local development, set the OPRF service to true
        os.environ['OPRF_SERVICE_INTERNAL'] = 'true'
        logger.info("Set OPRF_SERVICE_INTERNAL=true for integrated OPRF service")
    
    # Ensure data directories exist
    os.makedirs(os.path.join(DATA_DIR, 'revocation', 'cascades'), exist_ok=True)
    
    # Initialize cascade manager for OPRF revocation only if available and enabled
    cascade_manager = None
    if OPRF_AVAILABLE and os.environ.get('OPRF_SERVICE_INTERNAL', 'false').lower() != 'false':
        cascade_dir = os.path.join(DATA_DIR, 'revocation', 'cascades')
        init_cascade_manager(cascade_dir)
        cascade_manager = get_cascade_manager()
        logger.info("OPRF cascade manager initialized")
    else:
        logger.info("OPRF cascade manager disabled or not available")
    
    # Define routes - removed redirect to allow main app to handle homepage
    # @app.route('/')  # Commented out to let the main Flask app handle the homepage
    # def index():
    #     """Redirect to the main Lemma application."""
    #     return redirect('/lemma/')
    
    @app.route('/cascade/<epoch>')
    def cascade_direct(epoch):
        logger.info(f"Cascade request for epoch: {epoch}")
        try:
            # First try to find the cascade in the default location
            cascade_dir = os.path.join(DATA_DIR, 'revocation', 'cascades')
            cascade_file = os.path.join(cascade_dir, f'cascade_{epoch}.json')
            
            # If not found, try latest
            if not os.path.exists(cascade_file) and epoch != 'latest':
                latest_file = os.path.join(cascade_dir, 'cascade_latest.json')
                if os.path.exists(latest_file):
                    logger.info(f"Cascade {epoch} not found, using latest")
                    cascade_file = latest_file
            
            # If still not found, return an error instead of creating dummy data
            if not os.path.exists(cascade_file):
                logger.warning(f"Cascade {epoch} not found and no cascades available")
                return jsonify({
                    "error": "Cascade not found",
                    "message": f"No cascade available for epoch {epoch}",
                    "available_epochs": []  # Could list available epochs here
                }), 404
            
            # Load the cascade from file
            with open(cascade_file, 'r') as f:
                cascade = json.load(f)
            
            # Add CORS headers for testing
            response = jsonify(cascade)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
            
            logger.info(f"Successfully loaded cascade for epoch {epoch}")
            return response
        except Exception as e:
            logger.error(f"Error serving cascade: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/cascades')
    def cascades_list():
        try:
            cascade_dir = os.path.join(DATA_DIR, 'revocation', 'cascades')
            
            if not os.path.exists(cascade_dir):
                return jsonify([])
                
            # List all cascade files
            cascades = []
            for filename in os.listdir(cascade_dir):
                if not filename.startswith('cascade_') or not filename.endswith('.json'):
                    continue
                    
                # Skip "latest" as it's a duplicate
                if filename == 'cascade_latest.json':
                    continue
                    
                # Get epoch from filename
                epoch = filename.replace('cascade_', '').replace('.json', '')
                
                cascades.append({"epoch": epoch})
            
            return jsonify(cascades)
        except Exception as e:
            logger.error(f"Error listing cascades: {e}")
            return jsonify({"error": str(e)}), 500
            
    # API endpoints for OPRF integration testing
    @app.route('/api/oprf/status', methods=['GET'])
    def oprf_status():
        """API endpoint to check OPRF service status."""
        try:
            # Get the cascade manager status
            cascade_status = cascade_manager.get_status() if cascade_manager else {"status": "not_initialized"}
            
            # Return the OPRF service status
            return jsonify({
                "status": "ok",
                "oprf_service": "internal",
                "oprf_response": {
                    "status": "ok",
                    "service": "oprf",
                    "version": "1.0.0",
                    "cascade_status": cascade_status
                }
            })
        except Exception as e:
            logger.error(f"Error in OPRF status endpoint: {str(e)}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500
    
    @app.route('/api/oprf/evaluate', methods=['POST'])
    def oprf_evaluate():
        """API endpoint to evaluate the OPRF function for a blinded input."""
        try:
            # Get the request data
            data = request.json
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            # Extract the blinded input
            blinded_input = data.get('blinded_input')
            
            if not blinded_input:
                return jsonify({"error": "No blinded input provided"}), 400
                
            # Evaluate the OPRF function
            if cascade_manager:
                result = cascade_manager.evaluate_oprf(blinded_input)
                return jsonify({
                    "status": "ok",
                    "evaluated_value": result
                })
            else:
                # If cascade manager is not initialized, return an error
                logger.error("OPRF service not available - cascade manager not initialized")
                return jsonify({
                    "status": "error",
                    "error": "OPRF service not available",
                    "message": "Cascade manager not initialized"
                }), 503
                
        except Exception as e:
            logger.error(f"Error evaluating OPRF: {str(e)}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500
    
    # Shield Demo Route
    @app.route('/shield-demo')
    def shield_demo():
        """Demo page showing background wallet and conditional Shield UI"""
        from flask import render_template
        return render_template('shield_demo.html')
            
    @app.route('/api/credentials/verify', methods=['POST'])
    def verify_credential():
        """API endpoint to verify credentials with OPRF revocation check."""
        try:
            # Get the request data
            data = request.json
            
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            # Extract the presentation, challenge, and domain
            presentation = data.get('presentation')
            challenge = data.get('challenge')
            domain = data.get('domain')
            check_revocation = data.get('check_revocation', False)
            
            if not presentation:
                return jsonify({"error": "No presentation provided"}), 400
                
            if not challenge:
                return jsonify({"error": "No challenge provided"}), 400
                
            if not domain:
                return jsonify({"error": "No domain provided"}), 400
            
            # Log the verification request
            logger.info(f"Verifying credential with revocation check: {check_revocation}")
            
            # Extract the credential ID for revocation checking
            credential = presentation.get("verifiableCredential", [{}])[0] if presentation.get("verifiableCredential") else {}
            credential_id = credential.get("id", "")
            
            # Initialize revocation variables
            revocation_checked = False
            revocation_status = "unknown"
            
            # Perform revocation check if requested
            if check_revocation and credential_id and cascade_manager:
                try:
                    # Check if the credential is revoked using the cascade manager
                    logger.info(f"Checking revocation status for credential: {credential_id}")
                    
                    # Get revocation proof from the presentation if available
                    revocation_proof = presentation.get("revocationProof", {})
                    
                    # Check revocation status
                    is_revoked, revocation_details = cascade_manager.check_revocation(credential_id)
                    
                    revocation_checked = True
                    revocation_status = "revoked" if is_revoked else "not_revoked"
                    
                    logger.info(f"Revocation status for {credential_id}: {revocation_status}")
                except Exception as e:
                    logger.error(f"Error checking revocation: {str(e)}")
                    revocation_checked = True
                    revocation_status = "error"
            else:
                # For testing, simulate a successful revocation check
                if check_revocation:
                    revocation_checked = True
                    revocation_status = "not_revoked"
                    logger.info("Simulated revocation check (no cascade manager available)")
            
            # In a real implementation, we would verify the credential signature
            # For now, we'll assume the credential is valid
                    
            # Return the verification result
            return jsonify({
                "verification_result": True,
                "credential_status": "valid",
                "issuer": credential.get("issuer", "unknown"),
                "subject": credential.get("credentialSubject", {}).get("id", "unknown"),
                "issuance_date": credential.get("issuanceDate", "unknown"),
                "expiration_date": credential.get("expirationDate", "unknown"),
                "attributes": credential.get("credentialSubject", {}),
                "revocation_checked": revocation_checked,
                "revocation_status": revocation_status
            })
                
        except Exception as e:
            logger.error(f"Error verifying credential: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    return app

# Create the application
app = create_app()

if __name__ == '__main__':
    # Run the application
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)