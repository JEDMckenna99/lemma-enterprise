"""
Flow 10: Credential import / export

Tests the export and import of credentials, including password protection and
verification of exported credential data.
"""
import pytest
import json
import time
import base64
import os
from unittest.mock import patch, MagicMock

# Test ID
FLOW_ID = 10
FLOW_NAME = "Credential import / export"

@pytest.fixture
def sample_credential(generate_credential):
    """Generate a sample credential for testing."""
    credential_response = generate_credential()
    return credential_response['credential']

@pytest.fixture
def encrypt_decrypt_mock():
    """Mock the encryption and decryption functions."""
    with patch('lemma.utils.crypto.encrypt_credential') as mock_encrypt:
        # Mock encryption function
        def _encrypt(credential, password):
            # Just return a base64-encoded version of the credential for testing
            return base64.b64encode(json.dumps(credential).encode()).decode()
        
        mock_encrypt.side_effect = _encrypt
        
        # Also mock the decryption function
        with patch('lemma.utils.crypto.decrypt_credential') as mock_decrypt:
            # Mock decryption function
            def _decrypt(encrypted_data, password):
                # For testing, just decode the base64 and parse the JSON
                try:
                    if password == "wrong_password":
                        raise ValueError("Invalid password")
                    
                    return json.loads(base64.b64decode(encrypted_data).decode())
                except Exception as e:
                    raise ValueError(f"Decryption failed: {e}")
            
            mock_decrypt.side_effect = _decrypt
            
            yield {
                "encrypt": mock_encrypt,
                "decrypt": mock_decrypt
            }

def test_credential_export_endpoint(client, api_key, sample_credential):
    """Test the credential export endpoint."""
    # Call the export endpoint
    response = client.post(
        '/api/export-credential',
        json={
            'credential': sample_credential,
            'password': 'test_password'
        },
        headers={'X-API-Key': api_key}
    )
    
    # If endpoint doesn't exist, skip
    if response.status_code == 404:
        pytest.skip("Export endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to export credential: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result
    assert "success" in result, f"No success field in response: {result}"
    assert result["success"] is True, f"Export failed: {result}"
    assert "exported" in result, f"No exported field in response: {result}"
    assert isinstance(result["exported"], str), f"Exported data is not a string: {type(result['exported'])}"
    assert len(result["exported"]) > 0, "Exported data is empty"

def test_credential_export_contains_credential_info(client, api_key, sample_credential, encrypt_decrypt_mock):
    """Test that exported credentials contain the necessary credential information."""
    # Call the export endpoint
    response = client.post(
        '/api/export-credential',
        json={
            'credential': sample_credential,
            'password': 'test_password'
        },
        headers={'X-API-Key': api_key}
    )
    
    # If endpoint doesn't exist, skip
    if response.status_code == 404:
        pytest.skip("Export endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to export credential: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # We should have an exported field
    assert "exported" in result, f"No exported field in response: {result}"
    
    # Check that the encryption function was called
    encrypt_decrypt_mock["encrypt"].assert_called_once()
    
    # Try to decrypt the credential (this uses our mock)
    try:
        decrypted = encrypt_decrypt_mock["decrypt"].side_effect(result["exported"], "test_password")
        
        # Verify that the decrypted credential matches the original
        assert decrypted["id"] == sample_credential["id"], "Credential ID mismatch after export/decrypt"
        
        # Check for other essential fields
        if "credentialSubject" in sample_credential:
            assert "credentialSubject" in decrypted, "No credentialSubject after export/decrypt"
            assert decrypted["credentialSubject"]["isHuman"] == sample_credential["credentialSubject"]["isHuman"], \
                "isHuman value mismatch after export/decrypt"
    
    except Exception as e:
        assert False, f"Failed to decrypt exported credential: {e}"

def test_credential_import_endpoint(client, api_key, sample_credential, encrypt_decrypt_mock):
    """Test the credential import endpoint."""
    # First export a credential to get encrypted data
    exported_data = base64.b64encode(json.dumps(sample_credential).encode()).decode()
    
    # Call the import endpoint
    response = client.post(
        '/api/import-credential',
        json={
            'encrypted_credential': exported_data,
            'password': 'test_password'
        },
        headers={'X-API-Key': api_key}
    )
    
    # If endpoint doesn't exist, skip
    if response.status_code == 404:
        pytest.skip("Import endpoint not available")
    
    # Should succeed
    assert response.status_code == 200, f"Failed to import credential: {response.data}"
    
    # Parse the response
    try:
        result = response.json
    except:
        result = json.loads(response.data)
    
    # Check result
    assert "success" in result, f"No success field in response: {result}"
    assert result["success"] is True, f"Import failed: {result}"
    
    # Should have credential in response
    assert "credential" in result, f"No credential field in response: {result}"
    
    # Check the imported credential
    imported_credential = result["credential"]
    assert imported_credential["id"] == sample_credential["id"], "Credential ID mismatch after import"
    
    # Check that the decryption function was called
    encrypt_decrypt_mock["decrypt"].assert_called_once()

def test_import_with_invalid_password(client, api_key, sample_credential, encrypt_decrypt_mock):
    """Test import with an invalid password."""
    # First export a credential to get encrypted data
    exported_data = base64.b64encode(json.dumps(sample_credential).encode()).decode()
    
    # Call the import endpoint with wrong password
    response = client.post(
        '/api/import-credential',
        json={
            'encrypted_credential': exported_data,
            'password': 'wrong_password'
        },
        headers={'X-API-Key': api_key}
    )
    
    # If endpoint doesn't exist, skip
    if response.status_code == 404:
        pytest.skip("Import endpoint not available")
    
    # Should be rejected - may return 400 or 200 with error
    if response.status_code == 200:
        # Parse the response
        try:
            result = response.json
        except:
            result = json.loads(response.data)
        
        # Should indicate failure
        assert "success" in result, f"No success field in response: {result}"
        assert result["success"] is False, f"Import incorrectly succeeded with wrong password: {result}"
        
        # Should include error message about password
        assert "error" in result, f"No error field in response: {result}"
        assert "password" in result["error"].lower(), f"Error doesn't mention password: {result['error']}"
    else:
        # Should return 400 Bad Request
        assert response.status_code == 400, f"Expected 400 but got {response.status_code}"
    
    # Check that the decryption function was called
    encrypt_decrypt_mock["decrypt"].assert_called_once()

def test_roundtrip_export_import(client, api_key, sample_credential):
    """Test a full export-then-import roundtrip."""
    # First export the credential
    export_response = client.post(
        '/api/export-credential',
        json={
            'credential': sample_credential,
            'password': 'test_password'
        },
        headers={'X-API-Key': api_key}
    )
    
    # If endpoint doesn't exist, skip
    if export_response.status_code == 404:
        pytest.skip("Export endpoint not available")
    
    # Should succeed
    assert export_response.status_code == 200, f"Failed to export credential: {export_response.data}"
    
    # Parse the response
    try:
        export_result = export_response.json
    except:
        export_result = json.loads(export_response.data)
    
    # Get the exported data
    exported_data = export_result["exported"]
    
    # Now import the credential
    import_response = client.post(
        '/api/import-credential',
        json={
            'encrypted_credential': exported_data,
            'password': 'test_password'
        },
        headers={'X-API-Key': api_key}
    )
    
    # Should succeed
    assert import_response.status_code == 200, f"Failed to import credential: {import_response.data}"
    
    # Parse the response
    try:
        import_result = import_response.json
    except:
        import_result = json.loads(import_response.data)
    
    # Should have credential in response
    assert "credential" in import_result, f"No credential field in response: {import_result}"
    
    # Check the imported credential
    imported_credential = import_result["credential"]
    
    # Verify that the imported credential matches the original
    assert imported_credential["id"] == sample_credential["id"], "Credential ID mismatch after roundtrip"
    
    if "credentialSubject" in sample_credential:
        assert "credentialSubject" in imported_credential, "No credentialSubject after roundtrip"
        assert imported_credential["credentialSubject"]["id"] == sample_credential["credentialSubject"]["id"], \
            "Subject ID mismatch after roundtrip" 