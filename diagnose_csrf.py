"""
Diagnostic script to understand CSRF protection in Lemma Enterprise tests.
"""
import sys
import os
import flask
from flask import Flask, session, request
from flask_wtf.csrf import CSRFProtect, generate_csrf

# Create a simple Flask app for testing
app = Flask(__name__)
app.config['SECRET_KEY'] = 'test_secret_key'
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['CSRF_ENABLED'] = False
app.config['SKIP_AUTH_IN_TESTS'] = True

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Routes for testing
@app.route('/')
def index():
    return 'CSRF Test App'

@app.route('/protected', methods=['POST'])
def protected():
    return 'Protected Route Accessed'

@app.route('/status')
def status():
    # Return CSRF configuration status
    return {
        'WTF_CSRF_ENABLED': app.config.get('WTF_CSRF_ENABLED', True),
        'CSRF_ENABLED': app.config.get('CSRF_ENABLED', True),
        'TESTING': app.config.get('TESTING', False),
        'SKIP_AUTH_IN_TESTS': app.config.get('SKIP_AUTH_IN_TESTS', False),
        'csrf_exempt_views': len(csrf._exempt_views) if hasattr(csrf, '_exempt_views') else 'N/A',
        'csrf_exempt_blueprints': len(csrf._exempt_blueprints) if hasattr(csrf, '_exempt_blueprints') else 'N/A',
    }

# Create a test client
client = app.test_client()

def run_tests():
    """Run diagnostic tests"""
    print("Running CSRF diagnostic tests...")
    
    # Test 1: Check CSRF configuration
    print("\nTest 1: CSRF Configuration")
    response = client.get('/status')
    print(f"Status: {response.status_code}")
    print(f"Data: {response.json}")
    
    # Test 2: Try a POST request without CSRF token
    print("\nTest 2: POST without CSRF token")
    response = client.post('/protected')
    print(f"Status: {response.status_code}")
    print(f"Data: {response.data}")
    
    # Test 3: Try a POST request with CSRF token
    print("\nTest 3: POST with CSRF token")
    with client.session_transaction() as sess:
        csrf_token = generate_csrf()
        sess['csrf_token'] = csrf_token
    
    response = client.post('/protected', data={'csrf_token': csrf_token})
    print(f"Status: {response.status_code}")
    print(f"Data: {response.data}")
    
    # Test 4: Check if disabling CSRF works
    print("\nTest 4: Disabling CSRF protection")
    try:
        # Try to disable CSRF protection
        csrf._exempt_views = set()
        csrf._exempt_blueprints = set()
        
        # Try a POST request without CSRF token
        response = client.post('/protected')
        print(f"Status: {response.status_code}")
        print(f"Data: {response.data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    run_tests()
