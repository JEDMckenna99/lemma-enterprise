#!/usr/bin/env python3
"""
Lemma Enterprise: Human Verification System with DID Proofing

A streamlined, enterprise-grade implementation for verifying humans
with minimal data collection and strong cryptographic standards.
"""
import os
import logging
from lemma import create_app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the application instance
logger.info("Creating Lemma Enterprise application")
logger.info(f"Current working directory: {os.getcwd()}")

app = create_app()

# Configuration - Use instance folder for Heroku compatibility
DATA_DIR = os.path.join(os.getcwd(), 'instance', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

KEYS_FILE = os.path.join(DATA_DIR, 'keys.json')
REGISTRY_FILE = os.path.join(DATA_DIR, 'registry.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

# Admin credentials (should be set via environment variables in production)
ADMIN_USERNAME = os.environ.get('LEMMA_ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('LEMMA_ADMIN_PASS', 'password')

if __name__ == '__main__':
    """Run the application when executed directly."""
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    logger.info(f"Starting application on port {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)
