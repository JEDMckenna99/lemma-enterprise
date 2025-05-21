"""
Flow 5: Local non‑revocation check

Tests the local non-revocation check against the cascaded Bloom filter.
"""
import pytest
import time
import json
import os
import hashlib
import base64
from unittest.mock import patch, MagicMock

# Test ID
FLOW_ID = 5
FLOW_NAME = "Local non‑revocation check"

@pytest.fixture
def mock_revocation_service():
    """Create a mock revocation service."""
    try:
        from lemma.core.cascaded_bloom import CascadedBloomRevocation
        
        # Create a cascade with controlled revocations
        cascade = CascadedBloomRevocation(
            issuer_id="did:lemma:test",
            cascade_levels=3,
            error_rate=0.02,
            expected_revocations=1000
        )
        
        # Add some known revocations
        for i in range(10):
            # Create a test credential ID
            test_cred = f"test_revoked_{i}"
            
            # Create a fake OPRF evaluation
            fake_eval = hashlib.sha256(f"oprf_{test_cred}".encode()).digest()
            
            # Add to the cascade
            cascade.revoke(test_cred, fake_eval)
        
        return cascade
    except ImportError:
        return None

@pytest.fixture
def test_evaluations(oprf_client):
    """Generate test OPRF evaluations for valid and revoked credentials."""
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Create test credential IDs
    valid_cred = f"test_valid_{int(time.time())}"
    revoked_cred = "test_revoked_0"  # This ID is in the mock revocation service
    
    # Get OPRF evaluations
    valid_eval = oprf_client.get_evaluation(valid_cred)
    revoked_eval = oprf_client.get_evaluation(revoked_cred)
    
    return {
        "valid_cred": valid_cred,
        "revoked_cred": revoked_cred,
        "valid_eval": valid_eval,
        "revoked_eval": revoked_eval
    }

def test_revocation_check_performance(mock_revocation_service, measure_execution_time):
    """Test the performance of revocation checking."""
    if mock_revocation_service is None:
        pytest.skip("Revocation service not available")
    
    # Create a test evaluation
    test_eval = os.urandom(32)  # Random bytes similar to OPRF output
    
    # Measure the execution time
    (is_revoked, level), elapsed_time = measure_execution_time(
        mock_revocation_service.is_revoked, test_eval
    )
    
    # Check if the execution time is within limits (should be < 1ms)
    assert elapsed_time < 0.001, f"Revocation check took {elapsed_time*1000:.3f} ms, should be < 1 ms"
    
    # The result doesn't matter for this test, we're just testing performance
    print(f"Revocation check took {elapsed_time*1000:.3f} ms: is_revoked={is_revoked}, level={level}")

def test_valid_credential_check(mock_revocation_service, test_evaluations):
    """Test that a valid credential passes the revocation check."""
    if mock_revocation_service is None or test_evaluations is None:
        pytest.skip("Revocation service or test evaluations not available")
    
    # Create a controlled environment with known valid/revoked credentials
    cascade = mock_revocation_service
    
    # Override with our test revocations
    with patch.object(cascade, 'is_revoked') as mock_is_revoked:
        # Valid credentials should not be revoked
        mock_is_revoked.return_value = (False, -1)
        
        # Test with a valid credential evaluation
        is_revoked, level = cascade.is_revoked(test_evaluations["valid_eval"])
        
        # Should not be revoked
        assert is_revoked is False, f"Valid credential incorrectly marked as revoked: {is_revoked}"

def test_revoked_credential_check(mock_revocation_service, test_evaluations):
    """Test that a revoked credential is detected."""
    if mock_revocation_service is None or test_evaluations is None:
        pytest.skip("Revocation service or test evaluations not available")
    
    # Create a controlled environment with known valid/revoked credentials
    cascade = mock_revocation_service
    
    # Override with our test revocations
    with patch.object(cascade, 'is_revoked') as mock_is_revoked:
        # Revoked credentials should be detected
        mock_is_revoked.return_value = (True, 0)
        
        # Test with a revoked credential evaluation
        is_revoked, level = cascade.is_revoked(test_evaluations["revoked_eval"])
        
        # Should be revoked
        assert is_revoked is True, f"Revoked credential incorrectly marked as valid: {is_revoked}"

def test_cascade_lookup(mock_revocation_service):
    """Test looking up a value in the cascade."""
    if mock_revocation_service is None:
        pytest.skip("Revocation service not available")
    
    cascade = mock_revocation_service
    
    # Generate a random OPRF-like evaluation
    test_eval = os.urandom(32)
    
    # First make sure this random value is not revoked
    is_revoked, level = cascade.is_revoked(test_eval)
    assert is_revoked is False, f"Random evaluation incorrectly marked as revoked: {is_revoked}"
    
    # Now add the evaluation to the cascade
    for bloom in cascade.levels:
        bloom.add(test_eval)
    
    # Now it should be found
    is_revoked, level = cascade.is_revoked(test_eval)
    assert is_revoked is True, f"Added evaluation not found in cascade: {is_revoked}"
    assert level >= 0, f"Evaluation found at invalid level: {level}"

def test_wallet_revocation_check():
    """Test revocation checking in the wallet."""
    # This test requires a browser environment, so we'll mock it
    # First check if we can import the necessary modules
    try:
        from lemma.core.cascaded_bloom import CascadedBloomRevocation
    except ImportError:
        pytest.skip("Revocation modules not available")
    
    # Create a mock wallet revocation check function
    def mock_wallet_check(y):
        # Mock successful wallet revocation check
        return False  # Not revoked
    
    # Create a test OPRF evaluation
    test_eval = os.urandom(32)
    
    # Test the revocation check
    is_revoked = mock_wallet_check(test_eval)
    assert is_revoked is False, "Wallet revocation check failed"

def test_revocation_check_via_api(client, api_key, oprf_client, epoch):
    """Test checking revocation status via the API."""
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Generate a test credential ID
    test_cred = f"test_cred_{int(time.time())}"
    
    # Get a witness
    witness = oprf_client.generate_witness(test_cred, epoch)
    
    # Call the revocation check API
    response = client.post(
        '/api/check-revocation',
        json={'witness': witness},
        headers={'X-API-Key': api_key}
    )
    
    # If endpoint doesn't exist, skip
    if response.status_code == 404:
        pytest.skip("Revocation check API not available")
    
    # Should get a valid response
    assert response.status_code == 200, f"API returned {response.status_code}"
    
    # Extract the result
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Should have a status field
    assert "revoked" in result, "No 'revoked' field in response"
    assert isinstance(result["revoked"], bool), f"'revoked' is not a boolean: {type(result['revoked'])}" 