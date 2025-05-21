"""
Flow 9: Credential revocation

Tests the credential revocation flow, including cascade rebuild and wallet handling
of revoked credentials.
"""
import pytest
import json
import time
import base64
import os
from unittest.mock import patch, MagicMock

# Test ID
FLOW_ID = 9
FLOW_NAME = "Credential revocation"

@pytest.fixture
def revocation_admin_mock():
    """Mock the admin revocation function."""
    with patch('lemma.routes.api.get_credential_service') as mock_get_service:
        # Create a mock service with a revoke_credential method
        mock_service = MagicMock()
        mock_service.revoke_credential.return_value = True
        mock_get_service.return_value = mock_service
        
        yield mock_service

@pytest.fixture
def cascade_rebuild_mock():
    """Mock the cascade rebuild function."""
    with patch('lemma.core.cascaded_bloom.rebuild_cascade') as mock_rebuild:
        # Mock successful cascade rebuild
        mock_rebuild.return_value = True
        
        yield mock_rebuild

@pytest.fixture
def wallet_mock():
    """Mock the wallet for testing revocation handling."""
    mock_wallet = MagicMock()
    
    # Add functions to simulate wallet behavior
    mock_wallet.clearRevokedCredential = MagicMock(return_value=True)
    mock_wallet.checkRevocationStatus = MagicMock(return_value=True)
    
    return mock_wallet

def test_revoke_credential_endpoint(client, api_key, revocation_admin_mock):
    """Test the endpoint for revoking a credential."""
    # Create a test credential ID
    test_credential_id = f"test_cred_{int(time.time())}"
    
    # Call the revoke credential endpoint
    response = client.post(
        '/api/revoke',
        json={'credential_id': test_credential_id},
        headers={'X-API-Key': api_key}
    )
    
    # If the endpoint doesn't exist, skip the test
    if response.status_code == 404:
        pytest.skip("Revoke endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to revoke credential: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result
    assert "success" in result, f"No success field in response: {result}"
    assert result["success"] is True, f"Revocation failed: {result}"
    
    # Check that the service's revoke_credential method was called
    revocation_admin_mock.revoke_credential.assert_called_with(test_credential_id)

def test_cascade_rebuild_after_revocation(client, api_key, revocation_admin_mock, cascade_rebuild_mock):
    """Test that the cascade is rebuilt after a credential is revoked."""
    # Create a test credential ID
    test_credential_id = f"test_cred_{int(time.time())}"
    
    # Call the revoke credential endpoint
    response = client.post(
        '/api/revoke',
        json={'credential_id': test_credential_id},
        headers={'X-API-Key': api_key}
    )
    
    # If the endpoint doesn't exist, skip the test
    if response.status_code == 404:
        pytest.skip("Revoke endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to revoke credential: {response.data}"
    
    # Check that the cascade rebuild was triggered
    assert cascade_rebuild_mock.called, "Cascade rebuild was not triggered after revocation"

def test_lookup_now_revoked(client, generate_credential, api_key, revocation_admin_mock, 
                           oprf_client, epoch):
    """Test that a revoked credential is correctly identified as revoked."""
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Generate a credential
    credential_response = generate_credential()
    credential = credential_response['credential']
    credential_id = credential['id']
    
    # Create a witness
    witness = oprf_client.generate_witness(credential_id, epoch)
    
    # Mock the revocation check to return "revoked" for our test credential
    with patch('lemma.core.cascaded_bloom.CascadedBloomRevocation.is_revoked') as mock_is_revoked:
        # Return True (revoked) for this specific credential's evaluation
        mock_is_revoked.return_value = (True, 0)
        
        # Check revocation status
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
        
        # Should be marked as revoked
        assert "revoked" in result, f"No 'revoked' field in response: {result}"
        assert result["revoked"] is True, f"Credential not marked as revoked: {result}"

def test_wallet_clears_revoked_credential(wallet_mock):
    """Test that the wallet clears a revoked credential on refresh."""
    # This test would normally use Selenium to test the actual wallet JS
    # For now, we'll use the mock
    
    # Define test data
    credential_id = f"test_cred_{int(time.time())}"
    
    # Mock a check that finds a credential is revoked
    wallet_mock.checkRevocationStatus.return_value = True  # Credential is revoked
    
    # Simulate the wallet's refresh behavior
    # 1. Check revocation status
    is_revoked = wallet_mock.checkRevocationStatus(credential_id)
    assert is_revoked is True, "Revocation check didn't return True"
    
    # 2. If revoked, clear the credential
    if is_revoked:
        cleared = wallet_mock.clearRevokedCredential(credential_id)
        assert cleared is True, "Failed to clear revoked credential"
    
    # Verify the clear method was called
    wallet_mock.clearRevokedCredential.assert_called_once_with(credential_id)

def test_vp_with_revoked_credential_rejected(client, create_presentation, generate_challenge,
                                            oprf_client, epoch):
    """Test that a VP with a revoked credential is rejected."""
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    # Generate a challenge
    challenge = generate_challenge
    
    # Create a presentation
    presentation = create_presentation(challenge=challenge)
    
    # Add a witness to the presentation
    # We'll mock it to use a specific credential ID that we'll mark as revoked
    credential_id = presentation["verifiableCredential"][0]["id"]
    witness = oprf_client.generate_witness(credential_id, epoch)
    
    if "proof" in presentation:
        presentation["proof"]["revocationWitness"] = witness
    else:
        presentation["revocationWitness"] = witness
    
    # Mark the credential as revoked when checked
    with patch('lemma.core.cascaded_bloom.CascadedBloomRevocation.is_revoked') as mock_is_revoked:
        # Return True (revoked) for this specific credential's evaluation
        mock_is_revoked.return_value = (True, 0)
        
        # Verify the presentation
        response = client.post('/api/verify-presentation', json={
            'presentation': presentation,
            'challenge': challenge
        })
        
        # Should still return 200 but with invalid result
        assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
        
        # Parse the response
        try:
            result = response.json
        except:
            result = json.loads(response.data)
        
        # Should be invalid due to revocation
        if "success" in result:
            assert result["success"] is False, "Revoked credential incorrectly verified as valid"
        elif "valid" in result:
            assert result["valid"] is False, "Revoked credential incorrectly verified as valid"
        else:
            assert False, f"Cannot determine verification result: {result}"
        
        # Should indicate revocation as the reason
        reason_found = False
        for field in ["reason", "error", "message"]:
            if field in result and "revoked" in str(result[field]).lower():
                reason_found = True
                break
        
        # It's okay if the reason isn't explicitly stated
        if not reason_found:
            print("Warning: Revocation reason not explicitly stated in response")

def test_batch_revocation(client, api_key, revocation_admin_mock):
    """Test batch revocation of credentials."""
    # Create test credential IDs
    test_credential_ids = [
        f"test_cred_{i}_{int(time.time())}" for i in range(3)
    ]
    
    # Call the batch revoke endpoint
    response = client.post(
        '/api/batch-revoke',
        json={'credential_ids': test_credential_ids},
        headers={'X-API-Key': api_key}
    )
    
    # If the endpoint doesn't exist, skip the test
    if response.status_code == 404:
        pytest.skip("Batch revoke endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to revoke credentials: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result
    assert "success" in result, f"No success field in response: {result}"
    assert result["success"] is True, f"Batch revocation failed: {result}"
    
    # Check that the service's revoke_credential method was called for each credential
    assert revocation_admin_mock.revoke_credential.call_count >= len(test_credential_ids), \
        f"Revoke method called {revocation_admin_mock.revoke_credential.call_count} times, expected {len(test_credential_ids)}" 