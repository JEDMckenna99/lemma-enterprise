"""
Simple test to debug Flask/Werkzeug compatibility issues.
"""
import pytest
from flask import Flask

@pytest.fixture
def app():
    """Create a minimal test Flask application."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    @app.route('/')
    def index():
        return 'Hello, World!'
    
    return app

@pytest.fixture
def client(app):
    """Create a test client."""
    # The key is to NOT use any additional parameters here
    return app.test_client()

def test_index(client):
    """Test a simple route."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Hello, World!' in response.data

if __name__ == '__main__':
    pytest.main(['-xvs', __file__])
