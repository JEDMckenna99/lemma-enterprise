#!/usr/bin/env python3
"""
OPRF Service Integration Test Script
Tests the OPRF service integration with the main Lemma application.
"""

import requests
import json
import base64
import os
import sys
import time
import logging
import uuid
from urllib.parse import urljoin

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OPRFTester:
    def __init__(self, base_url=None):
        # Use provided URL or default to localhost for testing
        self.base_url = base_url or "http://localhost:5000"
        logger.info(f"Testing OPRF service at {self.base_url}")
        
        # Generate a unique credential ID for testing
        self.test_credential_id = f"test-credential-{uuid.uuid4()}"
    
    def _get_full_url(self, path):
        """Convert relative path to full URL"""
        return urljoin(self.base_url, path)
    
    def test_status(self):
        """Test the OPRF service status endpoint"""
        logger.info("Testing OPRF status endpoint...")
        try:
            response = requests.get(self._get_full_url('/api/oprf/status'), timeout=10)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"OPRF status response: {json.dumps(result, indent=2)}")
            
            if result.get('status') == 'ok' and 'oprf_service' in result:
                logger.info("✓ OPRF service status endpoint working")
                return True
            else:
                logger.error("✗ OPRF service returned unexpected response format")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Error connecting to OPRF status endpoint: {e}")
            return False
    
    def test_evaluate(self):
        """Test the OPRF evaluation endpoint"""
        logger.info("Testing OPRF evaluation endpoint...")
        try:
            # Create a mock blinded input (this would normally be created using cryptographic operations)
            mock_blinded = base64.b64encode(os.urandom(32)).decode('utf-8')
            
            payload = {
                "blinded_input": mock_blinded,
                "credential_id": self.test_credential_id
            }
            
            response = requests.post(
                self._get_full_url('/api/oprf/evaluate'),
                json=payload,
                timeout=10
            )
            
            # Check if the request was accepted
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Evaluation response: {json.dumps(result, indent=2)}")
                
                if 'result' in result:
                    logger.info("✓ OPRF evaluation endpoint working")
                    return True
                else:
                    logger.error("✗ OPRF evaluation returned unexpected response format")
                    return False
            else:
                logger.error(f"✗ OPRF evaluation failed with status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Error connecting to OPRF evaluation endpoint: {e}")
            return False
    
    def test_full_integration(self):
        """Test a full OPRF integration flow"""
        logger.info("\n=== Testing full OPRF integration flow ===")
        
        # Step 1: Check the OPRF service status
        status_ok = self.test_status()
        if not status_ok:
            logger.error("Failed at status check, stopping integration test")
            return False
        
        # Step 2: Test OPRF evaluation
        eval_ok = self.test_evaluate()
        if not eval_ok:
            logger.error("Failed at evaluation test, stopping integration test")
            return False
        
        # Additional integration tests could be added here
        
        logger.info("✓ All OPRF integration tests passed")
        return True

def main():
    """Main entry point for the test script"""
    # Parse command line arguments
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = os.environ.get('LEMMA_BASE_URL', "http://localhost:5000")
    
    # Check if testing against Heroku
    if 'herokuapp.com' in base_url:
        logger.info(f"Testing against Heroku deployment: {base_url}")
    
    # Run the tests
    tester = OPRFTester(base_url)
    success = tester.test_full_integration()
    
    # Exit with appropriate code
    if success:
        logger.info("\n✓✓✓ OPRF service is working correctly")
        sys.exit(0)
    else:
        logger.error("\n✗✗✗ OPRF service test failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 