#!/usr/bin/env python3
"""
WSGI entry point for the Lemma Enterprise application.
This is used by production servers like Gunicorn or uWSGI.
"""

from app import create_app

# Create the Flask application
app = create_app()

if __name__ == "__main__":
    app.run()
