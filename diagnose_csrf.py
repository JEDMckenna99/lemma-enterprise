"""
Diagnose CSRF token issues in the Lemma Enterprise application.

This script checks various components of the CSRF token system:
1. Configuration in Flask app
2. Token generation
3. Token validation
4. Session storage

Usage:
    python diagnose_csrf.py
"""

import os
import sys
import json
import requests
from urllib.parse import urljoin
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_csrf_configuration(base_url):
    """Check CSRF configuration by making test requests."""
    logger.info("Checking CSRF token generation...")
    
    # Step 1: Get a CSRF token
    try:
        token_response = requests.get(urljoin(base_url, "/api/generate-csrf-token"))
        token_response.raise_for_status()
        token_data = token_response.json()
        
        if 'csrf_token' in token_data:
            token = token_data['csrf_token']
            logger.info(f"Successfully obtained CSRF token: {token[:10]}...")
        else:
            logger.error("Token endpoint didn't return a csrf_token field")
            return False
    except Exception as e:
        logger.error(f"Error getting CSRF token: {str(e)}")
        return False
    
    # Step 2: Test the token with both header and JSON payload methods
    try:
        # Test with header
        logger.info("Testing CSRF token in header...")
        header_response = requests.post(
            urljoin(base_url, "/api/verify-presentation"),
            headers={'X-CSRF-Token': token, 'Content-Type': 'application/json'},
            json={'presentation': {}, 'challenge': 'test', 'csrf_token': token}
        )
        
        # Even if we get a 400, it should be for missing credentials, not CSRF
        if header_response.status_code == 400:
            error_data = header_response.json()
            if 'error' in error_data and 'CSRF' in error_data['error']:
                logger.error(f"CSRF validation failed with token in header: {error_data}")
                return False
            logger.info("Token in header accepted (got expected 400 for missing presentation data)")
        
        # Test with JSON payload
        logger.info("Testing CSRF token in JSON payload...")
        json_response = requests.post(
            urljoin(base_url, "/api/verify-presentation"),
            headers={'Content-Type': 'application/json'},
            json={'presentation': {}, 'challenge': 'test', 'csrf_token': token}
        )
        
        # Check if it's a CSRF error
        if json_response.status_code == 400:
            error_data = json_response.json()
            if 'error' in error_data and 'CSRF' in error_data['error']:
                logger.error(f"CSRF validation failed with token in JSON: {error_data}")
                return False
            logger.info("Token in JSON payload accepted (got expected 400 for missing presentation data)")
        
        return True
    except Exception as e:
        logger.error(f"Error testing CSRF token: {str(e)}")
        return False

def main():
    """Main diagnostic function."""
    logger.info("Starting CSRF token diagnostic...")
    
    # Get base URL from argument or use default
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    logger.info(f"Using base URL: {base_url}")
    
    # Check CSRF configuration
    if check_csrf_configuration(base_url):
        logger.info("✅ CSRF token system appears to be working correctly")
    else:
        logger.error("❌ CSRF token system has issues")
        
    logger.info("Diagnostics complete")

if __name__ == "__main__":
    main()
