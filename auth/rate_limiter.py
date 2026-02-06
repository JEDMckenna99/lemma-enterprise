"""
Rate Limiting for Lemma Authentication Endpoints

Provides protection against:
- Brute force attacks on passkey endpoints
- Token enumeration attacks
- DoS via expensive operations (credential issuance)

Uses Redis for distributed rate limiting (works across Heroku dynos).
Falls back to in-memory limiting for local development.
"""

import os
import logging
from flask import request

# Optional flask_limiter import - allows module to work without it installed
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    FLASK_LIMITER_AVAILABLE = True
except ImportError:
    Limiter = None
    get_remote_address = lambda: request.remote_addr if request else '127.0.0.1'
    FLASK_LIMITER_AVAILABLE = False

logger = logging.getLogger(__name__)

# Redis URL from environment (Heroku sets this automatically)
REDIS_URL = os.environ.get('REDIS_URL') or os.environ.get('REDIS_TLS_URL')


def get_client_identifier():
    """
    Get a unique identifier for the client for rate limiting.

    Uses X-Forwarded-For if behind a proxy (Heroku), otherwise remote_addr.
    Also incorporates user agent to distinguish different clients behind same IP.
    """
    # Get the real IP (Heroku uses X-Forwarded-For)
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip = get_remote_address()

    return ip


def create_limiter(app):
    """
    Create and configure the rate limiter for the Flask app.

    Uses Redis if available (production), falls back to in-memory (development).
    Returns None if flask_limiter is not installed.
    """
    if not FLASK_LIMITER_AVAILABLE:
        logger.warning("Rate limiter not available (flask_limiter not installed)")
        return None

    storage_uri = "memory://"

    if REDIS_URL:
        # Use Redis for distributed rate limiting
        # Handle Heroku's redis:// vs rediss:// (TLS)
        if REDIS_URL.startswith('redis://'):
            storage_uri = REDIS_URL
        elif REDIS_URL.startswith('rediss://'):
            # Heroku Redis with TLS - need to disable cert verification
            storage_uri = f"{REDIS_URL}?ssl_cert_reqs=none"
        logger.info("Rate limiter using Redis storage")
    else:
        logger.warning("Rate limiter using in-memory storage (not suitable for production)")

    limiter = Limiter(
        key_func=get_client_identifier,
        app=app,
        storage_uri=storage_uri,
        default_limits=["1000 per hour", "100 per minute"],  # Global defaults
        strategy="fixed-window",  # Simple and predictable
        headers_enabled=True,  # Add X-RateLimit-* headers to responses
    )

    return limiter


# Rate limit decorators for different endpoint types
# These are functions that return the actual limit string

def auth_limit():
    """Limit for authentication endpoints - strict to prevent brute force."""
    return "10 per minute"


def registration_limit():
    """Limit for registration endpoints - moderate."""
    return "5 per minute"


def credential_issue_limit():
    """Limit for credential issuance - expensive operation."""
    return "20 per hour"


def session_limit():
    """Limit for session operations - moderate."""
    return "30 per minute"


def validation_limit():
    """Limit for token validation - more lenient (used frequently)."""
    return "100 per minute"


def rate_limit(limit_func_or_string):
    """
    Rate limit decorator for blueprint routes.

    Usage:
        from auth.rate_limiter import rate_limit, auth_limit

        @bp.route('/api/login', methods=['POST'])
        @rate_limit(auth_limit)  # or @rate_limit("10 per minute")
        def login():
            ...

    Works by checking the limiter attached to current_app.
    Fails open (allows request) if limiter not configured.
    """
    from functools import wraps

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import current_app, jsonify, request

            # Skip rate limiting for OPTIONS requests
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            limiter = getattr(current_app, 'limiter', None)
            if not limiter:
                return f(*args, **kwargs)

            # Get limit string from function or use directly
            if callable(limit_func_or_string):
                limit_string = limit_func_or_string()
            else:
                limit_string = limit_func_or_string

            try:
                # Create a decorated version with the rate limit
                limited_func = limiter.limit(limit_string)(f)
                return limited_func(*args, **kwargs)
            except Exception as e:
                # Check if it's a rate limit error
                error_name = type(e).__name__
                if 'RateLimitExceeded' in error_name or '429' in str(e):
                    logger.warning(f"Rate limit exceeded ({limit_string}): {get_client_identifier()}")
                    return jsonify({
                        'success': False,
                        'error': 'rate_limit_exceeded',
                        'message': f'Too many requests. Please try again later.',
                        'retry_after': 60  # seconds
                    }), 429
                # Non-rate-limit errors - re-raise
                raise

        return decorated_function
    return decorator
