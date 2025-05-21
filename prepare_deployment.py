#!/usr/bin/env python3
"""
Prepare Deployment Script for Lemma Enterprise

This script prepares the Lemma Enterprise system for production deployment
by setting up necessary files, configurations, and testing that everything
works correctly.
"""

import os
import sys
import json
import subprocess
import logging
import argparse
import shutil
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('deployment_prep.log')
    ]
)
logger = logging.getLogger('prepare_deployment')

def setup_env(env_file='.env', production=False):
    """Set up environment variables file."""
    logger.info(f"Setting up environment file: {env_file}")
    
    # Template file to copy from
    template_file = '.env.production.template' if production else '.env'
    
    # If template doesn't exist but default env does, use that
    if not os.path.exists(template_file) and os.path.exists('.env'):
        template_file = '.env'
    
    # If template exists and it's not the same as the target file, copy it
    if os.path.exists(template_file) and os.path.abspath(template_file) != os.path.abspath(env_file):
        shutil.copy(template_file, env_file)
        logger.info(f"Copied {template_file} to {env_file}")
    elif not os.path.exists(env_file):
        # Create a minimal env file
        with open(env_file, 'w') as f:
            f.write("# Lemma Enterprise Environment Variables\n")
            f.write("FLASK_APP=app.py\n")
            f.write("FLASK_RUN_PORT=5000\n")
            f.write("LEMMA_ADMIN_USER=admin\n")
            f.write("LEMMA_ADMIN_PASS=password\n")
            f.write("LEMMA_STORAGE_DIR=instance/data\n")
            f.write("LEMMA_API_KEY=test_api_key\n")
            f.write("LEMMA_ADMIN_API_KEY=admin_api_key\n")
            
            # Production settings
            if production:
                f.write("LEMMA_DISABLE_MOCK_SERVICES=true\n")
                f.write("LEMMA_REQUIRE_HTTPS=true\n")
                f.write("LEMMA_STRICT_CSRF=true\n")
                f.write("LEMMA_STRICT_API_KEYS=true\n")
        
        logger.info(f"Created new environment file: {env_file}")
    else:
        logger.info(f"Using existing environment file: {env_file}")
    
    return env_file

def setup_keys(storage_dir='instance/data'):
    """Set up cryptographic keys for the application."""
    logger.info("Setting up cryptographic keys")
    
    # Create the keys directory
    keys_dir = os.path.join(storage_dir, 'keys')
    os.makedirs(keys_dir, exist_ok=True)
    
    # Generate Ed25519 keys for signing
    logger.info("Generating Ed25519 key pair")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Encode the keys
    private_bytes = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption()
    )
    public_bytes = public_key.public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw
    )
    
    # Create key dictionary
    keys = {
        "ed25519_private": base64.b64encode(private_bytes).decode('utf-8'),
        "ed25519_public": base64.b64encode(public_bytes).decode('utf-8'),
        "created": datetime.now().isoformat(),
        "key_id": "key-1"
    }
    
    # Save the keys
    keys_file = os.path.join(keys_dir, 'keys.json')
    with open(keys_file, 'w') as f:
        json.dump(keys, f, indent=2)
    
    logger.info(f"Saved keys to {keys_file}")
    return keys_file

def setup_storage(storage_dir='instance/data'):
    """Set up storage directories."""
    logger.info(f"Setting up storage in {storage_dir}")
    
    # Main data directory
    os.makedirs(storage_dir, exist_ok=True)
    
    # Keys directory
    keys_dir = os.path.join(storage_dir, 'keys')
    os.makedirs(keys_dir, exist_ok=True)
    
    # Revocation directories
    revocation_dir = os.path.join(storage_dir, 'revocation')
    os.makedirs(revocation_dir, exist_ok=True)
    
    cascades_dir = os.path.join(revocation_dir, 'cascades')
    os.makedirs(cascades_dir, exist_ok=True)
    
    registry_dir = os.path.join(revocation_dir, 'registry')
    os.makedirs(registry_dir, exist_ok=True)
    
    # Logs directory
    logs_dir = os.path.join(storage_dir, '..', 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    logger.info("Storage directories created successfully")
    return storage_dir

def build_initial_cascade(storage_dir='instance/data'):
    """Build initial cascade for testing."""
    logger.info("Building initial cascade")
    
    # Run the revoke_and_build.py script to create a test cascade
    try:
        result = subprocess.run(
            [sys.executable, 'revoke_and_build.py', '--test', '--storage', storage_dir],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Successfully built initial cascade")
        logger.debug(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error building cascade: {e}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return False

def run_flow_tests():
    """Run the flow tests to verify the system works."""
    logger.info("Running flow tests")
    
    try:
        # Create a pytest command to run flow test 4
        from datetime import datetime
        epoch = datetime.now().strftime('%Y-%m-%d')
        
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', 'prod_tests/flows/test_flow_4.py', '-v'],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Flow test 4 passed successfully")
        logger.debug(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Flow test 4 failed: {e}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return False

def setup_heroku_config():
    """Set up Heroku configuration."""
    logger.info("Setting up Heroku configuration")
    
    # Check if Heroku CLI is installed
    try:
        result = subprocess.run(['heroku', '--version'], capture_output=True, text=True, check=True)
        logger.info(f"Heroku CLI detected: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Heroku CLI not found. Please install it to deploy to Heroku.")
        return False
    
    # Check if we're already logged in
    try:
        result = subprocess.run(['heroku', 'auth:whoami'], capture_output=True, text=True, check=True)
        logger.info(f"Logged in as: {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        logger.warning("Not logged in to Heroku. Please run 'heroku login' to authenticate.")
        return False
    
    # Prompt for app name
    app_name = input("Enter Heroku app name (leave blank to create new): ").strip()
    
    if not app_name:
        # Create a new app
        try:
            result = subprocess.run(['heroku', 'create'], capture_output=True, text=True, check=True)
            app_name = result.stdout.strip().split('|')[0].strip().split(' ')[-1]
            logger.info(f"Created new Heroku app: {app_name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating Heroku app: {e}")
            return False
    
    # Set environment variables from .env.production
    if os.path.exists('.env.production'):
        logger.info("Setting Heroku config variables from .env.production")
        with open('.env.production', 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse the variable
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key, value = parts
                    try:
                        subprocess.run(
                            ['heroku', 'config:set', f"{key}={value}", '--app', app_name],
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        logger.info(f"Set {key} for {app_name}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Error setting {key}: {e}")
    
    logger.info(f"Heroku configuration complete for app: {app_name}")
    logger.info(f"To deploy, run: git push heroku main")
    return True

def main():
    parser = argparse.ArgumentParser(description="Prepare Lemma Enterprise for deployment")
    parser.add_argument("--prod", action="store_true", help="Prepare for production deployment")
    parser.add_argument("--storage", default="instance/data", help="Storage directory")
    parser.add_argument("--heroku", action="store_true", help="Configure for Heroku deployment")
    parser.add_argument("--test-flow-4", action="store_true", help="Run flow test 4")
    args = parser.parse_args()
    
    # Set up storage
    setup_storage(args.storage)
    
    # Set up environment
    env_file = '.env.production' if args.prod else '.env'
    setup_env(env_file, args.prod)
    
    # Set up cryptographic keys
    setup_keys(args.storage)
    
    # Build initial cascade
    build_initial_cascade(args.storage)
    
    # Run flow test 4 if requested
    if args.test_flow_4:
        if run_flow_tests():
            logger.info("Flow test 4 passed - system is ready for production")
        else:
            logger.error("Flow test 4 failed - please fix issues before deploying")
    
    # Set up Heroku if requested
    if args.heroku:
        setup_heroku_config()
    
    logger.info("Deployment preparation complete")

if __name__ == "__main__":
    main()
