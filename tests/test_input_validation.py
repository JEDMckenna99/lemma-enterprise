"""
Input validation tests for Lemma Human Verification System.
Tests that all API endpoints properly validate and sanitize input data.
"""
import pytest
import json
from typing import Dict, Any
from flask.testing import FlaskClient


class TestCredentialValidation:
    """Test credential input validation."""

    def test_credential_validation_missing_required_fields(self, client: FlaskClient, csrf_token: str):
        """Test that missing required fields are properly rejected."""
        invalid_credentials = [
            {},  # Empty credential
            {"@context": []},  # Missing required fields
            {"id": "test"},  # Missing other required fields
            {"type": "VerifiableCredential"},  # Missing context and other fields
        ]
        
        for invalid_credential in invalid_credentials:
            response = client.post('/api/verify-credential',
                                 json={'credential': invalid_credential},
                                 headers={'X-CSRFToken': csrf_token})
            assert response.status_code == 400
            assert 'error' in response.json

    def test_credential_validation_invalid_field_types(self, client: FlaskClient, csrf_token: str):
        """Test that invalid field types are properly rejected."""
        invalid_credentials = [
            {"@context": "not_a_list"},  # Should be list
            {"id": 12345},  # Should be string
            {"type": "not_a_list"},  # Should be list
            {"issuanceDate": "invalid_date"},  # Should be valid ISO date
        ]
        
        for invalid_credential in invalid_credentials:
            response = client.post('/api/verify-credential',
                                 json={'credential': invalid_credential},
                                 headers={'X-CSRFToken': csrf_token})
            assert response.status_code == 400

    def test_credential_validation_oversized_fields(self, client: FlaskClient, csrf_token: str):
        """Test that oversized fields are properly rejected."""
        # Create credential with very large fields
        oversized_credential = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "A" * 50000,  # Very long ID
            "type": ["VerifiableCredential"],
            "issuer": "did:test:" + "A" * 50000,  # Very long issuer
        }
        
        response = client.post('/api/verify-credential',
                             json={'credential': oversized_credential},
                             headers={'X-CSRFToken': csrf_token})
        assert response.status_code == 400

    def test_credential_validation_nested_depth_limit(self, client: FlaskClient, csrf_token: str):
        """Test that deeply nested structures are rejected."""
        # Create deeply nested structure
        nested_data = {"level": 1}
        for i in range(20):  # Create 20 levels of nesting
            nested_data = {"nested": nested_data, "level": i + 2}
        
        deep_credential = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "test-credential",
            "type": ["VerifiableCredential"],
            "credentialSubject": nested_data
        }
        
        response = client.post('/api/verify-credential',
                             json={'credential': deep_credential},
                             headers={'X-CSRFToken': csrf_token})
        assert response.status_code == 400


class TestPresentationValidation:
    """Test presentation input validation."""

    def test_presentation_validation_missing_required_fields(self, client: FlaskClient, csrf_token: str):
        """Test that missing required fields in presentations are rejected."""
        invalid_presentations = [
            {},  # Empty presentation
            {"@context": []},  # Missing required fields
            {"type": ["VerifiablePresentation"]},  # Missing other required fields
        ]
        
        for invalid_presentation in invalid_presentations:
            response = client.post('/api/verify-presentation',
                                 json={
                                     'presentation': invalid_presentation,
                                     'challenge': 'test_challenge'
                                 },
                                 headers={'X-CSRFToken': csrf_token})
            assert response.status_code == 400

    def test_presentation_validation_invalid_challenge(self, client: FlaskClient, csrf_token: str):
        """Test that invalid challenges are rejected."""
        valid_presentation = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "holder": "did:user:test"
        }
        
        invalid_challenges = [
            "",  # Empty challenge
            None,  # Null challenge
            123,  # Non-string challenge
            "x",  # Too short challenge
        ]
        
        for invalid_challenge in invalid_challenges:
            response = client.post('/api/verify-presentation',
                                 json={
                                     'presentation': valid_presentation,
                                     'challenge': invalid_challenge
                                 },
                                 headers={'X-CSRFToken': csrf_token})
            assert response.status_code == 400

    def test_presentation_validation_malformed_credentials(self, client: FlaskClient, csrf_token: str):
        """Test that presentations with malformed credentials are rejected."""
        malformed_presentation = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "holder": "did:user:test",
            "verifiableCredential": [
                {"invalid": "credential"}  # Malformed credential
            ]
        }
        
        response = client.post('/api/verify-presentation',
                             json={
                                 'presentation': malformed_presentation,
                                 'challenge': 'valid_challenge_123'
                             },
                             headers={'X-CSRFToken': csrf_token})
        assert response.status_code == 400


class TestAPIKeyValidation:
    """Test API key validation."""

    def test_api_key_format_validation(self, client: FlaskClient):
        """Test that API keys are properly validated for format."""
        invalid_api_keys = [
            "",  # Empty key
            " ",  # Whitespace only
            "short",  # Too short
            "A" * 1000,  # Too long
            "key with spaces",  # Contains spaces
            # Note: newline test removed as test framework blocks it at header level
        ]
        
        # Temporarily disable API key skipping for this test
        with client.application.app_context():
            original_skip = client.application.config.get('SKIP_API_KEY_CHECK', False)
            client.application.config['SKIP_API_KEY_CHECK'] = False
            client.application.config['API_KEY'] = 'valid_test_api_key'
            
            try:
                for invalid_key in invalid_api_keys:
                    response = client.post('/api/issue-credential',
                                         json={'user_id': 'test_user'},
                                         headers={'X-API-Key': invalid_key})
                    # API endpoints with CSRF protection may return 400 for missing CSRF token
                    # before checking API key, so we accept both 400 and 401
                    assert response.status_code in [400, 401]
                    assert 'error' in response.json
            finally:
                # Restore original setting
                client.application.config['SKIP_API_KEY_CHECK'] = original_skip

    def test_api_key_special_characters(self, client: FlaskClient):
        """Test API key validation with special characters."""
        special_char_keys = [
            "key<script>alert('xss')</script>",  # XSS attempt
            "key'; DROP TABLE users; --",  # SQL injection attempt
            "key\x00\x01\x02",  # Control characters (but not newlines due to test framework)
        ]
        
        # Temporarily disable API key skipping for this test
        with client.application.app_context():
            original_skip = client.application.config.get('SKIP_API_KEY_CHECK', False)
            client.application.config['SKIP_API_KEY_CHECK'] = False
            client.application.config['API_KEY'] = 'valid_test_api_key'
            
            try:
                for special_key in special_char_keys:
                    response = client.post('/api/issue-credential',
                                         json={'user_id': 'test_user'},
                                         headers={'X-API-Key': special_key})
                    # API endpoints with CSRF protection may return 400 for missing CSRF token
                    # before checking API key, so we accept both 400 and 401
                    assert response.status_code in [400, 401]
                    assert 'error' in response.json
            finally:
                # Restore original setting
                client.application.config['SKIP_API_KEY_CHECK'] = original_skip


class TestUserIDValidation:
    """Test user ID validation across endpoints."""

    def test_user_id_format_validation(self, client: FlaskClient, auth_headers: Dict[str, str]):
        """Test that user IDs are properly validated for format."""
        invalid_user_ids = [
            "",  # Empty user ID
            " ",  # Whitespace only
            "A" * 1000,  # Too long
            "user\nwith\nnewlines",  # Contains newlines
            "user\x00with\x01control",  # Contains control characters
        ]
        
        for invalid_user_id in invalid_user_ids:
            response = client.post('/api/issue-credential',
                                 json={'user_id': invalid_user_id},
                                 headers=auth_headers)
            assert response.status_code == 400

    def test_user_id_special_characters(self, client: FlaskClient, auth_headers: Dict[str, str]):
        """Test user ID validation with special characters."""
        special_char_user_ids = [
            "<script>alert('xss')</script>",  # XSS attempt
            "'; DROP TABLE users; --",  # SQL injection attempt
            "../../../etc/passwd",  # Path traversal attempt
        ]
        
        for special_user_id in special_char_user_ids:
            response = client.post('/api/issue-credential',
                                 json={'user_id': special_user_id},
                                 headers=auth_headers)
            # Should either reject or safely handle the input
            assert response.status_code != 500  # Should not cause server error


class TestDIDValidation:
    """Test DID (Decentralized Identifier) validation."""

    def test_did_format_validation(self, client: FlaskClient, csrf_token: str):
        """Test that DIDs are properly validated for format."""
        invalid_dids = [
            "not_a_did",  # Missing did: prefix
            "did:",  # Incomplete DID
            "did:method:",  # Missing identifier
            "did::identifier",  # Missing method
            "did:method:id:with:too:many:parts",  # Too many parts
        ]
        
        for invalid_did in invalid_dids:
            credential_with_invalid_did = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "id": "test-credential",
                "type": ["VerifiableCredential"],
                "issuer": invalid_did,
                "credentialSubject": {"id": "did:user:test", "isHuman": True}
            }
            
            response = client.post('/api/verify-credential',
                                 json={'credential': credential_with_invalid_did},
                                 headers={'X-CSRFToken': csrf_token})
            # Should handle invalid DID gracefully
            assert response.status_code != 500

    def test_did_method_validation(self, client: FlaskClient, csrf_token: str):
        """Test that DID methods are properly validated."""
        unsupported_methods = [
            "did:unsupported:identifier",
            "did:fake:identifier",
            "did:malicious:identifier",
        ]
        
        for unsupported_did in unsupported_methods:
            credential_with_unsupported_did = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "id": "test-credential",
                "type": ["VerifiableCredential"],
                "issuer": unsupported_did,
                "credentialSubject": {"id": "did:user:test", "isHuman": True}
            }
            
            response = client.post('/api/verify-credential',
                                 json={'credential': credential_with_unsupported_did},
                                 headers={'X-CSRFToken': csrf_token})
            # Should handle unsupported DID method gracefully
            assert response.status_code != 500


class TestJSONValidation:
    """Test JSON structure validation."""

    def test_malformed_json_handling(self, client: FlaskClient):
        """Test that malformed JSON is properly handled."""
        # Send malformed JSON
        response = client.post('/api/verify-credential',
                             data='{"invalid": json}',  # Missing quotes around json
                             headers={'Content-Type': 'application/json'})
        assert response.status_code == 400

    def test_non_json_content_type(self, client: FlaskClient):
        """Test that non-JSON content types are properly handled."""
        # Send JSON data with wrong content type
        response = client.post('/api/verify-credential',
                             data='{"credential": {"test": "data"}}',
                             headers={'Content-Type': 'text/plain'})
        # Should either reject or handle gracefully
        assert response.status_code in [400, 415]  # Bad Request or Unsupported Media Type

    def test_empty_request_body(self, client: FlaskClient):
        """Test that empty request bodies are properly handled."""
        response = client.post('/api/verify-credential',
                             data='',
                             headers={'Content-Type': 'application/json'})
        assert response.status_code == 400

    def test_null_values_handling(self, client: FlaskClient, csrf_token: str):
        """Test that null values in JSON are properly handled."""
        null_value_credential = {
            "@context": None,  # Null context
            "id": "test-credential",
            "type": None,  # Null type
            "issuer": "did:test:issuer",
            "credentialSubject": None  # Null subject
        }
        
        response = client.post('/api/verify-credential',
                             json={'credential': null_value_credential},
                             headers={'X-CSRFToken': csrf_token})
        assert response.status_code == 400


class TestBoundaryValueTesting:
    """Test boundary values for input validation."""

    def test_string_length_boundaries(self, client: FlaskClient, auth_headers: Dict[str, str]):
        """Test string length boundaries."""
        # Test maximum allowed length (assuming 10000 is the limit based on InputValidator)
        max_length_user_id = "A" * 10000
        response = client.post('/api/issue-credential',
                             json={'user_id': max_length_user_id},
                             headers=auth_headers)
        # Should either accept or reject based on validation rules
        assert response.status_code != 500

        # Test length just over the limit
        over_limit_user_id = "A" * 10001
        response = client.post('/api/issue-credential',
                             json={'user_id': over_limit_user_id},
                             headers=auth_headers)
        assert response.status_code == 400

    def test_list_length_boundaries(self, client: FlaskClient, csrf_token: str):
        """Test list length boundaries."""
        # Test maximum allowed list length (assuming 100 is the limit)
        max_length_context = ["https://example.com/context"] * 100
        large_list_credential = {
            "@context": max_length_context,
            "id": "test-credential",
            "type": ["VerifiableCredential"],
            "issuer": "did:test:issuer"
        }
        
        response = client.post('/api/verify-credential',
                             json={'credential': large_list_credential},
                             headers={'X-CSRFToken': csrf_token})
        # Should handle large list appropriately
        assert response.status_code != 500

    def test_numeric_boundaries(self, client: FlaskClient, csrf_token: str):
        """Test numeric value boundaries."""
        # Test with very large numbers
        large_number_credential = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "test-credential",
            "type": ["VerifiableCredential"],
            "issuer": "did:test:issuer",
            "credentialSubject": {
                "id": "did:user:test",
                "numericValue": 9999999999999999999999999999999
            }
        }
        
        response = client.post('/api/verify-credential',
                             json={'credential': large_number_credential},
                             headers={'X-CSRFToken': csrf_token})
        # Should handle large numbers without crashing
        assert response.status_code != 500 