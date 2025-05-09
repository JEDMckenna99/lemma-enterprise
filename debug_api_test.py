"""
Debug script for API tests.
"""
import os
import sys
import json
from flask import Flask, current_app

# Add the package to the path
sys.path.insert(0, os.path.abspath('.'))

# Create a test app
from lemma import create_app

def main():
    """Run the debug script."""
    # Create a test app with test configuration
    test_app = create_app({
        'TESTING': True,
        'SKIP_AUTH_IN_TESTS': True,
        'STORAGE_DIR': '.lemma_test',
        'SECRET_KEY': 'test_secret_key',
        'ADMIN_USERNAME': 'test_admin',
        'ADMIN_PASSWORD': 'test_password',
        'API_KEY': 'test_api_key',
        'WTF_CSRF_ENABLED': False,
        'SESSION_COOKIE_SECURE': False,
        'SESSION_COOKIE_HTTPONLY': False,
        'SESSION_COOKIE_SAMESITE': None,
        'SKIP_API_KEY_CHECK': True
    })
    
    # Log configuration
    print(f"Test app configuration:")
    print(f"  TESTING: {test_app.config.get('TESTING')}")
    print(f"  SKIP_AUTH_IN_TESTS: {test_app.config.get('SKIP_AUTH_IN_TESTS')}")
    print(f"  API_KEY: {test_app.config.get('API_KEY')}")
    print(f"  WTF_CSRF_ENABLED: {test_app.config.get('WTF_CSRF_ENABLED')}")
    print(f"  SKIP_API_KEY_CHECK: {test_app.config.get('SKIP_API_KEY_CHECK')}")
    
    # Create a test client
    client = test_app.test_client()
    
    # Test the API
    with test_app.app_context():
        # Test without API key
        print("\nTesting /api/issue-credential without API key:")
        response = client.post('/api/issue-credential', 
                            json={'user_id': 'test_api_user'})
        print(f"  Status code: {response.status_code}")
        print(f"  Response: {response.data.decode()}")
        
        # Test with API key
        print("\nTesting /api/issue-credential with API key:")
        response = client.post('/api/issue-credential', 
                            json={'user_id': 'test_api_user'},
                            headers={'X-API-Key': 'test_api_key'})
        print(f"  Status code: {response.status_code}")
        print(f"  Response: {response.data.decode()}")
        
        # Test with missing user_id
        print("\nTesting /api/issue-credential with missing user_id:")
        response = client.post('/api/issue-credential', 
                            json={},
                            headers={'X-API-Key': 'test_api_key'})
        print(f"  Status code: {response.status_code}")
        print(f"  Response: {response.data.decode()}")

if __name__ == "__main__":
    main()
