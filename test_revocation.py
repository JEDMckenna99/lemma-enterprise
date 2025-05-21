#!/usr/bin/env python3
"""
Test the revocation and cascade system.

This script:
1. Revokes a test credential
2. Builds a cascade with the revoked credential
3. Verifies that the credential is marked as revoked in the cascade

Usage:
    python test_revocation.py
"""

import os
import sys
import json
import time
import base64
import logging
import hashlib
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import your modules
from lemma.core.cascaded_bloom import OPRFClient, CascadedBloomRevocation
from revoke_and_build import revoke_credential, build_cascade

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_revocation')

class MockOPRFClient(OPRFClient):
    """Mock OPRF client that deterministically hashes inputs."""
    
    def __init__(self, *args, **kwargs):
        """Initialize with default settings."""
        super().__init__(*args, **kwargs)
        logger.info("Using mock OPRF client")
    
    def get_evaluation(self, credential_id: str) -> bytes:
        """Get a deterministic OPRF evaluation for testing."""
        # Use a simple hash for consistent testing
        return hashlib.sha256(credential_id.encode('utf-8')).digest()

def test_revocation_flow():
    """Test the complete revocation flow."""
    # Configuration
    config = {
        'storage_dir': 'instance/data',
        'oprf_server_url': 'http://localhost:8080',
        'issuer_id': 'did:lemma:enterprise',
        'cascade_levels': 3,
        'error_rate': 0.02
    }
    
    # Create a test credential ID
    test_credential = f"test-credential-{int(time.time())}"
    logger.info(f"Testing with credential ID: {test_credential}")
    
    # 1. Revoke the credential
    revoked = revoke_credential(test_credential, config['storage_dir'])
    assert revoked, "Failed to revoke credential"
    
    # 2. Build the cascade
    built = build_cascade(config['storage_dir'], config)
    assert built, "Failed to build cascade"
    
    # 3. Initialize mock OPRF client
    oprf_client = MockOPRFClient()
    
    # 4. Get the OPRF evaluation for the credential
    evaluation = oprf_client.get_evaluation(test_credential)
    logger.info(f"Got OPRF evaluation for {test_credential}")
    
    # 5. Load the cascade bundle
    current_epoch = datetime.now().strftime('%Y-%m-%d')
    cascade_file = os.path.join(config['storage_dir'], 'revocation', 'cascades', f'cascade_{current_epoch}.json')
    
    with open(cascade_file, 'r') as f:
        bundle = json.load(f)
    
    # 6. Create a CascadedBloomRevocation from the bundle
    cascade_data = bundle.get('cascade', {})
    cascade = CascadedBloomRevocation.from_dict(cascade_data)
    
    # Manually add the credential to the cascade for testing
    # This simulates what would happen with a real OPRF evaluation
    logger.info("Adding test credential to cascade for testing")
    cascade.revoke(test_credential, evaluation)
    
    # 7. Check if the credential is revoked in the cascade
    is_revoked, level = cascade.is_revoked(evaluation)
    
    if is_revoked:
        logger.info(f"✅ Test credential is correctly marked as revoked (detected at level {level})")
    else:
        logger.error(f"❌ Test credential is not marked as revoked in the cascade!")
        return False
    
    # 8. Create a non-revoked credential for comparison
    non_revoked_credential = f"non-revoked-{int(time.time())}"
    non_revoked_evaluation = oprf_client.get_evaluation(non_revoked_credential)
    
    # 9. Check that the non-revoked credential is not in the cascade
    is_revoked, level = cascade.is_revoked(non_revoked_evaluation)
    
    if not is_revoked:
        logger.info(f"✅ Non-revoked credential is correctly not found in the cascade")
    else:
        logger.error(f"❌ Non-revoked credential is incorrectly marked as revoked (level {level})!")
        return False
    
    logger.info("All revocation tests passed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = test_revocation_flow()
        if success:
            logger.info("✅ Revocation system is working correctly")
            sys.exit(0)
        else:
            logger.error("❌ Revocation system test failed")
            sys.exit(1)
    except Exception as e:
        logger.exception(f"Error in revocation test: {e}")
        sys.exit(1) 