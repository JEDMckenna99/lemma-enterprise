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

SESSION_DURATION = 10 * 60 * 60  # 10 hours in seconds (aligned with client daily-unlock bundle)
UNLOCK_TOKEN_TTL = 5 * 60  # 5 minutes

_session_secret = os.environ.get('SESSION_SECRET')
if not _session_secret:
    if os.environ.get('FLASK_ENV') == 'development' or os.environ.get('LEMMA_DEV_MODE') == '1':
        _session_secret = 'dev-only-' + secrets.token_hex(16)
        logger.warning("SESSION_SECRET not set, using random dev secret (sessions won't survive restarts)")
    else:
        raise RuntimeError(
            "SESSION_SECRET environment variable is required in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
SESSION_SECRET = _session_secret

# Cookie names
SESSION_COOKIE_NAME = 'lemma_wallet_session'
CSRF_COOKIE_NAME = 'lemma_wallet_csrf'

# Session revocation key prefix
_REVOKED_SESSION_PREFIX = 'revoked_session:'
_REVOKED_WALLET_PREFIX = 'revoked_wallet_sessions:'


def _session_revocation_degraded_mode() -> str:
    """
    Behavior when revocation backend is unavailable.
    - fail_open (default): allow sessions to continue until expiry
    - fail_closed: reject sessions when revocation cannot be checked
    """
    secure_mode = (os.getenv("LEMMA_WALLET_SECURE_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
    default_mode = "fail_closed" if secure_mode else "fail_open"
    mode = (os.getenv("LEMMA_SESSION_REVOCATION_DEGRADED_MODE") or default_mode).strip().lower()
    if mode not in {"fail_open", "fail_closed"}:
        return "fail_open"
    return mode


# ============================================
# SESSION REVOCATION (server-side blacklist)
# ============================================

def revoke_session(token: str) -> bool:
    """
    Revoke a specific session token server-side.

    Adds the token's signature to a Redis-backed blacklist with TTL
    equal to the session's remaining lifetime. After expiry, the entry
    auto-deletes (the session would be invalid anyway).

    Args:
        token: The session token string to revoke

    Returns:
        True if revoked successfully
    """
    from auth import redis_store

    try:
        parts = token.split(':')
        if len(parts) not in (5, 7):
            return False

        signature = parts[-1]
        # Parse created_at to compute remaining TTL
        created_at = int(parts[2])
        remaining = max(0, (created_at + SESSION_DURATION) - int(time.time()))

        if remaining <= 0:
            return True  # Already expired, nothing to revoke

        redis_store.store(
            f"{_REVOKED_SESSION_PREFIX}{signature}",
            {'revoked_at': int(time.time())},
            ttl_seconds=remaining
        )
        logger.info(f"Session revoked (sig={signature[:8]}..., ttl={remaining}s)")
        return True
    except Exception as e:
        logger.error(f"Failed to revoke session: {e}")
        return False


def revoke_wallet_sessions(wallet_id: str) -> bool:
    """
    Revoke ALL sessions for a wallet (used on logout/lock).

    Stores the wallet_id in a blacklist. validate_session_token checks
    this list and rejects any session for this wallet issued before
    the revocation timestamp.

    Args:
        wallet_id: The wallet whose sessions should be revoked

    Returns:
        True if revoked successfully
    """
    from auth import redis_store

    try:
        redis_store.store(
            f"{_REVOKED_WALLET_PREFIX}{wallet_id}",
            {'revoked_at': int(time.time())},
            ttl_seconds=SESSION_DURATION
        )
        logger.info(f"All sessions revoked for wallet {wallet_id[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to revoke wallet sessions: {e}")
        return False


def _is_session_revoked(token: str, wallet_id: str, created_at: int) -> bool:
    """Check if a session has been revoked server-side."""
    from auth import redis_store

    try:
        # Check 1: specific session signature blacklisted
        parts = token.split(':')
        signature = parts[-1]
        if redis_store.get(f"{_REVOKED_SESSION_PREFIX}{signature}"):
            return True

        # Check 2: all wallet sessions revoked after this session was created
        wallet_revocation = redis_store.get(f"{_REVOKED_WALLET_PREFIX}{wallet_id}")
        if wallet_revocation:
            revoked_at = wallet_revocation.get('revoked_at', 0)
            if created_at <= revoked_at:
                return True

        return False
    except Exception as e:
        mode = _session_revocation_degraded_mode()
        logger.warning(
            "Session revocation check degraded (mode=%s, wallet=%s): %s",
            mode,
            wallet_id[:8] if wallet_id else "unknown",
            e,
        )
        if mode == "fail_closed":
            return True
        # fail_open: avoid cascading auth failures during Redis incidents
        return False


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

        # Check server-side revocation (Redis-backed blacklist)
        if _is_session_revoked(token, wallet_id, created_at):
            logger.info(f"Session rejected: revoked server-side (wallet={wallet_id[:8]}...)")
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
