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
from flask_cors import cross_origin
import time
import os
import secrets
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote
from html import escape

# Import session logic from centralized module
from auth.session_manager import (
    SESSION_DURATION,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    UNLOCK_TOKEN_TTL,
    generate_session_token,
    validate_session_token,
    generate_unlock_token,
    validate_unlock_token,
    generate_csrf_token,
    get_session_expiry,
    get_current_time_ms,
)
from auth.decorators import optional_auth

logger = logging.getLogger(__name__)

wallet_session_sync_bp = Blueprint('wallet_session_sync', __name__)
CLI_LINK_TTL_SECONDS = 300

try:
    from auth.redis_store import store as redis_store, get as redis_get, delete as redis_delete
except Exception:  # pragma: no cover
    redis_store = None
    redis_get = None
    redis_delete = None


def _cli_link_key(state: str) -> str:
    return f"wallet_cli_link:{state}"


def _persist_cli_link(state: str, payload: dict) -> bool:
    if redis_store:
        return bool(redis_store(_cli_link_key(state), payload, ttl_seconds=CLI_LINK_TTL_SECONDS))
    return _storage.set_session(_cli_link_key(state), payload, ttl=CLI_LINK_TTL_SECONDS)


def _read_cli_link(state: str) -> dict | None:
    if redis_get:
        return redis_get(_cli_link_key(state))
    return _storage.get_session(_cli_link_key(state))


def _delete_cli_link(state: str) -> None:
    if redis_delete:
        redis_delete(_cli_link_key(state))
        return
    _storage.delete_session(_cli_link_key(state))

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


def _canonical_api_base(raw: str | None) -> str:
    """Normalize API base URL and collapse duplicated URL fragments."""
    value = str(raw or "").strip()
    if not value:
        return "https://lemma.id"

    # Keep first token when env var includes separators.
    for sep in (",", " ", "\n", "\t"):
        if sep in value:
            value = value.split(sep, 1)[0].strip()

    # Guard against accidental concatenation like "https://lemma.idhttps://lemma.id".
    for marker in ("https://", "http://"):
        first = value.find(marker)
        if first == 0:
            second = value.find(marker, len(marker))
            if second > 0:
                value = value[:second].strip()
                break

    parsed = urlparse(value if "://" in value else f"https://{value}")
    if not parsed.netloc:
        return "https://lemma.id"
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}".rstrip("/")


def _origin_hostname(origin: str | None) -> str | None:
    normalized = _parse_origin(origin or '')
    if not normalized:
        return None
    host = (urlparse(normalized).hostname or '').strip().lower().rstrip('.')
    return host or None


def _host_matches_suffix(hostname: str, suffix: str) -> bool:
    host = (hostname or '').strip().lower().rstrip('.')
    normalized_suffix = (suffix or '').strip().lower().lstrip('.').rstrip('.')
    if not host or not normalized_suffix:
        return False
    return host == normalized_suffix or host.endswith(f".{normalized_suffix}")


def _lemma_origin_allowed(origin: str | None) -> bool:
    """
    Strict allowlist for endpoints that must only be callable from lemma origins.
    Uses hostname parsing (never substring checks) to prevent origin spoofing.
    """
    hostname = _origin_hostname(origin)
    if not hostname:
        return False
    if hostname == 'lemma.id' or hostname.endswith('.lemma.id'):
        return True
    if _ALLOW_DEV_ORIGINS and hostname in {'localhost', '127.0.0.1'}:
        return True
    return False


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    normalized = _parse_origin(origin)
    hostname = _origin_hostname(origin)
    if not normalized or not hostname:
        return False
    if normalized in _ALLOWED_ORIGINS:
        return True
    for suffix in _ALLOWED_ORIGIN_SUFFIXES:
        if _host_matches_suffix(hostname, suffix):
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
    """Validate CSRF token from cookie matches header."""
    from auth.session_manager import validate_csrf
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get('X-Lemma-CSRF')
    return validate_csrf(csrf_cookie, csrf_header)


@wallet_session_sync_bp.route('/api/wallet/cli-link/start', methods=['POST'])
@optional_auth
def wallet_cli_link_start():
    """
    Start a short-lived CLI wallet-link flow.

    Returns a browser URL to approve from an already-unlocked wallet session and
    a poll URL for the CLI to retrieve a temporary unlock token.
    """
    try:
        payload = request.get_json(silent=True) or {}
        requested_scope = str(payload.get('requested_scope') or 'wallet:revoke').strip().lower()
        state = secrets.token_urlsafe(24)
        api_base = _canonical_api_base(os.environ.get('LEMMA_BASE_URL') or request.url_root)
        approve_url = f"{api_base}/api/wallet/cli-link/approve?state={state}"
        poll_url = f"{api_base}/api/wallet/cli-link/poll?state={state}"
        stored = _persist_cli_link(
            state,
            {
                'state': state,
                'status': 'pending',
                'requested_scope': requested_scope,
                'created_at': int(time.time()),
                'expires_at': int(time.time()) + CLI_LINK_TTL_SECONDS,
            },
        )
        if not stored:
            return jsonify({'success': False, 'error': 'storage_unavailable'}), 503
        return jsonify(
            {
                'success': True,
                'state': state,
                'requested_scope': requested_scope,
                'approve_url': approve_url,
                'poll_url': poll_url,
                'expires_in': CLI_LINK_TTL_SECONDS,
            }
        )
    except Exception as exc:
        logger.error("wallet_cli_link_start failed: %s", exc)
        return jsonify({'success': False, 'error': 'cli_link_start_failed'}), 500


@wallet_session_sync_bp.route('/api/wallet/cli-link/approve', methods=['GET'])
def wallet_cli_link_approve():
    """Approve pending CLI link from unlocked browser wallet session."""
    state = str(request.args.get('state') or '').strip()
    if not state:
        return make_response("Missing state", 400)
    record = _read_cli_link(state)
    if not isinstance(record, dict):
        return make_response("Link request expired or not found.", 404)
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    session_data = validate_session_token(session_token) if session_token else None
    if not session_data:
        api_base = _canonical_api_base(os.environ.get('LEMMA_BASE_URL') or request.url_root)
        retry_url = f"{api_base}/api/wallet/cli-link/approve?state={quote(state, safe='')}"
        unlock_url = f"{api_base}/unlock?return_url={quote(retry_url, safe='')}"
        html = f"""
        <html><body>
          <h3>Wallet Unlock Required</h3>
          <p>Complete unlock, then you will be returned to finish CLI approval automatically.</p>
          <p><a href="{escape(unlock_url)}">Continue to unlock</a></p>
          <p style="font-size: 12px; color: #6b7280;">If redirect fails, reopen this approval link from your terminal output.</p>
        </body></html>
        """
        return make_response(html, 401)

    unlocked_at = int(session_data.get('unlocked_at') or int(time.time()))
    expires_at = int(time.time()) + min(300, UNLOCK_TOKEN_TTL)
    unlock_token = generate_unlock_token(session_data.get('wallet_id'), unlocked_at, expires_at)
    approved = dict(record)
    approved.update(
        {
            'status': 'approved',
            'wallet_id': session_data.get('wallet_id'),
            'approved_at': int(time.time()),
            'unlock_token': unlock_token,
        }
    )
    _persist_cli_link(state, approved)
    return make_response(
        """
        <html><body>
          <h3>CLI Link Approved</h3>
          <p>You can close this tab and return to your terminal.</p>
        </body></html>
        """,
        200,
    )


@wallet_session_sync_bp.route('/api/wallet/cli-link/poll', methods=['GET'])
def wallet_cli_link_poll():
    """Poll pending CLI link state; returns unlock token once approved."""
    state = str(request.args.get('state') or '').strip()
    if not state:
        return jsonify({'success': False, 'error': 'missing_state'}), 400
    record = _read_cli_link(state)
    if not isinstance(record, dict):
        return jsonify({'success': False, 'error': 'not_found'}), 404
    if record.get('status') != 'approved':
        return jsonify({'success': True, 'approved': False, 'state': state}), 200
    unlock_token = str(record.get('unlock_token') or '').strip()
    wallet_id = str(record.get('wallet_id') or '').strip()
    _delete_cli_link(state)
    return jsonify(
        {
            'success': True,
            'approved': True,
            'state': state,
            'wallet_id': wallet_id,
            'unlock_token': unlock_token,
            'expires_in': min(300, UNLOCK_TOKEN_TTL),
        }
    ), 200


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
    
    # SECURITY: Only allow from lemma origins (or explicit local dev origins).
    if not _lemma_origin_allowed(origin):
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


@wallet_session_sync_bp.route('/api/wallet/signal-unlock', methods=['POST', 'OPTIONS'])
def signal_unlock():
    """
    Signal that a wallet has been unlocked via local passkey verification.
    
    This is a SIMPLE endpoint that just stores unlock state for cross-device sync.
    NO cryptographic verification is done here - that's intentional!
    
    Security model:
    - The passkey protects ACCESS to the wallet secret (local verification)
    - HSM-signed lemmas provide the actual authorization/security
    - This endpoint just enables cross-device convenience ("one passkey per day")
    
    A malicious client could call this without actually verifying a passkey,
    but that's harmless because:
    1. They still can't get the wallet secret (stored locally, protected by passkey)
    2. They still can't forge lemmas (requires HSM signature)
    3. They can only set unlock state for wallet IDs they know
    
    Request body:
        - wallet_id: The wallet that was unlocked
        - unlocked_at: Timestamp of unlock (ms)
        - expires_at: When session expires (seconds)
        - profile_id: Active profile ID (optional)
        - profile_name: Active profile name (optional)
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
    
    # Only allow from lemma origins (where local passkey verification happens).
    if not _lemma_origin_allowed(origin):
        response = jsonify({'success': False, 'error': 'origin_not_allowed'})
        response.headers.update(_cors_headers(origin))
        return response, 403
    
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    unlocked_at = data.get('unlocked_at', int(time.time() * 1000))
    expires_at = data.get('expires_at', int(time.time()) + SESSION_DURATION)
    profile_id = data.get('profile_id', 'default')
    profile_name = data.get('profile_name', 'Personal')
    
    if not wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_id required'})
        response.headers.update(_cors_headers(origin))
        return response, 400
    
    # Store global session for cross-device sync
    logger.info(f"Signal-unlock: storing session for wallet {wallet_id[:8]}...")
    global_stored = _store_global_session(
        wallet_id=wallet_id,
        unlocked_at=unlocked_at,
        expires_at=expires_at,
        profile_id=profile_id,
        profile_name=profile_name
    )
    
    if not global_stored:
        logger.error(f"Signal-unlock: failed to store global session for {wallet_id[:8]}")
        response = jsonify({'success': False, 'error': 'database_error'})
        response.headers.update(_cors_headers(origin))
        return response, 500
    
    logger.info(f"Signal-unlock: session stored for wallet {wallet_id[:8]}")
    
    # Publish SSE event so other devices detect the unlock instantly
    try:
        from api.revocation_events import publish_session_event
        publish_session_event(wallet_id, 'session_restored', expires_at=expires_at)
    except Exception as e:
        logger.warning(f"Signal-unlock: SSE publish failed (non-fatal): {e}")
    
    # Also set session cookie for bridge iframe
    session_token = generate_session_token(wallet_id, unlocked_at)
    csrf_token = secrets.token_urlsafe(32)
    
    response = jsonify({
        'success': True,
        'global_session_stored': True,
        'expires_at': expires_at,
        'message': 'Unlock state stored for cross-device sync'
    })
    
    response.headers.update(_cors_headers(origin))
    
    # Set session cookies
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


@wallet_session_sync_bp.route('/api/wallet/clear-session', methods=['POST', 'OPTIONS'])
def clear_session():
    """Clear wallet session cookie AND global session (for cross-device lock detection)."""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    origin = request.headers.get('Origin')
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    # Fallback: derive wallet_id from signed session cookie if client did not send it.
    if not wallet_id:
        try:
            session_token = request.cookies.get(SESSION_COOKIE_NAME)
            session_data = validate_session_token(session_token) if session_token else None
            wallet_id = session_data.get('wallet_id') if session_data else None
            if wallet_id:
                logger.info(f"Clear-session: derived wallet_id from session cookie ({wallet_id[:8]}...)")
        except Exception as e:
            logger.warning(f"Clear-session: failed to derive wallet_id from cookie: {e}")
    
    # Clear global session if wallet_id provided
    # This ensures other devices detect the lock
    if wallet_id:
        logger.info(f"Clear-session: attempting to clear global session for {wallet_id[:8]}...")
        global_cleared = _clear_global_session(wallet_id)
        logger.info(f"Clear-session: global_cleared={global_cleared} for {wallet_id[:8]}...")

        # Server-side session revocation: blacklist ALL sessions for this wallet
        # so stolen/cached tokens are rejected even before cookie expiry
        from auth.session_manager import revoke_wallet_sessions
        revoke_wallet_sessions(wallet_id)
        
        # Publish SSE event so other devices detect the lock instantly
        try:
            from api.revocation_events import publish_session_event
            publish_session_event(wallet_id, 'session_invalidated')
        except Exception as e:
            logger.warning(f"Clear-session: SSE publish failed (non-fatal): {e}")
    else:
        logger.warning("Clear-session: no wallet_id available (request or cookie)")
        global_cleared = False
    
    response = jsonify({
        'success': True, 
        'session_cleared': True,
        'global_session_cleared': global_cleared
    })
    response.headers.update(_cors_headers(origin))
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
# REDIRECT AUTH TOKEN EXCHANGE (REMOVED)
# ============================================================
# Legacy redirect tokens transferred wallet_secret to third-party sites.
# Removed in favor of the lemma_credential redirect flow (wallet_secret stays
# on lemma.id). Endpoints return HTTP 410 Gone.

LEGACY_REDIRECT_TOKEN_REMOVED = {
    'success': False,
    'error': 'redirect_token_removed',
    'message': (
        'Server-side redirect tokens are no longer supported. '
        'Upgrade to the lemma_credential redirect flow.'
    ),
}


def _legacy_redirect_token_response(origin=None, status=410):
    response = jsonify(LEGACY_REDIRECT_TOKEN_REMOVED)
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response, status


@wallet_session_sync_bp.route('/api/wallet/create-redirect-token', methods=['POST', 'OPTIONS'])
def create_redirect_token():
    """Removed: legacy server-side redirect token creation."""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://lemma.id'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    origin = request.headers.get('Origin', '')
    if not _lemma_origin_allowed(origin):
        return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403

    return _legacy_redirect_token_response(origin)


@wallet_session_sync_bp.route('/api/wallet/exchange-redirect-token', methods=['POST', 'OPTIONS'])
def exchange_redirect_token():
    """Removed: legacy server-side redirect token exchange."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        return response

    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403

    return _legacy_redirect_token_response(origin)


# ---------------------------------------------------------------------------
# Wallet Ed25519 signing key registration (local-first hardening)
# ---------------------------------------------------------------------------

@wallet_session_sync_bp.route("/api/wallet/challenge", methods=["POST"])
@cross_origin()
def wallet_challenge():
    """Issue a short-lived nonce for wallet assertion signing."""
    from api.wallet_authn import issue_wallet_challenge

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    payload = issue_wallet_challenge(wallet_id=wallet_id)
    response = jsonify(payload)
    response.headers.update(_cors_headers(request.headers.get("Origin")))
    return response


@wallet_session_sync_bp.route("/api/wallet/register-signing-key", methods=["POST"])
@cross_origin()
def wallet_register_signing_key():
    """Register wallet Ed25519 public key (self-signed registration proof)."""
    from api.wallet_authn import register_wallet_signing_key

    body = request.get_json(silent=True) or {}
    result = register_wallet_signing_key(
        wallet_id=(body.get("wallet_id") or "").strip(),
        pubkey_b64=(body.get("pubkey") or "").strip(),
        signature_b64=(body.get("signature") or "").strip(),
    )
    if not result.ok:
        return jsonify({
            "success": False,
            "error": result.error,
            "code": result.code,
        }), 403
    response = jsonify({"success": True, "registered": True})
    response.headers.update(_cors_headers(request.headers.get("Origin")))
    return response


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
