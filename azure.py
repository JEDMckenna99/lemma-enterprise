"""
Azure-specific entry point for the Lemma Enterprise application
"""
import os
import sys

# Add the current directory to the path so Python can find the app module
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask app
from app import app

# This is what Azure App Service will look for
application = app

if __name__ == '__main__':
    app.run()
