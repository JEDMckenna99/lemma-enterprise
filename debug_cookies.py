#!/usr/bin/env python3
"""Debug session cookie configuration"""
from app import app

def debug_cookie_config():
    """Debug Flask session cookie configuration"""
    with app.app_context():
        print("Flask Session Cookie Configuration:")
        print(f"SESSION_COOKIE_SECURE: {app.config.get('SESSION_COOKIE_SECURE')}")
        print(f"SESSION_COOKIE_HTTPONLY: {app.config.get('SESSION_COOKIE_HTTPONLY')}")
        print(f"SESSION_COOKIE_SAMESITE: {app.config.get('SESSION_COOKIE_SAMESITE')}")
        print(f"PERMANENT_SESSION_LIFETIME: {app.config.get('PERMANENT_SESSION_LIFETIME')}")
        print(f"SECRET_KEY set: {bool(app.config.get('SECRET_KEY'))}")
        print(f"DEBUG: {app.debug}")
        print(f"TESTING: {app.config.get('TESTING')}")

if __name__ == "__main__":
    debug_cookie_config() 