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
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

wallet_session_sync_bp = Blueprint('wallet_session_sync', __name__)

# Session configuration
SESSION_COOKIE_NAME = 'lemma_wallet_session'
SESSION_DURATION = 24 * 60 * 60  # 24 hours in seconds
SESSION_SECRET = os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production')
CSRF_COOKIE_NAME = 'lemma_wallet_csrf'
UNLOCK_TOKEN_TTL = 5 * 60  # 5 minutes

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


def generate_session_token(wallet_id: str, unlocked_at: int, profile_id: str = 'default', profile_name: str = 'Personal') -> str:
    """Generate a secure session token for the cookie.
    
    Args:
        wallet_id: The user's wallet ID
        unlocked_at: Timestamp when wallet was unlocked
        profile_id: Active profile ID (default: 'default')
        profile_name: Active profile display name (default: 'Personal')
    """
    session_nonce = secrets.token_hex(16)
    # Include profile info in payload (URL-safe encoding for profile name)
    import base64
    profile_name_encoded = base64.urlsafe_b64encode(profile_name.encode()).decode()
    payload = f"{wallet_id}:{unlocked_at}:{int(time.time())}:{session_nonce}:{profile_id}:{profile_name_encoded}"
    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{signature}"


def generate_unlock_token(wallet_id: str, unlocked_at: int, expires_at: int) -> str:
    """Generate a short-lived unlock token after verified passkey authentication."""
    issued_at = int(time.time())
    nonce = secrets.token_hex(8)
    payload = f"{wallet_id}:{unlocked_at}:{expires_at}:{issued_at}:{nonce}"
    signature = hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}:{signature}"


def validate_unlock_token(token: str) -> dict | None:
    """Validate an unlock token and return decoded fields."""
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
        if int(time.time()) - issued_at > UNLOCK_TOKEN_TTL:
            return None
        return {
            'wallet_id': wallet_id,
            'unlocked_at': unlocked_at,
            'expires_at': expires_at
        }
    except Exception:
        return None


def validate_session_token(token: str) -> dict:
    """Validate and decode a session token."""
    import base64
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
            except:
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
            'unlock_url': 'https://lemma.id/unlock'
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
            'unlock_url': 'https://lemma.id/unlock'
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
            'time_remaining': session_data['expires_at'] - int(time.time()),
            'profile_id': session_data.get('profile_id', 'default'),
            'profile_name': session_data.get('profile_name', 'Personal')
        },
        'credentials': [],  # Credentials stored locally only
        'synced_at': int(time.time() * 1000)
    }
    
    response = jsonify(response_data)
    response.headers.update(_cors_headers(origin))
    return response


@wallet_session_sync_bp.route('/api/wallet/link-unlock-token', methods=['POST', 'OPTIONS'])
def get_link_unlock_token():
    """
    Get an unlock token for device linking.
    
    This endpoint is called by the SOURCE device (the one generating the QR code)
    when it has a valid session. The token is included in the link QR code so the
    DESTINATION device can establish its session without needing a server-registered passkey.
    
    Requires: Valid session cookie (user must be unlocked on lemma.id)
    
    Returns:
        - unlock_token: A token valid for 5 minutes that can be used with set-session
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
    
    # Verify existing session
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        response = jsonify({
            'success': False,
            'error': 'no_session',
            'message': 'Must have valid session to generate link unlock token'
        })
        response.headers.update(_cors_headers(origin))
        return response, 401
    
    session_data = validate_session_token(session_token)
    if not session_data:
        response = jsonify({
            'success': False,
            'error': 'session_expired',
            'message': 'Session expired - unlock wallet first'
        })
        response.headers.update(_cors_headers(origin))
        return response, 401
    
    # Generate unlock token for the linking device
    wallet_id = session_data['wallet_id']
    unlocked_at = int(time.time() * 1000)  # Current time in ms
    expires_at = int(time.time()) + SESSION_DURATION  # 24 hours from now
    
    unlock_token = generate_unlock_token(
        wallet_id=wallet_id,
        unlocked_at=unlocked_at,
        expires_at=expires_at
    )
    
    logger.info(f"✅ Link unlock token generated for wallet {wallet_id[:8]}...")
    
    response = jsonify({
        'success': True,
        'unlock_token': unlock_token,
        'wallet_id': wallet_id,
        'expires_in': UNLOCK_TOKEN_TTL
    })
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
        - profile_id: Active profile ID (optional, default: 'default')
        - profile_name: Active profile display name (optional, default: 'Personal')
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
    unlock_token = data.get('unlock_token')
    profile_id = data.get('profile_id', 'default')
    profile_name = data.get('profile_name', 'Personal')

    if not wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_id required'})
        response.headers.update(_cors_headers(origin))
        return response, 400
    
    # SECURITY: Require a short-lived unlock token from server-verified passkey auth
    unlock_data = validate_unlock_token(unlock_token) if unlock_token else None
    if not unlock_data or unlock_data['wallet_id'] != wallet_id:
        response = jsonify({'success': False, 'error': 'unlock_token_required'})
        response.headers.update(_cors_headers(origin))
        return response, 403
    
    unlocked_at = unlock_data['unlocked_at']
    expires_at = unlock_data['expires_at']

    # Generate session token + CSRF token (now includes profile info)
    token = generate_session_token(wallet_id, unlocked_at, profile_id, profile_name)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = expires_at or (int(time.time()) + SESSION_DURATION)
    
    # Store in database for cross-device sync
    device_hint = request.headers.get('User-Agent', '')[:100]  # Truncate for storage
    global_stored = _store_global_session(
        wallet_id=wallet_id,
        unlocked_at=unlocked_at,
        expires_at=expires_at,
        profile_id=profile_id,
        profile_name=profile_name,
        device_hint=device_hint
    )
    logger.info(f"Set-session: global_stored={global_stored} for wallet {wallet_id[:8]}...")

    # Create response with cookie
    response = jsonify({
        'success': True,
        'session_set': True,
        'expires_at': expires_at,
        'cross_device_enabled': True,
        'global_session_stored': global_stored  # Debug: shows if DB storage worked
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


@wallet_session_sync_bp.route('/api/wallet/init-first-session', methods=['POST', 'OPTIONS'])
def init_first_session():
    """
    Initialize first session for a NEW wallet (no prior session exists).
    
    This is called after local passkey creation on lemma.id when there's no
    existing server session. It creates the initial session and returns an
    unlock_token for cross-device SSO.
    
    SECURITY:
    - Only works if NO session exists for this wallet_id yet
    - Only allowed from lemma.id origin
    - Rate limited to prevent abuse
    
    Request body:
        - wallet_id: The newly created wallet's ID
    
    Returns:
        - unlock_token: Token for set-session calls
        - success: true if session created
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
    
    # SECURITY: Only allow from lemma.id
    if origin and 'lemma.id' not in origin and 'localhost' not in origin:
        response = jsonify({'success': False, 'error': 'origin_not_allowed'})
        response.headers.update(_cors_headers(origin))
        return response, 403
    
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    
    if not wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_id required'})
        response.headers.update(_cors_headers(origin))
        return response, 400
    
    # SECURITY: Check if session already exists for this wallet
    existing_session = _get_global_session(wallet_id)
    if existing_session:
        # Wallet already has a session - don't override
        # User should use normal unlock flow
        response = jsonify({
            'success': False,
            'error': 'session_exists',
            'message': 'Wallet already has a session. Use normal unlock flow.'
        })
        response.headers.update(_cors_headers(origin))
        return response, 409  # Conflict
    
    # Create new session for this wallet
    unlocked_at = int(time.time() * 1000)
    expires_at = int(time.time()) + SESSION_DURATION
    
    # Generate unlock_token
    unlock_token = generate_unlock_token(
        wallet_id=wallet_id,
        unlocked_at=unlocked_at,
        expires_at=expires_at
    )
    
    # Store global session
    global_stored = _store_global_session(
        wallet_id=wallet_id,
        unlocked_at=unlocked_at,
        expires_at=expires_at,
        profile_id='default',
        profile_name='Personal'
    )
    
    # Generate session token for cookie
    session_token = generate_session_token(wallet_id, unlocked_at)
    csrf_token = secrets.token_urlsafe(32)
    
    logger.info(f"✅ First session initialized for new wallet {wallet_id[:8]}...")
    
    response = jsonify({
        'success': True,
        'wallet_id': wallet_id,
        'unlock_token': unlock_token,
        'expires_at': expires_at,
        'global_session_stored': global_stored
    })
    
    response.headers.update(_cors_headers(origin))
    
    # Set session cookie
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=SESSION_DURATION,
        httponly=True,
        secure=True,
        samesite='None',
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
    """Clear wallet session cookie AND global session (for cross-device lock detection)."""
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    
    # Clear global session if wallet_id provided
    # This ensures other devices detect the lock
    if wallet_id:
        logger.info(f"Clear-session: attempting to clear global session for {wallet_id[:8]}...")
        global_cleared = _clear_global_session(wallet_id)
        logger.info(f"Clear-session: global_cleared={global_cleared} for {wallet_id[:8]}...")
    else:
        global_cleared = False
    
    response = jsonify({
        'success': True, 
        'session_cleared': True,
        'global_session_cleared': global_cleared
    })
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')
    response.delete_cookie(CSRF_COOKIE_NAME, path='/')
    return response


# ============================================================
# CROSS-DEVICE SESSION SYNC (Global Sessions)
# ============================================================
# Enables "one passkey per day" across ALL devices with same wallet.
# When user unlocks on Device A, Device B can check if already unlocked.
# ============================================================

def _get_db_session():
    """Get database session for global session operations."""
    try:
        from api.database import get_db, WalletSession
        session = get_db()
        logger.debug(f"_get_db_session: got session={session is not None}, WalletSession={WalletSession is not None}")
        return session, WalletSession
    except Exception as e:
        logger.error(f"Database not available for global sessions: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None, None


def _store_global_session(wallet_id: str, unlocked_at: int, expires_at: int, 
                          profile_id: str = 'default', profile_name: str = 'Personal',
                          device_hint: str = None):
    """Store or update global wallet session in database."""
    db_session, WalletSession = _get_db_session()
    if not db_session or not WalletSession:
        logger.error(f"_store_global_session: db_session={db_session is not None}, WalletSession={WalletSession is not None}")
        return False
    
    try:
        # Convert timestamps (ms to datetime)
        unlocked_dt = datetime.fromtimestamp(unlocked_at / 1000 if unlocked_at > 10000000000 else unlocked_at)
        expires_dt = datetime.fromtimestamp(expires_at if expires_at < 10000000000 else expires_at / 1000)
        
        # Upsert: update if exists, insert if not
        existing = db_session.query(WalletSession).filter_by(wallet_id=wallet_id).first()
        
        if existing:
            existing.unlocked_at = unlocked_dt
            existing.expires_at = expires_dt
            existing.profile_id = profile_id
            existing.profile_name = profile_name
            existing.device_hint = device_hint
            existing.updated_at = datetime.utcnow()
        else:
            new_session = WalletSession(
                wallet_id=wallet_id,
                unlocked_at=unlocked_dt,
                expires_at=expires_dt,
                profile_id=profile_id,
                profile_name=profile_name,
                device_hint=device_hint
            )
            db_session.add(new_session)
        
        db_session.commit()
        logger.info(f"Global session stored for wallet {wallet_id[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to store global session: {e}")
        db_session.rollback()
        return False
    finally:
        db_session.close()


def _get_global_session(wallet_id: str):
    """Get global session for a wallet_id if valid."""
    logger.debug(f"_get_global_session called for wallet: {wallet_id[:8] if wallet_id else 'None'}...")
    db_session, WalletSession = _get_db_session()
    if not db_session or not WalletSession:
        logger.error(f"_get_global_session: DB not available")
        return None
    
    try:
        session = db_session.query(WalletSession).filter_by(wallet_id=wallet_id).first()
        
        if not session:
            logger.info(f"_get_global_session: No session found for {wallet_id[:8]}...")
            return None
        
        # Check if expired
        if session.expires_at < datetime.utcnow():
            logger.info(f"_get_global_session: Session EXPIRED for {wallet_id[:8]}... (expired at {session.expires_at})")
            return None
        
        logger.info(f"_get_global_session: Found VALID session for {wallet_id[:8]}... (expires {session.expires_at})")
        return {
            'wallet_id': session.wallet_id,
            'unlocked_at': int(session.unlocked_at.timestamp() * 1000),
            'expires_at': int(session.expires_at.timestamp()),
            'profile_id': session.profile_id,
            'profile_name': session.profile_name,
            'device_hint': session.device_hint
        }
    except Exception as e:
        logger.error(f"Failed to get global session: {e}")
        return None
    finally:
        db_session.close()


def _clear_global_session(wallet_id: str):
    """Clear/invalidate global session for a wallet_id (called on lock)."""
    db_session, WalletSession = _get_db_session()
    if not db_session or not WalletSession:
        return False
    
    try:
        # Delete the session record entirely
        deleted = db_session.query(WalletSession).filter_by(wallet_id=wallet_id).delete()
        db_session.commit()
        
        if deleted:
            logger.info(f"Global session cleared for wallet {wallet_id[:8]}...")
        return deleted > 0
    except Exception as e:
        logger.error(f"Failed to clear global session: {e}")
        db_session.rollback()
        return False
    finally:
        db_session.close()


@wallet_session_sync_bp.route('/api/wallet/global-session', methods=['POST', 'OPTIONS'])
def check_global_session():
    """
    Check if a wallet has an active session on ANY device.
    
    This enables cross-device "one passkey per day" - if user unlocked on their phone,
    their laptop can skip the passkey prompt.
    
    Request body:
        - wallet_id: The wallet identifier to check
    
    Returns:
        - valid: true if wallet was unlocked within 24h on any device
        - session: Session details if valid
    
    PRIVACY: Only wallet_id is required. No tracking of which device/site is checking.
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
    
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    
    if not wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_id required'})
        response.headers.update(_cors_headers(origin))
        return response, 400
    
    # Check global session
    global_session = _get_global_session(wallet_id)
    
    if global_session:
        response = jsonify({
            'success': True,
            'valid': True,
            'session': {
                'wallet_id': global_session['wallet_id'],
                'unlocked_at': global_session['unlocked_at'],
                'expires_at': global_session['expires_at'],
                'time_remaining': global_session['expires_at'] - int(time.time()),
                'profile_id': global_session['profile_id'],
                'profile_name': global_session['profile_name'],
                'cross_device': True  # Flag that this came from another device
            }
        })
    else:
        response = jsonify({
            'success': True,
            'valid': False,
            'message': 'No active global session for this wallet'
        })
    
    response.headers.update(_cors_headers(origin))
    return response


# ============================================================
# REDIRECT AUTH TOKEN EXCHANGE
# ============================================================
# For mobile browsers that block third-party cookies/storage,
# we use a short-lived token passed in the redirect URL.
#
# Flow:
# 1. User unlocks on lemma.id wallet page
# 2. lemma.id calls /api/wallet/create-redirect-token
# 3. Token returned, included in redirect URL
# 4. Third-party site receives token, calls /api/wallet/exchange-redirect-token
# 5. Token validated, wallet_secret returned, token deleted (single-use)
#
# Security:
# - Tokens expire in 60 seconds
# - Tokens are single-use (deleted after exchange)
# - Tokens are cryptographically random
# - wallet_secret encrypted in transit (HTTPS)
# ============================================================

def _get_redirect_token_db():
    """Get database session and RedirectToken model."""
    try:
        from api.database import get_session, RedirectToken
        return get_session(), RedirectToken
    except Exception as e:
        logger.warning(f"Database not available for redirect tokens: {e}")
        return None, None


def _cleanup_expired_tokens_db():
    """Remove expired tokens from database."""
    db_session, RedirectToken = _get_redirect_token_db()
    if not db_session or not RedirectToken:
        return
    
    try:
        expired_count = db_session.query(RedirectToken).filter(
            RedirectToken.expires_at < datetime.utcnow()
        ).delete()
        db_session.commit()
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired redirect tokens")
    except Exception as e:
        logger.error(f"Failed to cleanup expired tokens: {e}")
        db_session.rollback()
    finally:
        db_session.close()


@wallet_session_sync_bp.route('/api/wallet/create-redirect-token', methods=['POST', 'OPTIONS'])
def create_redirect_token():
    """
    DEPRECATED: Legacy endpoint for server-side redirect tokens.
    
    New SDK versions (2.30.0+) use client-side encryption instead.
    This endpoint is kept for backward compatibility with older SDKs.
    
    PRIVACY NOTE: We intentionally do NOT store return_url to avoid tracking
    which sites users authenticate to.
    
    Request body:
        - wallet_id: The wallet identifier
        - wallet_secret: The wallet secret to pass to third-party site
        - return_url: IGNORED (not stored for privacy)
    
    Returns:
        - token: Short-lived token to include in redirect URL
    
    SECURITY: Only called from lemma.id domain (same-origin)
    TOKEN STORAGE: Database-backed for multi-dyno Heroku deployment
    """
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://lemma.id'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # Only allow from lemma.id
    origin = request.headers.get('Origin', '')
    if 'lemma.id' not in origin and 'localhost' not in origin:
        return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403
    
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    wallet_secret = data.get('wallet_secret')
    # NOTE: return_url is intentionally ignored for privacy - we don't track site visits
    
    if not wallet_id or not wallet_secret:
        return jsonify({'success': False, 'error': 'wallet_id and wallet_secret required'}), 400
    
    # Get database session
    db_session, RedirectToken = _get_redirect_token_db()
    if not db_session or not RedirectToken:
        return jsonify({'success': False, 'error': 'database_unavailable'}), 500
    
    try:
        # Cleanup old tokens periodically
        _cleanup_expired_tokens_db()
        
        # Generate random token
        token = secrets.token_urlsafe(32)
        
        # Store with 60 second expiration in DATABASE (works across Heroku dynos)
        # PRIVACY: return_url is NOT stored - we don't track which sites users visit
        token_record = RedirectToken(
            token=token,
            wallet_id=wallet_id,
            wallet_secret=wallet_secret,
            return_url=None,  # Intentionally not stored for privacy
            expires_at=datetime.utcnow() + timedelta(seconds=60)
        )
        db_session.add(token_record)
        db_session.commit()
        
        logger.info(f"Created legacy redirect token for wallet (expires in 60s)")
        
        response = jsonify({
            'success': True,
            'token': token,
            'expires_in': 60
        })
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
        
    except Exception as e:
        logger.error(f"Failed to create redirect token: {e}")
        db_session.rollback()
        return jsonify({'success': False, 'error': 'database_error'}), 500
    finally:
        db_session.close()


@wallet_session_sync_bp.route('/api/wallet/exchange-redirect-token', methods=['POST', 'OPTIONS'])
def exchange_redirect_token():
    """
    Exchange a redirect token for wallet authentication data.
    
    Called by third-party site SDK after redirect from lemma.id.
    Token is single-use - deleted after successful exchange.
    
    Request body:
        - token: The token from the redirect URL
    
    Returns:
        - wallet_id: The wallet identifier
        - wallet_secret: The wallet secret for PPID derivation
    
    SECURITY: Tokens are single-use and expire in 60 seconds
    """
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403
    
    data = request.get_json() or {}
    token = data.get('token')
    
    if not token:
        response = jsonify({'success': False, 'error': 'token required'})
        response.headers.update(_cors_headers(origin))
        return response, 400
    
    # Get database session
    db_session, RedirectToken = _get_redirect_token_db()
    if not db_session or not RedirectToken:
        response = jsonify({'success': False, 'error': 'database_unavailable'})
        response.headers.update(_cors_headers(origin))
        return response, 500
    
    try:
        # Look up token in database
        token_record = db_session.query(RedirectToken).filter_by(token=token).first()
        
        if not token_record:
            response = jsonify({
                'success': False,
                'error': 'invalid_or_expired_token',
                'message': 'Token not found, expired, or already used'
            })
            response.headers.update(_cors_headers(origin))
            return response, 400
        
        # Check expiration
        if token_record.expires_at < datetime.utcnow():
            db_session.delete(token_record)
            db_session.commit()
            response = jsonify({
                'success': False,
                'error': 'token_expired',
                'message': 'Token has expired'
            })
            response.headers.update(_cors_headers(origin))
            return response, 400
        
        # Token valid - extract data and DELETE (single-use)
        wallet_id = token_record.wallet_id
        wallet_secret = token_record.wallet_secret
        db_session.delete(token_record)
        db_session.commit()
        
        logger.info(f"Exchanged redirect token successfully (from DB)")
        
        response = jsonify({
            'success': True,
            'wallet_id': wallet_id,
            'wallet_secret': wallet_secret
        })
        response.headers.update(_cors_headers(origin))
        return response
        
    except Exception as e:
        logger.error(f"Failed to exchange redirect token: {e}")
        db_session.rollback()
        response = jsonify({'success': False, 'error': 'database_error'})
        response.headers.update(_cors_headers(origin))
        return response, 500
    finally:
        db_session.close()


# ============================================================
# PRIVACY MODEL
# ============================================================
# - Session (unlock status): Server cookie (stateless JWT) + DB for cross-device
# - Credentials: LOCAL ONLY in each site's IndexedDB
# - Server stores: wallet_id + timestamps ONLY (no user identity, no site visits)
# - Cross-device sync: Opt-in, only stores that "wallet X unlocked at time Y"
# - Redirect auth (v2.30.0+): CLIENT-SIDE ENCRYPTION - wallet secret never touches server
#   * SDK generates encryption key, stores locally
#   * lemma.id client-side JS encrypts wallet data
#   * Encrypted blob returned in URL, decrypted by SDK
#   * Server NEVER sees the wallet_secret or which sites user authenticates to
# - Legacy redirect tokens: For old SDK versions, server stores wallet_secret for 60s
#   * return_url is NOT stored (privacy improvement)
# ============================================================
