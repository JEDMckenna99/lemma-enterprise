"""
Helper functions for testing the Lemma Enterprise application.
"""
import os
import shutil
from flask import Flask
from flask.testing import FlaskClient

# Create a patched Flask test client to handle compatibility issues
class PatchedFlaskClient(FlaskClient):
    """A patched version of Flask's test client that works with newer Werkzeug versions."""
    
    def open(self, *args, **kwargs):
        # Remove problematic parameters that might be automatically added
        if 'as_tuple' in kwargs:
            del kwargs['as_tuple']
        
        # Call the parent open method with cleaned arguments
        return super().open(*args, **kwargs)

def create_test_app():
    """Create a test Flask application with the patched client."""
    app = Flask(__name__)
    app.config.update({
        'TESTING': True,
        'SKIP_AUTH_IN_TESTS': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_secret_key',
        'ADMIN_USERNAME': 'test_admin',
        'ADMIN_PASSWORD': 'test_password',
        'API_KEY': 'test_api_key'
    })
    
    # Use the patched test client
    app.test_client_class = PatchedFlaskClient
    
    return app

def clean_test_directory(directory):
    """Clean up a test directory."""
    if os.path.exists(directory):
        shutil.rmtree(directory)
