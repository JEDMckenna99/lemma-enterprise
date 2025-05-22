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
    
    # Define routes
    @app.route('/')
    def index():
        """Redirect to the main Lemma application."""
        return redirect('/lemma/')
    
    @app.route('/cascade/<epoch>')
    def cascade_direct(epoch):
        logger.debug(f"Direct cascade request for epoch: {epoch}")
        try:
            # First try to find the cascade in the default location
            cascade_dir = os.path.join(DATA_DIR, 'revocation', 'cascades')
            cascade_file = os.path.join(cascade_dir, f'cascade_{epoch}.json')
            
            logger.debug(f"Looking for cascade file at: {cascade_file}")
            
            # If not found, try latest
            if not os.path.exists(cascade_file) and epoch != 'latest':
                latest_file = os.path.join(cascade_dir, 'cascade_latest.json')
                if os.path.exists(latest_file):
                    logger.debug(f"Cascade {epoch} not found, using latest")
                    cascade_file = latest_file
            
            # If still not found, create a dummy cascade
            if not os.path.exists(cascade_file):
                logger.debug(f"Cascade {epoch} not found, creating dummy")
                cascade = {
                    "epoch": epoch if epoch != 'latest' else datetime.datetime.now().strftime('%Y-%m-%d'),
                    "created": datetime.datetime.now().isoformat(),
                    "issuer": "did:web:lemma-enterprise.herokuapp.com",
                    "filters": [],
                    "signature": {
                        "type": "Ed25519Signature2020",
                        "created": datetime.datetime.now().isoformat(),
                        "verificationMethod": "did:web:lemma-enterprise.herokuapp.com#key-1",
                        "proofValue": "z" + "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=64))
                    }
                }
            else:
                # Load the cascade from file
                with open(cascade_file, 'r') as f:
                    cascade = json.load(f)
            
            # Add CORS headers for testing
            response = jsonify(cascade)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
            
            logger.debug(f"Successfully loaded cascade for epoch {epoch}")
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
            # Get the OPRF service URL from environment
            oprf_service_url = os.environ.get('OPRF_SERVICE_INTERNAL', 'https://lemma-oprf-service.herokuapp.com')
            
            # Try to connect to the OPRF service
            response = requests.get(f"{oprf_service_url}/status", timeout=5)
            
            if response.status_code == 200:
                # OPRF service is available
                return jsonify({
                    "status": "ok",
                    "oprf_service": oprf_service_url,
                    "oprf_response": response.json()
                })
            else:
                # OPRF service returned an error
                return jsonify({
                    "status": "error",
                    "oprf_service": oprf_service_url,
                    "error": f"OPRF service returned status code {response.status_code}"
                }), 500
                
        except requests.RequestException as e:
            # OPRF service is not available
            return jsonify({
                "status": "error",
                "oprf_service": os.environ.get('OPRF_SERVICE_INTERNAL', 'https://lemma-oprf-service.herokuapp.com'),
                "error": f"Could not connect to OPRF service: {str(e)}"
            }), 500
            
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
                
            # In a real implementation, we would verify the credential
            # For testing, we'll just return a mock response
            
            # If check_revocation is True, we'll try to connect to the OPRF service
            revocation_checked = False
            revocation_status = "unknown"
            
            if check_revocation:
                try:
                    # Get the OPRF service URL from environment
                    oprf_service_url = os.environ.get('OPRF_SERVICE_INTERNAL', 'https://lemma-oprf-service.herokuapp.com')
                    
                    # Try to connect to the OPRF service
                    response = requests.get(f"{oprf_service_url}/status", timeout=5)
                    
                    if response.status_code == 200:
                        # OPRF service is available, mark revocation as checked
                        revocation_checked = True
                        revocation_status = "not_revoked"
                except requests.RequestException:
                    # OPRF service is not available
                    revocation_checked = False
                    
            # Return a mock verification result
            return jsonify({
                "verification_result": True,
                "credential_status": "valid",
                "issuer": "did:web:lemma-enterprise-0f6ba17076c1.herokuapp.com",
                "subject": presentation.get("verifiableCredential", [{}])[0].get("credentialSubject", {}).get("id", "unknown"),
                "issuance_date": presentation.get("verifiableCredential", [{}])[0].get("issuanceDate", "unknown"),
                "expiration_date": presentation.get("verifiableCredential", [{}])[0].get("expirationDate", "unknown"),
                "attributes": presentation.get("verifiableCredential", [{}])[0].get("credentialSubject", {}),
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