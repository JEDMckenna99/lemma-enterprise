#!/usr/bin/env python3
"""
Minimal WSGI entry point for debugging
"""

from minimal_app import app

if __name__ == "__main__":
    app.run() 