#!/usr/bin/env python3
"""
WSGI entry point for the Lemma Enterprise application.
This is used by production servers like Gunicorn or uWSGI.
"""

from app import create_production_ready_app

# Create the production-ready Flask application with all routes
app = create_production_ready_app()

if __name__ == "__main__":
    app.run()
