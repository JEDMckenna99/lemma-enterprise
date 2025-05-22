#!/usr/bin/env python3
"""
Comprehensive tests for the Lemma wallet and OPRF integration.
Tests the full flow from wallet initialization to credential storage,
presentation creation, and OPRF-based revocation checking.
"""
import os
import json
import time
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import requests
from flask import Flask, session
from flask_testing import TestCase

# Import the application factory
from lemma import create_app
from lemma.core.credential_service import get_credential_service, init_credential_service
from lemma.utils.oprf_client import OPRFClient

# Mock JavaScript environment for wallet testing
class MockLocalStorage:
    """Mock implementation of browser localStorage for testing."""
    def __init__(self):
        self.store = {}
        
    def getItem(self, key):
        return self.store.get(key)
        
    def setItem(self, key, value):
        self.store[key] = value
        
    def removeItem(self, key):
        if key in self.store:
            del self.store[key]
            
    def clear(self):
        self.store = {}
        
    def keys(self):
        return list(self.store.keys())

class MockIndexedDB:
    """Mock implementation of browser IndexedDB for testing."""
    def __init__(self):
        self.databases = {}
        self.current_db = None
        
    def open(self, name, version):
        if name not in self.databases:
            self.databases[name] = {
                'stores': {},
                'version': version
            }
        self.current_db = name
        return MockDBRequest(self, name)
        
    def createObjectStore(self, store_name):
        if self.current_db:
            self.databases[self.current_db]['stores'][store_name] = {}
            
    def add(self, store_name, data, key=None):
        if self.current_db and store_name in self.databases[self.current_db]['stores']:
            if key is None and 'id' in data:
                key = data['id']
            self.databases[self.current_db]['stores'][store_name][key] = data
            
    def get(self, store_name, key):
        if self.current_db and store_name in self.databases[self.current_db]['stores']:
            return self.databases[self.current_db]['stores'][store_name].get(key)
            
    def getAll(self, store_name):
        if self.current_db and store_name in self.databases[self.current_db]['stores']:
            return list(self.databases[self.current_db]['stores'][store_name].values())
        return []
        
    def delete(self, store_name, key):
        if self.current_db and store_name in self.databases[self.current_db]['stores']:
            if key in self.databases[self.current_db]['stores'][store_name]:
                del self.databases[self.current_db]['stores'][store_name][key]

class MockDBRequest:
    """Mock implementation of IndexedDB request for testing."""
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.result = None
        self.error = None
        self.transaction = MockTransaction(db)
        
    def addEventListener(self, event, callback):
        if event == 'success':
            self.result = self.db
            callback({'target': {'result': self.db}})
        elif event == 'error':
            if self.error:
                callback({'target': {'error': self.error}})
                
    def set_onsuccess(self, callback):
        self.onsuccess = callback
        self.result = self.db
        callback({'target': {'result': self.db}})
        
    def set_onerror(self, callback):
        self.onerror = callback
        
class MockTransaction:
    """Mock implementation of IndexedDB transaction for testing."""
    def __init__(self, db):
        self.db = db
        self.objectStores = {}
        
    def objectStore(self, name):
        if name not in self.objectStores:
            self.objectStores[name] = MockObjectStore(self.db, name)
        return self.objectStores[name]
        
class MockObjectStore:
    """Mock implementation of IndexedDB object store for testing."""
    def __init__(self, db, name):
        self.db = db
        self.name = name
        
    def add(self, data, key=None):
        request = MockDBRequest(self.db, self.name)
        self.db.add(self.name, data, key)
        return request
        
    def get(self, key):
        request = MockDBRequest(self.db, self.name)
        request.result = self.db.get(self.name, key)
        return request
        
    def getAll(self):
        request = MockDBRequest(self.db, self.name)
        request.result = self.db.getAll(self.name)
        return request
        
    def delete(self, key):
        request = MockDBRequest(self.db, self.name)
        self.db.delete(self.name, key)
        return request

class TestWalletOPRFIntegration(TestCase):
    """Test the integration between the Lemma wallet and OPRF service."""
    
    def create_app(self):
        """Create and configure a Flask app for testing."""
        app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'test_secret_key',
            'SKIP_AUTH_IN_TESTS': True,
            'STORAGE_DIR': tempfile.mkdtemp(),
            'OPRF_SERVICE_URL': os.environ.get('OPRF_SERVICE_URL', 'http://localhost:8080'),
            'OPRF_SERVICE_INTERNAL': False
        })
        
        # Initialize the credential service
        with app.app_context():
            init_credential_service(app)
            
        return app
        
    def setUp(self):
        """Set up test environment before each test."""
        # Create mock browser environment
        self.localStorage = MockLocalStorage()
        self.indexedDB = MockIndexedDB()
        
        # Create a test user ID
        self.user_id = f"test_user_{int(time.time())}"
        
        # Create a test credential
        with self.app.app_context():
            self.credential_service = get_credential_service()
            self.credential = self.credential_service.issue_credential(self.user_id)
            
    def tearDown(self):
        """Clean up after each test."""
        # Clean up storage
        self.localStorage.clear()
        
    def test_wallet_initialization(self):
        """Test that the wallet initializes correctly."""
        with patch('lemma.utils.wallet.LemmaWallet') as MockWallet:
            instance = MockWallet.return_value
            instance.init.return_value = instance
            
            # Call the wallet initialization
            from lemma.utils.wallet import init_wallet
            wallet = init_wallet()
            
            # Check that the wallet was initialized
            self.assertIsNotNone(wallet)
            instance.init.assert_called_once()
            
    def test_credential_storage_in_wallet(self):
        """Test storing a credential in the wallet."""
        # Mock the wallet
        with patch('lemma.utils.wallet.LemmaWallet') as MockWallet:
            instance = MockWallet.return_value
            instance.init.return_value = instance
            instance.storeCredential.return_value = self.user_id
            
            # Call the wallet initialization
            from lemma.utils.wallet import init_wallet
            wallet = init_wallet()
            
            # Store a credential
            result = wallet.storeCredential(self.credential, self.user_id)
            
            # Check that the credential was stored
            self.assertEqual(result, self.user_id)
            instance.storeCredential.assert_called_once()
            
    def test_presentation_creation(self):
        """Test creating a presentation from a credential."""
        # Mock the wallet
        with patch('lemma.utils.wallet.LemmaWallet') as MockWallet:
            instance = MockWallet.return_value
            instance.init.return_value = instance
            
            # Set up the mock to return a presentation
            challenge = "test_challenge"
            mock_presentation = {
                "type": ["VerifiablePresentation"],
                "verifiableCredential": [self.credential],
                "proof": {
                    "type": "Ed25519Signature2020",
                    "challenge": challenge
                }
            }
            instance.createPresentation.return_value = mock_presentation
            
            # Call the wallet initialization
            from lemma.utils.wallet import init_wallet
            wallet = init_wallet()
            
            # Create a presentation
            presentation = wallet.createPresentation(self.credential, challenge)
            
            # Check that the presentation was created
            self.assertEqual(presentation, mock_presentation)
            instance.createPresentation.assert_called_once_with(self.credential, challenge)
            
    @patch('requests.post')
    def test_oprf_evaluation(self, mock_post):
        """Test OPRF evaluation for revocation checking."""
        # Mock the OPRF service response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "evaluated": "mocked_evaluated_value",
            "key_id": "test_key_id",
            "epoch": "2025-05-22"
        }
        mock_post.return_value = mock_response
        
        # Create OPRF client
        oprf_client = OPRFClient(
            service_url=os.environ.get('OPRF_SERVICE_URL', 'http://localhost:8080')
        )
        
        # Test blind evaluation
        blinded_data = oprf_client.blind("test_data")
        self.assertIsNotNone(blinded_data)
        
        # Test evaluation
        result = oprf_client.evaluate(blinded_data)
        self.assertEqual(result["evaluated"], "mocked_evaluated_value")
        self.assertEqual(result["key_id"], "test_key_id")
        
        # Verify the request
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["blinded"], blinded_data)
        
    @patch('requests.get')
    def test_cascade_retrieval(self, mock_get):
        """Test retrieving the revocation cascade."""
        # Mock the cascade response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "epoch": "2025-05-22",
            "cascade": {
                "levels": [
                    {"size": 1000, "bits": "base64_encoded_bits"},
                    {"size": 10000, "bits": "base64_encoded_bits"}
                ],
                "metadata": {
                    "total_revoked": 100,
                    "false_positive_rate": 0.001
                }
            }
        }
        mock_get.return_value = mock_response
        
        # Create OPRF client
        oprf_client = OPRFClient(
            service_url=os.environ.get('OPRF_SERVICE_URL', 'http://localhost:8080')
        )
        
        # Test cascade retrieval
        cascade = oprf_client.get_cascade()
        self.assertEqual(cascade["epoch"], "2025-05-22")
        self.assertEqual(len(cascade["cascade"]["levels"]), 2)
        
        # Verify the request
        mock_get.assert_called_once()
        
    def test_revocation_check_with_cascade(self):
        """Test checking revocation status using a cascade."""
        # Mock the OPRF client
        with patch('lemma.utils.oprf_client.OPRFClient') as MockOPRFClient:
            instance = MockOPRFClient.return_value
            
            # Set up the mock to return an evaluation
            instance.blind.return_value = "blinded_data"
            instance.evaluate.return_value = {
                "evaluated": "evaluated_data",
                "key_id": "test_key_id",
                "epoch": "2025-05-22"
            }
            
            # Set up the mock cascade
            mock_cascade = {
                "epoch": "2025-05-22",
                "cascade": {
                    "levels": [
                        {"size": 1000, "bits": "base64_encoded_bits"},
                        {"size": 10000, "bits": "base64_encoded_bits"}
                    ],
                    "metadata": {
                        "total_revoked": 100,
                        "false_positive_rate": 0.001
                    }
                }
            }
            instance.get_cascade.return_value = mock_cascade
            
            # Mock the check_in_cascade method to return False (not revoked)
            instance.check_in_cascade.return_value = False
            
            # Create OPRF client
            from lemma.utils.oprf_client import OPRFClient
            oprf_client = OPRFClient()
            
            # Test revocation check
            credential_id = self.credential["id"]
            is_revoked = oprf_client.check_revocation(credential_id)
            
            # Check that the credential is not revoked
            self.assertFalse(is_revoked)
            instance.blind.assert_called_once()
            instance.evaluate.assert_called_once()
            instance.get_cascade.assert_called_once()
            instance.check_in_cascade.assert_called_once()
            
    def test_end_to_end_verification_flow(self):
        """Test the end-to-end verification flow with wallet and OPRF."""
        # This test simulates the full flow from credential issuance to verification
        
        # 1. Issue a credential
        with self.app.app_context():
            credential = self.credential_service.issue_credential(self.user_id)
            self.assertIsNotNone(credential)
            self.assertEqual(credential["credentialSubject"]["id"], f"did:user:{self.user_id}")
            
        # 2. Store the credential in the wallet (mock)
        with patch('lemma.utils.wallet.LemmaWallet') as MockWallet:
            wallet_instance = MockWallet.return_value
            wallet_instance.init.return_value = wallet_instance
            wallet_instance.storeCredential.return_value = self.user_id
            
            # Mock presentation creation
            challenge = "test_challenge"
            mock_presentation = {
                "type": ["VerifiablePresentation"],
                "verifiableCredential": [credential],
                "proof": {
                    "type": "Ed25519Signature2020",
                    "challenge": challenge,
                    "proofPurpose": "authentication"
                }
            }
            wallet_instance.createPresentation.return_value = mock_presentation
            
            # Initialize wallet
            from lemma.utils.wallet import init_wallet
            wallet = init_wallet()
            
            # Store credential
            wallet.storeCredential(credential, self.user_id)
            
            # 3. Create a presentation
            presentation = wallet.createPresentation(credential, challenge)
            self.assertIsNotNone(presentation)
            
            # 4. Verify the presentation
            with self.app.app_context():
                # Mock OPRF client for revocation check
                with patch('lemma.core.credential_service.OPRFClient') as MockOPRFClient:
                    oprf_instance = MockOPRFClient.return_value
                    oprf_instance.check_revocation.return_value = False  # Not revoked
                    
                    # Verify the presentation
                    result = self.credential_service.verify_presentation(presentation)
                    self.assertTrue(result["valid"])
                    self.assertEqual(result["credentials"][0]["valid"], True)
                    
                    # Check that revocation was checked
                    oprf_instance.check_revocation.assert_called_once()
                    
if __name__ == '__main__':
    unittest.main()