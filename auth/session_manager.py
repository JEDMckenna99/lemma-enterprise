"""
Session Manager for Lemma Authentication

Centralized session logic for:
- Session token generation and validation
- Unlock token generation and validation
- Session configuration

This module contains no Flask dependencies and can be used
from any part of the application.
"""

import os
import time
import hmac
import base64
import secrets
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================
# SESSION CONFIGURATION
# ============================================

SESSION_DURATION = 24 * 60 * 60  # 24 hours in seconds
UNLOCK_TOKEN_TTL = 5 * 60  # 5 minutes
SESSION_SECRET = os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production')

# Cookie names
SESSION_COOKIE_NAME = 'lemma_wallet_session'
CSRF_COOKIE_NAME = 'lemma_wallet_csrf'


# ============================================
# SESSION TOKEN FUNCTIONS
# ============================================

def generate_session_token(
    wallet_id: str,
    unlocked_at: int,
    profile_id: str = 'default',
    profile_name: str = 'Personal'
) -> str:
    """
    Generate a secure session token.

    Args:
        wallet_id: The user's wallet ID
        unlocked_at: Timestamp when wallet was unlocked (ms)
        profile_id: Active profile ID
        profile_name: Active profile display name

    Returns:
        Signed session token string
    """
    session_nonce = secrets.token_hex(16)
    profile_name_encoded = base64.urlsafe_b64encode(profile_name.encode()).decode()
    payload = f"{wallet_id}:{unlocked_at}:{int(time.time())}:{session_nonce}:{profile_id}:{profile_name_encoded}"
    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{signature}"


def validate_session_token(token: str) -> Optional[dict]:
    """
    Validate and decode a session token.

    Args:
        token: The session token string

    Returns:
        Dict with session data if valid, None if invalid/expired
    """
    try:
        parts = token.split(':')

        # Support both old format (5 parts) and new format with profiles (7 parts)
        if len(parts) == 5:
            # Legacy format without profile
            wallet_id, unlocked_at, created_at, session_nonce, signature = parts
            profile_id = 'default'
            profile_name = 'Personal'
            payload = f"{wallet_id}:{unlocked_at}:{created_at}:{session_nonce}"
        elif len(parts) == 7:
            # New format with profile
            wallet_id, unlocked_at, created_at, session_nonce, profile_id, profile_name_encoded, signature = parts
            try:
                profile_name = base64.urlsafe_b64decode(profile_name_encoded.encode()).decode()
            except Exception:
                profile_name = 'Personal'
            payload = f"{wallet_id}:{unlocked_at}:{created_at}:{session_nonce}:{profile_id}:{profile_name_encoded}"
        else:
            return None

        unlocked_at = int(unlocked_at)
        created_at = int(created_at)

        # Verify signature
        expected_sig = hmac.new(
            SESSION_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:32]

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Check expiration
        if time.time() - created_at > SESSION_DURATION:
            return None

        return {
            'wallet_id': wallet_id,
            'unlocked_at': unlocked_at,
            'created_at': created_at,
            'expires_at': created_at + SESSION_DURATION,
            'profile_id': profile_id,
            'profile_name': profile_name
        }
    except Exception:
        return None


# ============================================
# UNLOCK TOKEN FUNCTIONS
# ============================================

def generate_unlock_token(wallet_id: str, unlocked_at: int, expires_at: int) -> str:
    """
    Generate a short-lived unlock token after verified passkey authentication.

    This token is used to establish a session on third-party sites after
    the user has authenticated with their passkey on lemma.id.

    Args:
        wallet_id: The wallet identifier
        unlocked_at: When the wallet was unlocked (ms timestamp)
        expires_at: When the session expires (seconds timestamp)

    Returns:
        Signed unlock token string (valid for UNLOCK_TOKEN_TTL seconds)
    """
    issued_at = int(time.time())
    nonce = secrets.token_hex(8)
    payload = f"{wallet_id}:{unlocked_at}:{expires_at}:{issued_at}:{nonce}"
    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{signature}"


def validate_unlock_token(token: str) -> Optional[dict]:
    """
    Validate an unlock token and return decoded fields.

    Args:
        token: The unlock token string

    Returns:
        Dict with token data if valid, None if invalid/expired
    """
    try:
        wallet_id, unlocked_at, expires_at, issued_at, nonce, signature = token.split(':')
        unlocked_at = int(unlocked_at)
        expires_at = int(expires_at)
        issued_at = int(issued_at)

        payload = f"{wallet_id}:{unlocked_at}:{expires_at}:{issued_at}:{nonce}"
        expected_sig = hmac.new(
            SESSION_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:32]

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Check if token has expired
        if int(time.time()) - issued_at > UNLOCK_TOKEN_TTL:
            return None

        return {
            'wallet_id': wallet_id,
            'unlocked_at': unlocked_at,
            'expires_at': expires_at
        }
    except Exception:
        return None


# ============================================
# CSRF TOKEN FUNCTIONS
# ============================================

def generate_csrf_token() -> str:
    """Generate a CSRF token for session protection."""
    return secrets.token_urlsafe(32)


def validate_csrf(cookie_token: str, header_token: str) -> bool:
    """
    Validate CSRF token from cookie matches header.

    Args:
        cookie_token: CSRF token from cookie
        header_token: CSRF token from X-Lemma-CSRF header

    Returns:
        True if tokens match, False otherwise
    """
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)


# ============================================
# SESSION EXPIRY HELPERS
# ============================================

def get_session_expiry() -> int:
    """Get the expiry timestamp for a new session (24 hours from now)."""
    return int(time.time()) + SESSION_DURATION


def get_current_time_ms() -> int:
    """Get current time in milliseconds."""
    return int(time.time() * 1000)


def is_session_expired(expires_at: int) -> bool:
    """
    Check if a session has expired.

    Args:
        expires_at: Session expiry timestamp in seconds

    Returns:
        True if expired, False if still valid
    """
    return time.time() > expires_at


def get_time_remaining(expires_at: int) -> int:
    """
    Get remaining time for a session in seconds.

    Args:
        expires_at: Session expiry timestamp in seconds

    Returns:
        Seconds remaining (0 if expired)
    """
    remaining = expires_at - int(time.time())
    return max(0, remaining)
