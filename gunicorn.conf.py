"""
Gunicorn configuration file for Azure App Service
"""
import os
import sys

# Add the current directory to the path so Python can find the app module
sys.path.insert(0, os.path.dirname(__file__))

# Gunicorn config variables
bind = "0.0.0.0:8000"
workers = 2
timeout = 600
