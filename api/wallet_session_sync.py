"""
Wallet Session Sync API - PRIVACY-HARDENED

Enables the "One Passkey Per Day" experience by syncing wallet sessions
across sites via secure cookies.

FLOW:
1. User unlocks wallet on lemma.id → Session cookie set (24hr)
2. User visits third-party site → SDK calls /api/wallet/session-sync
3. Cookie validated → Session returned (stateless JWT validation)
4. SDK stores locally → All verifications are local (0 network calls)

PRIVACY MODEL:
- STATELESS: Session validation uses signed JWT, no database queries
- NO TRACKING: We don't log which sites users visit
- NO REFERRER: All responses include Referrer-Policy: no-referrer
- NO ANALYTICS: No tracking pixels, no third-party scripts
- MINIMAL DATA: Only wallet_id and timestamps in session token

What lemma.id CAN see:
- A session cookie exists (not which site requested it)
- When sessions are created/expire

What lemma.id CANNOT see:
- Which sites users visit
- User activities on any site
- User credentials (encrypted on device)
"""

from flask import Blueprint, request, jsonify, make_response
import time
import hashlib
import hmac
import os
import json
import secrets
from urllib.parse import urlparse

wallet_session_sync_bp = Blueprint('wallet_session_sync', __name__)

# Session configuration
SESSION_COOKIE_NAME = 'lemma_wallet_session'
SESSION_DURATION = 24 * 60 * 60  # 24 hours in seconds
SESSION_SECRET = os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production')
CSRF_COOKIE_NAME = 'lemma_wallet_csrf'

_ALLOWED_ORIGINS = {
    origin.strip().lower()
    for origin in os.environ.get('LEMMA_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
}
_ALLOWED_ORIGIN_SUFFIXES = [
    suffix.strip().lower()
    for suffix in os.environ.get('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '').split(',')
    if suffix.strip()
]
_ALLOW_DEV_ORIGINS = os.environ.get('LEMMA_ALLOW_DEV_ORIGINS', '1') != '0'


def _parse_origin(origin: str) -> str | None:
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc:
            return None
        return origin.lower()
    except Exception:
        return None


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    normalized = _parse_origin(origin)
    if not normalized:
        return False
    if normalized in _ALLOWED_ORIGINS:
        return True
    hostname = urlparse(normalized).hostname or ''
    if hostname:
        for suffix in _ALLOWED_ORIGIN_SUFFIXES:
            if hostname.endswith(suffix.lstrip('.')):
                return True
    if _ALLOW_DEV_ORIGINS and hostname in {'localhost', '127.0.0.1'}:
        return True
    return False


def _cors_headers(origin: str | None) -> dict:
    """
    Generate CORS headers with privacy protections.
    Includes Referrer-Policy to prevent site tracking.
    """
    if not _origin_allowed(origin):
        return {
            # Privacy headers even on error responses
            'Referrer-Policy': 'no-referrer',
        }
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Lemma-CSRF',
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin',
        # PRIVACY: Prevent referrer leakage
        'Referrer-Policy': 'no-referrer',
    }


def _validate_csrf() -> bool:
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get('X-Lemma-CSRF')
    if not csrf_cookie or not csrf_header:
        return False
    return secrets.compare_digest(csrf_cookie, csrf_header)


def generate_session_token(wallet_id: str, unlocked_at: int) -> str:
    """Generate a secure session token for the cookie."""
    session_nonce = secrets.token_hex(16)
    payload = f"{wallet_id}:{unlocked_at}:{int(time.time())}:{session_nonce}"
    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{signature}"


def validate_session_token(token: str) -> dict:
    """Validate and decode a session token."""
    try:
        parts = token.split(':')
        if len(parts) != 5:
            return None
        
        wallet_id, unlocked_at, created_at, session_nonce, signature = parts
        unlocked_at = int(unlocked_at)
        created_at = int(created_at)
        
        # Verify signature
        payload = f"{wallet_id}:{unlocked_at}:{created_at}:{session_nonce}"
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
            'expires_at': created_at + SESSION_DURATION
        }
    except Exception:
        # PRIVACY: Don't log validation errors (could leak timing info)
        return None


@wallet_session_sync_bp.route('/api/wallet/session-sync', methods=['POST', 'OPTIONS'])
def session_sync():
    """
    Sync wallet session across sites.
    
    Called by the bridge iframe to get session state when storage is partitioned.
    Uses httpOnly cookie for security.
    
    Returns:
        - session: Session state (unlocked_at, expires_at, wallet_id)
        - credentials: User's credentials for the requesting site
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403
    
    # Get session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_token:
        response = jsonify({
            'success': False,
            'error': 'no_session',
            'message': 'No wallet session. User needs to unlock wallet on lemma.id',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        })
        response.headers.update(_cors_headers(origin))
        return response, 401
    
    # Validate session
    session_data = validate_session_token(session_token)
    
    if not session_data:
        response = jsonify({
            'success': False,
            'error': 'session_expired',
            'message': 'Wallet session expired. User needs to unlock again.',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        })
        response.headers.update(_cors_headers(origin))
        return response, 401

    # NOTE: No CSRF check for session-sync (read-only operation)
    
    # PRIVACY: Return session only, no credentials
    # Credentials are stored locally in each site's IndexedDB
    response_data = {
        'success': True,
        'session': {
            'valid': True,
            'wallet_id': session_data['wallet_id'],
            'unlocked_at': session_data['unlocked_at'],
            'expires_at': session_data['expires_at'],
            'time_remaining': session_data['expires_at'] - int(time.time())
        },
        'credentials': [],  # Credentials stored locally only
        'synced_at': int(time.time() * 1000)
    }
    
    response = jsonify(response_data)
    response.headers.update(_cors_headers(origin))
    return response


@wallet_session_sync_bp.route('/api/wallet/set-session', methods=['POST', 'OPTIONS'])
def set_session():
    """
    Set wallet session cookie after successful passkey unlock.
    Called from any site after wallet unlock (cross-origin supported).

    Request body:
        - wallet_id: The user's wallet ID
        - unlocked_at: Timestamp of unlock
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response

    origin = request.headers.get('Origin')
    
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    unlocked_at = data.get('unlocked_at', int(time.time() * 1000))

    if not wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_id required'})
        response.headers.update(_cors_headers(origin))
        return response, 400

    # Generate session token + CSRF token
    token = generate_session_token(wallet_id, unlocked_at)
    csrf_token = secrets.token_urlsafe(32)

    # Create response with cookie
    response = jsonify({
        'success': True,
        'session_set': True,
        'expires_at': int(time.time()) + SESSION_DURATION
    })
    
    # Add CORS headers
    response.headers.update(_cors_headers(origin))

    # Set secure cookie
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_DURATION,
        httponly=True,
        secure=True,  # HTTPS only
        samesite='None',  # Allow cross-site requests
        path='/'
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=SESSION_DURATION,
        httponly=False,
        secure=True,
        samesite='None',
        path='/'
    )

    return response


@wallet_session_sync_bp.route('/api/wallet/clear-session', methods=['POST'])
def clear_session():
    """Clear wallet session cookie (logout)."""
    response = jsonify({'success': True, 'session_cleared': True})
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')
    response.delete_cookie(CSRF_COOKIE_NAME, path='/')
    return response


# ============================================================
# PRIVACY MODEL
# ============================================================
# - Session (unlock status): Server cookie (stateless JWT)
# - Credentials: LOCAL ONLY in each site's IndexedDB
# - Server stores NO credentials, NO user activity, NO site visits
# ============================================================
