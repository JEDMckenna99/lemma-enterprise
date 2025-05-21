#!/usr/bin/env python3
"""
Lemma Enterprise: Human Verification System with DID Proofing

A streamlined, enterprise-grade implementation for verifying humans
with minimal data collection and strong cryptographic standards.
"""
import os
import logging
import sys
import json
from flask import Flask, redirect, request, jsonify
from lemma import create_app as lemma_create_app

# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# Make sure we can import from the current directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Configuration - Use instance folder for Heroku compatibility
DATA_DIR = os.path.join(os.getcwd(), 'instance', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

KEYS_FILE = os.path.join(DATA_DIR, 'keys.json')
REGISTRY_FILE = os.path.join(DATA_DIR, 'registry.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

# Admin credentials (should be set via environment variables in production)
ADMIN_USERNAME = os.environ.get('LEMMA_ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('LEMMA_ADMIN_PASS', 'password')

# Create app with configuration
def create_app(test_config=None):
    """Create the Flask application."""
    logger.info("Creating Lemma Enterprise application")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    # Create configuration if none provided
    if test_config is None:
        config = {
            'STORAGE_DIR': DATA_DIR,
            'ADMIN_USERNAME': ADMIN_USERNAME,
            'ADMIN_PASSWORD': ADMIN_PASSWORD
        }
    else:
        config = test_config
    
    # Import here to avoid circular imports
    app = lemma_create_app(config)
    
    # Add direct cascade route (for testing)
    @app.route('/cascade/<epoch>')
    def cascade_direct(epoch):
        logger.debug(f"Direct cascade request for epoch: {epoch}")
        try:
            # First try to find the cascade in the default location
            cascade_dir = os.path.join(DATA_DIR, 'revocation', 'cascades')
            cascade_file = os.path.join(cascade_dir, f'cascade_{epoch}.json')
            
            logger.debug(f"Looking for cascade file at: {cascade_file}")
            
            # If not found, try latest
            if not os.path.exists(cascade_file):
                logger.debug(f"Cascade file not found, trying latest")
                cascade_file = os.path.join(cascade_dir, 'cascade_latest.json')
            
            # If still not found, look in the test environment
            if not os.path.exists(cascade_file):
                test_dir = os.path.join('.lemma_prod_test', 'revocation', 'cascades')
                if os.path.exists(test_dir):
                    cascade_file = os.path.join(test_dir, f'cascade_{epoch}.json')
                    if not os.path.exists(cascade_file):
                        cascade_file = os.path.join(test_dir, 'cascade_latest.json')
            
            # If still not found, return 404
            if not os.path.exists(cascade_file):
                logger.debug(f"No cascade files found")
                return jsonify({"error": "No cascade found for epoch", "current_epoch": epoch}), 404
                    
            # Read and return the cascade file
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
    
    # Add endpoint for cascades listing
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
    
    return app

if __name__ == '__main__':
    """Run the application when executed directly."""
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    logger.info(f"Starting application on port {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)
