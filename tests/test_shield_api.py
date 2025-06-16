"""
Unit tests for Lemma Shield API v1.0
Tests the clean refactored API endpoints following the checklist requirements.
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock
from lemma import create_app


@pytest.fixture
def app():
    """Create a test app instance"""
    app = create_app({'TESTING': True, 'LEMMA_API_KEY': 'test_api_key'})
    return app


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Authentication headers for protected endpoints"""
    return {
        'Authorization': 'Bearer test_api_key',
        'Content-Type': 'application/json'
    }


class TestShieldIssuerEndpoints:
    """Test Shield (Issuer) endpoints"""
    
    def test_kyc_start_success(self, client, auth_headers):
        """Test successful KYC start request"""
        data = {
            'user_id': 'test_user_123',
            'callback_url': 'https://test.com/callback'
        }
        
        response = client.post('/api/v1/kyc/start', 
                             headers=auth_headers, 
                             json=data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'session_id' in response_data
        assert 'verification_url' in response_data
        assert 'expires_at' in response_data
        assert response_data['session_id'].startswith('vs_')
    
    def test_kyc_start_missing_user_id(self, client, auth_headers):
        """Test KYC start with missing user_id"""
        data = {'callback_url': 'https://test.com/callback'}
        
        response = client.post('/api/v1/kyc/start', 
                             headers=auth_headers, 
                             json=data)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert 'error' in response_data
        assert response_data['error']['code'] == 'INVALID_REQUEST'
    
    def test_kyc_start_unauthorized(self, client):
        """Test KYC start without API key"""
        data = {'user_id': 'test_user_123'}
        
        response = client.post('/api/v1/kyc/start', json=data)
        
        assert response.status_code == 401
        response_data = json.loads(response.data)
        assert response_data['error']['code'] == 'UNAUTHORIZED'
    
    @patch('lemma.routes.shield_api.get_credential_service')
    def test_vc_issue_success(self, mock_get_service, client, auth_headers):
        """Test successful VC issuance"""
        # Mock credential service
        mock_service = MagicMock()
        mock_credential = {
            '@context': ['https://www.w3.org/2018/credentials/v1'],
            'type': ['VerifiableCredential', 'HumanVerificationCredential'],
            'id': 'test_credential_123'
        }
        mock_service.issue_credential.return_value = mock_credential
        mock_get_service.return_value = mock_service
        
        data = {
            'user_id': 'test_user_123',
            'session_id': 'vs_test_session_123'
        }
        
        response = client.post('/api/v1/vc/issue', 
                             headers=auth_headers, 
                             json=data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'credential' in response_data
        assert 'issued_at' in response_data
        assert 'expires_at' in response_data
        assert response_data['credential']['id'] == 'test_credential_123'
    
    def test_wallet_script(self, client):
        """Test wallet script endpoint"""
        response = client.get('/api/v1/wallet/script.js')
        
        assert response.status_code == 200
        assert response.content_type == 'application/javascript; charset=utf-8'
        assert b'LemmaShieldWallet' in response.data
        assert b'saveCredential' in response.data


class TestCheckVerifierEndpoints:
    """Test Check (Verifier) endpoints"""
    
    def test_generate_challenge(self, client):
        """Test challenge generation"""
        response = client.get('/api/v1/challenge')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'challenge' in response_data
        assert 'expires_at' in response_data
        assert len(response_data['challenge']) == 64  # 32 bytes hex = 64 chars
    
    @patch('lemma.routes.shield_api.get_credential_service')
    def test_verify_presentation_success(self, mock_get_service, client):
        """Test successful presentation verification"""
        # First get a challenge
        challenge_response = client.get('/api/v1/challenge')
        challenge_data = json.loads(challenge_response.data)
        challenge = challenge_data['challenge']
        
        # Mock credential service
        mock_service = MagicMock()
        mock_service.verify_presentation.return_value = {'valid': True}
        mock_get_service.return_value = mock_service
        
        # Test verification
        presentation = {
            '@context': ['https://www.w3.org/2018/credentials/v1'],
            'type': ['VerifiablePresentation'],
            'verifiableCredential': [{}]
        }
        
        data = {
            'presentation': presentation,
            'challenge': challenge
        }
        
        response = client.post('/api/v1/verify', json=data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'verified' in response_data
        assert 'timestamp' in response_data
        assert response_data['verified'] == True
    
    def test_verify_presentation_invalid_challenge(self, client):
        """Test verification with invalid challenge"""
        presentation = {
            '@context': ['https://www.w3.org/2018/credentials/v1'],
            'type': ['VerifiablePresentation']
        }
        
        data = {
            'presentation': presentation,
            'challenge': 'invalid_challenge'
        }
        
        response = client.post('/api/v1/verify', json=data)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert response_data['error']['code'] == 'INVALID_REQUEST'
    
    def test_verify_presentation_missing_data(self, client):
        """Test verification with missing data"""
        response = client.post('/api/v1/verify', json={})
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert response_data['error']['code'] == 'INVALID_REQUEST'


class TestRevocationEndpoints:
    """Test Revocation endpoints"""
    
    def test_get_revocation_filter(self, client):
        """Test getting revocation filter"""
        issuer_id = 'did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK'
        
        response = client.get(f'/api/v1/revocation/filter/{issuer_id}')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'issuer_id' in response_data
        assert 'filter' in response_data
        assert 'signature' in response_data
        assert 'timestamp' in response_data
        assert 'expires_at' in response_data
        assert response_data['issuer_id'] == issuer_id
    
    def test_register_webhook(self, client, auth_headers):
        """Test webhook registration"""
        data = {
            'callback_url': 'https://test.com/webhook',
            'events': ['credential.revoked', 'credential.suspended']
        }
        
        response = client.post('/api/v1/revocation/webhook',
                             headers=auth_headers,
                             json=data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'webhook_id' in response_data
        assert 'callback_url' in response_data
        assert 'events' in response_data
        assert 'status' in response_data
        assert response_data['callback_url'] == data['callback_url']
        assert response_data['status'] == 'active'


class TestUsageBillingEndpoints:
    """Test Usage/Billing endpoints"""
    
    def test_log_usage_event(self, client, auth_headers):
        """Test usage event logging"""
        data = {
            'salted_did': 'a' * 64,  # 64 char hex string
            'timestamp': int(time.time())
        }
        
        response = client.post('/api/v1/usage/event',
                             headers=auth_headers,
                             json=data)
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'logged' in response_data
        assert 'timestamp' in response_data
        assert response_data['logged'] == True
    
    def test_log_usage_event_missing_salted_did(self, client, auth_headers):
        """Test usage logging with missing salted_did"""
        data = {'timestamp': int(time.time())}
        
        response = client.post('/api/v1/usage/event',
                             headers=auth_headers,
                             json=data)
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert response_data['error']['code'] == 'INVALID_REQUEST'


class TestMetaEndpoints:
    """Test Meta endpoints"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get('/api/v1/healthz')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'status' in response_data
        assert 'timestamp' in response_data
        assert 'version' in response_data
        assert response_data['status'] == 'healthy'
    
    def test_version_endpoint(self, client):
        """Test version endpoint"""
        response = client.get('/api/v1/version')
        
        assert response.status_code == 200
        response_data = json.loads(response.data)
        assert 'version' in response_data
        assert 'git_sha' in response_data
        assert 'api_version' in response_data
        assert 'service' in response_data
        assert response_data['api_version'] == 'v1'
        assert response_data['service'] == 'lemma-shield'


class TestErrorHandling:
    """Test error handling and response formats"""
    
    def test_error_response_format(self, client):
        """Test that all errors follow the standard format"""
        # Test with invalid JSON
        response = client.post('/api/v1/kyc/start',
                             headers={'Authorization': 'Bearer test_api_key'},
                             data='invalid json')
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert 'error' in response_data
        assert 'code' in response_data['error']
        assert 'message' in response_data['error']
    
    def test_unauthorized_endpoints(self, client):
        """Test that protected endpoints require authentication"""
        protected_endpoints = [
            ('/api/v1/kyc/start', 'POST'),
            ('/api/v1/vc/issue', 'POST'),
            ('/api/v1/revocation/webhook', 'POST'),
            ('/api/v1/usage/event', 'POST')
        ]
        
        for endpoint, method in protected_endpoints:
            if method == 'POST':
                response = client.post(endpoint, json={})
            else:
                response = client.get(endpoint)
            
            assert response.status_code == 401
            response_data = json.loads(response.data)
            assert response_data['error']['code'] == 'UNAUTHORIZED'


class TestApiVersioning:
    """Test API versioning and URI stability"""
    
    def test_v1_prefix_required(self, client):
        """Test that all endpoints require v1 prefix"""
        # Test that endpoints without v1 don't exist
        response = client.get('/api/challenge')  # Missing /v1
        assert response.status_code == 404
        
        # Test that v1 endpoints work
        response = client.get('/api/v1/challenge')
        assert response.status_code == 200
    
    def test_content_type_validation(self, client, auth_headers):
        """Test that JSON endpoints validate content type"""
        # Test with wrong content type
        headers = auth_headers.copy()
        headers['Content-Type'] = 'text/plain'
        
        response = client.post('/api/v1/kyc/start',
                             headers=headers,
                             data='test')
        
        # Should still handle gracefully
        assert response.status_code in [400, 415]


if __name__ == '__main__':
    pytest.main([__file__]) 