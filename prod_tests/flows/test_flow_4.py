"""
Flow 4: Cascade download & verification

Tests the cascade download and verification process, including signature verification
and size constraints.
"""
import pytest
import json
import time
import os
import base64
import hashlib
import logging
from unittest.mock import patch, MagicMock

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test ID
FLOW_ID = 4
FLOW_NAME = "Cascade download & verification"

@pytest.fixture
def mock_cascade_bundle(epoch):
    """Create a mock cascade bundle."""
    bundle = {
        "metadata": {
            "issuer": "did:lemma:test",
            "epoch": epoch,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "revoked_count": 100,
            "hash": hashlib.sha256(f"cascade_{epoch}".encode()).hexdigest()
        },
        "levels": [
            {
                "bloom_filter": {
                    "capacity": 10000,
                    "error_rate": 0.02,
                    "bit_array": base64.b64encode(os.urandom(4096)).decode('utf-8'),
                    "hash_count": 5
                }
            },
            {
                "bloom_filter": {
                    "capacity": 100000,
                    "error_rate": 0.002,
                    "bit_array": base64.b64encode(os.urandom(8192)).decode('utf-8'),
                    "hash_count": 7
                }
            },
            {
                "bloom_filter": {
                    "capacity": 1000000,
                    "error_rate": 0.0002,
                    "bit_array": base64.b64encode(os.urandom(16384)).decode('utf-8'),
                    "hash_count": 10
                }
            }
        ],
        "signature": {
            "signature": base64.b64encode(os.urandom(64)).decode('utf-8'),
            "signer": "did:lemma:test#key-1",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
    }
    return bundle

def test_cascade_endpoint_available(client, epoch):
    """Test that the cascade endpoint is available."""
    logger.debug(f"Testing cascade endpoint for epoch: {epoch}")
    
    # Check if we can access the data directory
    from flask import current_app
    with client.application.app_context():
        data_dir = current_app.config.get('STORAGE_DIR', 'instance/data')
        cascade_dir = os.path.join(data_dir, 'revocation', 'cascades')
        logger.debug(f"Cascade directory: {cascade_dir}")
        
        if os.path.exists(cascade_dir):
            files = os.listdir(cascade_dir)
            logger.debug(f"Files in cascade directory: {files}")
    
    # Try to access the cascade endpoint
    endpoint = f'/cascade/{epoch}'
    logger.debug(f"Accessing endpoint: {endpoint}")
    response = client.get(endpoint)
    logger.debug(f"Response status: {response.status_code}")
    
    if hasattr(response, 'data'):
        logger.debug(f"Response data: {response.data[:100]}...")
    
    # If the endpoint doesn't exist, skip the tests
    if response.status_code == 404:
        logger.debug("Cascade endpoint not available, skipping tests")
        pytest.skip("Cascade endpoint not available")
    
    # Should either return a cascade or a 403/401 if auth required
    assert response.status_code in [200, 401, 403], \
        f"Cascade endpoint returned unexpected status: {response.status_code}"

def test_cascade_download(client, epoch, api_key):
    """Test downloading a cascade bundle."""
    logger.debug(f"Testing cascade download for epoch: {epoch}")
    
    # Try to download the cascade with API key
    response = client.get(
        f'/cascade/{epoch}',
        headers={'X-API-Key': api_key}
    )
    
    # If no cascade found, skip
    if response.status_code == 404:
        logger.debug(f"No cascade found for epoch {epoch}, skipping tests")
        pytest.skip("No cascade found for the current epoch")
    
    # Should return 200 with a JSON cascade
    assert response.status_code == 200, \
        f"Failed to download cascade: {response.status_code}"
    
    # Try to parse the response as JSON
    try:
        cascade = response.json
    except:
        # If not JSON, fall back to trying to parse the data
        cascade = json.loads(response.data)
    
    # Check cascade structure
    assert "metadata" in cascade, "No metadata in cascade"
    assert "levels" in cascade, "No levels in cascade"
    assert "signature" in cascade, "No signature in cascade"
    
    # Check metadata
    assert "issuer" in cascade["metadata"], "No issuer in metadata"
    assert "epoch" in cascade["metadata"], "No epoch in metadata"
    assert "created" in cascade["metadata"], "No created timestamp in metadata"
    
    # Epoch should match requested epoch
    assert cascade["metadata"]["epoch"] == epoch, \
        f"Epoch mismatch: {cascade['metadata']['epoch']} != {epoch}"
    
    # Check signature
    assert "signature" in cascade["signature"], "No signature in signature block"
    assert "signer" in cascade["signature"], "No signer in signature block"
    
    # Check levels (should have at least one)
    assert len(cascade["levels"]) > 0, "No levels in cascade"
    
    # Check first level
    assert "bloom_filter" in cascade["levels"][0], "No bloom filter in first level"
    assert "bit_array" in cascade["levels"][0]["bloom_filter"], "No bit array in first bloom filter"

def test_cascade_bundle_size(client, epoch, api_key, check_file_size):
    """Test that the cascade bundle size is within limits."""
    # Try to download the cascade with API key
    response = client.get(
        f'/cascade/{epoch}',
        headers={'X-API-Key': api_key}
    )
    
    # If no cascade found, skip
    if response.status_code == 404:
        pytest.skip("No cascade found for the current epoch")
    
    # Should return 200 with a JSON cascade
    assert response.status_code == 200, \
        f"Failed to download cascade: {response.status_code}"
    
    # Check the size of the response
    response_size_kb = len(response.data) / 1024
    
    # Should be <= 100 KB for 1M revoked credentials per spec
    assert response_size_kb <= 100, \
        f"Cascade bundle too large: {response_size_kb:.2f} KB > 100 KB"

def test_cascade_signature_verification(client, epoch, api_key):
    """Test verifying the cascade signature."""
    # Try to download the cascade with API key
    response = client.get(
        f'/cascade/{epoch}',
        headers={'X-API-Key': api_key}
    )
    
    # If no cascade found, skip
    if response.status_code == 404:
        pytest.skip("No cascade found for the current epoch")
    
    # Should return 200 with a JSON cascade
    assert response.status_code == 200, \
        f"Failed to download cascade: {response.status_code}"
    
    # Try to parse the response as JSON
    try:
        cascade = response.json
    except:
        # If not JSON, fall back to trying to parse the data
        cascade = json.loads(response.data)
    
    # Now verify the signature
    # First check if we can import the necessary modules
    try:
        from lemma.core.cascaded_bloom import verify_cascade_signature
    except ImportError:
        pytest.skip("Cascade signature verification not available")
    
    # Verify the signature
    is_valid = verify_cascade_signature(cascade)
    assert is_valid, "Cascade signature verification failed"

def test_tampered_signature_rejection():
    """Test that a tampered signature is rejected."""
    try:
        from lemma.core.cascaded_bloom import verify_cascade_signature
    except ImportError:
        pytest.skip("Cascade signature verification not available")
    
    # Create a cascade bundle
    cascade = {
        "metadata": {
            "issuer": "did:lemma:test",
            "epoch": "2023-01-01",
            "created": "2023-01-01T00:00:00Z",
            "revoked_count": 100,
            "hash": "0123456789abcdef0123456789abcdef"
        },
        "levels": [
            {
                "bloom_filter": {
                    "capacity": 10000,
                    "error_rate": 0.02,
                    "bit_array": "AAAA",
                    "hash_count": 5
                }
            }
        ],
        "signature": {
            "signature": "TAMPERED_SIGNATURE",
            "signer": "did:lemma:test#key-1",
            "created": "2023-01-01T00:00:00Z"
        }
    }
    
    # Verify the signature - should fail
    is_valid = verify_cascade_signature(cascade)
    assert not is_valid, "Tampered signature was incorrectly verified as valid"

def test_epoch_validity_window(client, epoch, api_key):
    """Test that the epoch is within the validity window."""
    # Try to download the cascade with API key
    response = client.get(
        f'/cascade/{epoch}',
        headers={'X-API-Key': api_key}
    )
    
    # If no cascade found, skip
    if response.status_code == 404:
        pytest.skip("No cascade found for the current epoch")
    
    # Should return 200 with a JSON cascade
    assert response.status_code == 200, \
        f"Failed to download cascade: {response.status_code}"
    
    # Try to parse the response as JSON
    try:
        cascade = response.json
    except:
        # If not JSON, fall back to trying to parse the data
        cascade = json.loads(response.data)
    
    # Check the created timestamp
    created = cascade["metadata"]["created"]
    
    # Parse the timestamp
    import datetime
    try:
        # Try ISO format
        created_dt = datetime.datetime.fromisoformat(created.replace('Z', '+00:00'))
    except:
        # Try RFC 3339 format
        from dateutil import parser
        created_dt = parser.parse(created)
    
    # Ensure the created time is not more than 24 hours old
    now = datetime.datetime.now(datetime.timezone.utc)
    age = now - created_dt
    
    # Should be less than 24 hours (86400 seconds)
    assert age.total_seconds() < 86400, \
        f"Cascade is too old: {age.total_seconds()/3600:.2f} hours > 24 hours" 