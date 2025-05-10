"""
Simple Flask application for Azure App Service
This file is specifically named 'application.py' as Azure App Service looks for this file by default.
"""
import os
import sys
from flask import Flask, jsonify

# Create a simple Flask app for testing
app = Flask(__name__)

@app.route('/')
def index():
    """Return a simple JSON response to verify the app is working"""
    return jsonify({
        'status': 'success',
        'message': 'Lemma Enterprise API is running',
        'environment': os.environ.get('FLASK_ENV', 'production'),
        'python_path': sys.path,
        'current_directory': os.getcwd()
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

# Try to import the main app
try:
    from app import app as main_app
    # If successful, replace our test app with the real app
    app = main_app
    print("Successfully imported the main Lemma application")
except Exception as e:
    print(f"Error importing main application: {e}")
    print("Using diagnostic application instead")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
