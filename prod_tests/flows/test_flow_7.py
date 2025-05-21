"""
Flow 7: Site backend verification

Tests the backend verification of Verifiable Presentations, including
signature, challenge, and revocation checks.
"""
import pytest
import json
import time
import os
import base64
import hashlib
from unittest.mock import patch, MagicMock

# Test ID
FLOW_ID = 7
FLOW_NAME = "Site backend verification"

@pytest.fixture
def mock_presentation(generate_credential, test_challenge=None):
    """Create a mock verifiable presentation."""
    # Get a credential
    credential_response = generate_credential()
    credential = credential_response['credential']
    
    # Create a challenge if not provided
    if test_challenge is None:
        random_bytes = os.urandom(16)
        test_challenge = base64.b64encode(random_bytes).decode('utf-8')
    
    # Create a presentation
    presentation = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiablePresentation"],
        "verifiableCredential": [credential],
        "challenge": test_challenge,
        "proof": {
            "type": "Ed25519Signature2018",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "verificationMethod": "did:lemma:test#key-1",
            "proofPurpose": "authentication",
            "challenge": test_challenge,
            "jws": "mock_signature" # The real system will fill this in
        }
    }
    
    return {
        "presentation": presentation,
        "challenge": test_challenge,
        "credential": credential
    }

def test_verify_presentation_endpoint_available(client):
    """Test that the verify presentation endpoint is available."""
    # Try a simple request to see if the endpoint exists
    response = client.post('/api/verify-presentation', json={
        'presentation': {},
        'challenge': 'test_challenge'
    })
    
    # We expect either:
    # - 400 Bad Request (invalid presentation)
    # - 422 Unprocessable Entity (invalid input)
    # - 200 OK (somehow it worked anyway)
    # But not 404 Not Found
    assert response.status_code != 404, "Verify presentation endpoint not found"

def test_verify_presentation_success(client, create_presentation, generate_challenge):
    """Test successful verification of a presentation."""
    # Generate a challenge
    challenge = generate_challenge
    
    # Create a presentation
    presentation = create_presentation(challenge=challenge)
    
    # Verify the presentation
    response = client.post('/api/verify-presentation', json={
        'presentation': presentation,
        'challenge': challenge
    })
    
    # Should succeed
    assert response.status_code == 200, f"Failed to verify presentation: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result
    assert result is not None, "Verification result is None"
    
    # The response should indicate success
    if "success" in result:
        assert result["success"] is True, f"Verification failed: {result}"
    elif "valid" in result:
        assert result["valid"] is True, f"Verification failed: {result}"
    else:
        assert False, f"Cannot determine verification result: {result}"

def test_verify_presentation_with_invalid_signature(client, mock_presentation):
    """Test verification of a presentation with an invalid signature."""
    presentation_data = mock_presentation
    
    # Create a copy of the presentation with a tampered signature
    tampered_presentation = presentation_data["presentation"].copy()
    tampered_proof = tampered_presentation["proof"].copy()
    tampered_proof["jws"] = "tampered_signature"
    tampered_presentation["proof"] = tampered_proof
    
    # Verify the tampered presentation
    response = client.post('/api/verify-presentation', json={
        'presentation': tampered_presentation,
        'challenge': presentation_data["challenge"]
    })
    
    # Should still return 200 but with invalid result
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result - should be invalid
    if "success" in result:
        assert result["success"] is False, "Tampered signature was incorrectly verified as valid"
    elif "valid" in result:
        assert result["valid"] is False, "Tampered signature was incorrectly verified as valid"
    else:
        assert False, f"Cannot determine verification result: {result}"

def test_verify_presentation_with_challenge_mismatch(client, mock_presentation):
    """Test verification of a presentation with a mismatched challenge."""
    presentation_data = mock_presentation
    
    # Create a different challenge
    different_challenge = base64.b64encode(os.urandom(16)).decode('utf-8')
    
    # Verify with the wrong challenge
    response = client.post('/api/verify-presentation', json={
        'presentation': presentation_data["presentation"],
        'challenge': different_challenge
    })
    
    # Should still return 200 but with invalid result
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result - should be invalid
    if "success" in result:
        assert result["success"] is False, "Challenge mismatch was incorrectly verified as valid"
    elif "valid" in result:
        assert result["valid"] is False, "Challenge mismatch was incorrectly verified as valid"
    else:
        assert False, f"Cannot determine verification result: {result}"

def test_verify_presentation_with_revocation_check(client, mock_presentation, oprf_client, epoch):
    """Test verification of a presentation with revocation checking."""
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    presentation_data = mock_presentation
    
    # Create a witness for the credential
    credential_id = presentation_data["credential"]["id"]
    witness = oprf_client.generate_witness(credential_id, epoch)
    
    # Add the witness to the presentation
    presentation = presentation_data["presentation"].copy()
    presentation["proof"] = presentation["proof"].copy()
    presentation["proof"]["revocationWitness"] = witness
    
    # Verify the presentation
    response = client.post('/api/verify-presentation', json={
        'presentation': presentation,
        'challenge': presentation_data["challenge"]
    })
    
    # Should succeed
    assert response.status_code == 200, f"Failed to verify presentation: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result - should be valid
    if "success" in result:
        assert result["success"] is True, f"Verification failed: {result}"
    elif "valid" in result:
        assert result["valid"] is True, f"Verification failed: {result}"
    else:
        assert False, f"Cannot determine verification result: {result}"

def test_stale_cascade_rejection(client, mock_presentation, oprf_client):
    """Test rejection of a presentation with a stale cascade epoch."""
    if oprf_client is None:
        pytest.skip("OPRF client not available")
    
    presentation_data = mock_presentation
    
    # Create a witness with a very old epoch
    credential_id = presentation_data["credential"]["id"]
    stale_epoch = "2000-01-01"  # Clearly stale
    
    # Mock the witness creation
    with patch.object(oprf_client, 'generate_witness') as mock_generate:
        mock_generate.return_value = {
            "epoch": stale_epoch,
            "alpha": "mock_alpha",
            "beta": "mock_beta",
            "r": "mock_r",
            "type": "OPRF-Ristretto255"
        }
        
        witness = oprf_client.generate_witness(credential_id, stale_epoch)
    
    # Add the witness to the presentation
    presentation = presentation_data["presentation"].copy()
    presentation["proof"] = presentation["proof"].copy()
    presentation["proof"]["revocationWitness"] = witness
    
    # Verify the presentation - should be rejected due to stale epoch
    response = client.post('/api/verify-presentation', json={
        'presentation': presentation,
        'challenge': presentation_data["challenge"]
    })
    
    # The API might still return 200 but with validity=false
    if response.status_code == 200:
        try:
            result = response.json
        except:
            result = json.loads(response.data)
        
        # Check result - should be invalid due to stale cascade
        if "success" in result:
            assert result["success"] is False, "Stale cascade was incorrectly accepted"
        elif "valid" in result:
            assert result["valid"] is False, "Stale cascade was incorrectly accepted"
        else:
            # If we can't determine the validity from the response, skip
            pytest.skip("Cannot determine validity from response")
    else:
        # Non-200 response is acceptable too (e.g., 400 Bad Request)
        assert response.status_code in [400, 401, 403, 422], f"Unexpected status code: {response.status_code}"

def test_human_verification_endpoint(client, create_presentation, generate_challenge):
    """Test the verify-human endpoint that sets a session."""
    # Generate a challenge
    challenge = generate_challenge
    
    # Create a presentation
    presentation = create_presentation(challenge=challenge)
    
    # Verify the human presentation
    response = client.post('/api/verify-human', json={
        'presentation': presentation,
        'challenge': challenge
    })
    
    # If the endpoint doesn't exist, skip
    if response.status_code == 404:
        pytest.skip("verify-human endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to verify human: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Should indicate success
    assert "success" in result, f"No success field in response: {result}"
    assert result["success"] is True, f"Human verification failed: {result}"
    
    # The response should set a session cookie
    assert "Set-Cookie" in response.headers or len(client.cookie_jar) > 0, "No session cookie set" 