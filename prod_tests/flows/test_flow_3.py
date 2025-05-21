"""
Flow 3: OPRF enrolment (per epoch)

Tests the OPRF enrolment process, blinding, and unblinding operations.
"""
import pytest
import time
import os
import base64
import hashlib
from unittest.mock import patch, MagicMock

# Test ID
FLOW_ID = 3
FLOW_NAME = "OPRF enrolment (per epoch)"

@pytest.fixture
def mock_server_logs():
    """Fixture to capture server logs for testing."""
    log_entries = []
    
    # Mock the logger to capture log entries
    def mock_log(msg, *args, **kwargs):
        log_entries.append(msg)
    
    # Patch the logger
    with patch('lemma.core.cascaded_bloom.logger.info', mock_log), \
         patch('lemma.core.cascaded_bloom.logger.debug', mock_log), \
         patch('lemma.core.cascaded_bloom.logger.warning', mock_log), \
         patch('lemma.core.cascaded_bloom.logger.error', mock_log):
        
        yield log_entries

def test_oprf_endpoint_available(client):
    """Test that the OPRF evaluation endpoint is available."""
    # Get public key first to ensure service is initialized
    response = client.get('/pubkey')
    
    # Check if we got a valid response
    if response.status_code != 200:
        pytest.skip("OPRF service not available, skipping tests")
    
    # Now try the OPRF evaluation endpoint
    response = client.post('/oprfeval', json={
        "alpha": ["AAAA"]  # dummy value
    })
    
    # Should at least get a response, even if it's an error
    assert response.status_code in [200, 400, 422], \
        f"OPRF endpoint unavailable, got status {response.status_code}"

def test_oprf_blinding_flow(oprf_client, mock_server_logs):
    """Test the OPRF blinding and evaluation flow."""
    # Skip if OPRF client is not available
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Generate a test credential ID
    credential_id = f"test_cred_{time.time()}"
    
    # Step 1: Blind the credential ID
    alpha, r = oprf_client.blind(credential_id)
    
    # Check the blinded output
    assert alpha is not None, "Blinded alpha is None"
    assert len(alpha) > 0, "Blinded alpha is empty"
    assert r is not None, "Blinding factor r is None"
    assert len(r) > 0, "Blinding factor r is empty"
    
    # Step 2: Evaluate the blinded value
    beta = oprf_client.evaluate(alpha)
    
    # Check the evaluated output
    assert beta is not None, "Evaluated beta is None"
    assert len(beta) > 0, "Evaluated beta is empty"
    
    # Step 3: Unblind the result
    y = oprf_client.unblind(beta, r)
    
    # Check the unblinded output
    assert y is not None, "Unblinded y is None"
    assert len(y) > 0, "Unblinded y is empty"
    
    # Should be 32 bytes for ristretto255
    assert len(y) == 32, f"Expected 32 bytes for OPRF output, got {len(y)}"
    
    # Check server logs to ensure privacy
    log_str = ' '.join(mock_server_logs)
    
    # Server should log alpha (blinded value) but not the credential ID
    if 'alpha' in log_str.lower():
        assert credential_id not in log_str, "Credential ID leaked to server logs"

def test_oprf_direct_evaluation(oprf_client):
    """Test direct OPRF evaluation without separate steps."""
    # Skip if OPRF client is not available
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Generate a test credential ID
    credential_id = f"test_cred_{time.time()}"
    
    # Get direct evaluation
    result = oprf_client.get_evaluation(credential_id)
    
    # Check the result
    assert result is not None, "OPRF evaluation result is None"
    assert len(result) > 0, "OPRF evaluation result is empty"
    assert len(result) == 32, f"Expected 32 bytes for OPRF output, got {len(result)}"

def test_oprf_witness_creation(oprf_client, epoch):
    """Test creating an OPRF witness for a credential."""
    # Skip if OPRF client is not available
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Generate a test credential ID
    credential_id = f"test_cred_{time.time()}"
    
    # Get a witness
    witness = oprf_client.generate_witness(credential_id, epoch)
    
    # Check the witness
    assert witness is not None, "OPRF witness is None"
    assert "epoch" in witness, "No epoch in witness"
    assert "alpha" in witness, "No alpha in witness"
    assert "beta" in witness, "No beta in witness"
    assert "r" in witness, "No r in witness"
    assert "type" in witness, "No type in witness"
    
    # Verify epoch matches
    assert witness["epoch"] == epoch, f"Epoch mismatch: {witness['epoch']} != {epoch}"

@pytest.mark.parametrize("expired", [True, False])
def test_expired_epoch_key(oprf_client, epoch, expired):
    """Test handling of expired epoch keys."""
    # Skip if OPRF client is not available
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Mock epoch validation
    def mock_validate_epoch(e):
        if expired and e != epoch:
            raise ValueError(f"Expired epoch: {e}")
        return True
    
    # Generate a test credential ID
    credential_id = f"test_cred_{time.time()}"
    
    # Use current epoch or expired epoch
    test_epoch = epoch if not expired else f"{epoch}_old"
    
    with patch.object(oprf_client, '_validate_epoch', mock_validate_epoch):
        if expired:
            # Should raise exception for expired epoch
            with pytest.raises(ValueError):
                witness = oprf_client.generate_witness(credential_id, test_epoch)
        else:
            # Should work fine for current epoch
            witness = oprf_client.generate_witness(credential_id, test_epoch)
            assert witness is not None, "OPRF witness is None"
            assert witness["epoch"] == test_epoch, f"Epoch mismatch: {witness['epoch']} != {test_epoch}" 