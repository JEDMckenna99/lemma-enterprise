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
import base64
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
WALLET_WEBAUTHN_TTL_SECONDS = 120

try:
    from auth.redis_store import (
        consume as redis_consume,
        delete as redis_delete,
        get as redis_get,
        store as redis_store,
    )
except Exception:  # pragma: no cover
    redis_store = None
    redis_get = None
    redis_delete = None
    redis_consume = None


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


def _wallet_webauthn_key(challenge_key: str) -> str:
    return f"wallet:webauthn-session:{challenge_key}"


def _issue_wallet_session_response(
    *,
    wallet_id: str,
    profile_id: str = "default",
    profile_name: str = "Personal",
    extra_payload: dict | None = None,
):
    """Issue a server-trusted wallet cookie after a verified ceremony."""
    unlocked_at = int(time.time() * 1000)
    expires_at = int(time.time()) + SESSION_DURATION
    _store_global_session(
        wallet_id=wallet_id,
        unlocked_at=unlocked_at,
        expires_at=expires_at,
        profile_id=profile_id,
        profile_name=profile_name,
    )
    payload = {
        "success": True,
        "wallet_id": wallet_id,
        "unlocked_at": unlocked_at,
        "expires_at": expires_at,
        **(extra_payload or {}),
    }
    response = make_response(jsonify(payload))
    response.set_cookie(
        SESSION_COOKIE_NAME,
        generate_session_token(wallet_id, unlocked_at),
        max_age=SESSION_DURATION,
        httponly=True,
        secure=True,
        samesite="None",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        generate_csrf_token(),
        max_age=SESSION_DURATION,
        httponly=False,
        secure=True,
        samesite="None",
        path="/",
    )
    response.headers.update(_cors_headers(request.headers.get("Origin")))
    return response


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
    csrf_header = request.headers.get('X-Lemma-CSRF') or request.form.get('csrf_token')
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


@wallet_session_sync_bp.route('/api/wallet/cli-link/approve', methods=['GET', 'POST'])
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

    if request.method == 'GET':
        csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or ''
        action_url = f"/api/wallet/cli-link/approve?state={quote(state, safe='')}"
        html = f"""
        <html><body>
          <h3>Approve CLI Link</h3>
          <p>Approve this terminal to use your currently unlocked wallet session?</p>
          <form method="post" action="{escape(action_url)}">
            <input type="hidden" name="csrf_token" value="{escape(csrf_token)}">
            <button type="submit">Approve CLI Link</button>
          </form>
        </body></html>
        """
        return make_response(html, 200)

    if not _validate_csrf():
        return make_response("CSRF validation failed.", 403)

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

    if not _validate_csrf():
        response = jsonify({'success': False, 'error': 'csrf_validation_failed'})
        response.headers.update(_cors_headers(origin))
        return response, 403
    
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


@wallet_session_sync_bp.route('/api/wallet/session-unlock/begin', methods=['POST', 'OPTIONS'])
def wallet_session_unlock_begin():
    """Issue a server challenge for a wallet-bound WebAuthn assertion."""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.update(_cors_headers(request.headers.get('Origin')))
        return response
    origin = request.headers.get('Origin')
    if not _lemma_origin_allowed(origin):
        response = jsonify({'success': False, 'error': 'origin_not_allowed'})
        response.headers.update(_cors_headers(origin))
        return response, 403

    body = request.get_json(silent=True) or {}
    wallet_id = str(body.get('wallet_id') or '').strip()
    device_id = str(body.get('device_id') or '').strip()
    credential_id = str(body.get('credential_id') or '').strip()
    if not wallet_id or not device_id or not credential_id:
        return jsonify({'success': False, 'error': 'wallet_id, device_id, and credential_id required'}), 400

    from api.database import SessionLocal, WalletPasskey

    db = SessionLocal()
    try:
        passkey = db.query(WalletPasskey).filter_by(
            wallet_id=wallet_id,
            device_id=device_id,
            credential_id=credential_id,
        ).first()
        if not passkey or passkey.revoked_at:
            return jsonify({'success': False, 'error': 'wallet_passkey_not_registered'}), 403
    finally:
        db.close()

    from api.passkey_auth import RP_ID

    challenge = secrets.token_bytes(32)
    challenge_key = f"wus_{secrets.token_urlsafe(24)}"
    redis_store(
        _wallet_webauthn_key(challenge_key),
        {
            'challenge': base64.urlsafe_b64encode(challenge).decode('ascii'),
            'wallet_id': wallet_id,
            'device_id': device_id,
            'credential_id': credential_id,
        },
        ttl_seconds=WALLET_WEBAUTHN_TTL_SECONDS,
    )
    response = jsonify({
        'success': True,
        'challenge_key': challenge_key,
        'challenge': base64.urlsafe_b64encode(challenge).decode('ascii').rstrip('='),
        'rp_id': RP_ID,
        'expires_in': WALLET_WEBAUTHN_TTL_SECONDS,
    })
    response.headers.update(_cors_headers(origin))
    return response


@wallet_session_sync_bp.route('/api/wallet/session-unlock/complete', methods=['POST', 'OPTIONS'])
def wallet_session_unlock_complete():
    """Verify wallet WebAuthn and issue the first trusted server session."""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.update(_cors_headers(request.headers.get('Origin')))
        return response
    origin = request.headers.get('Origin')
    if not _lemma_origin_allowed(origin):
        response = jsonify({'success': False, 'error': 'origin_not_allowed'})
        response.headers.update(_cors_headers(origin))
        return response, 403

    body = request.get_json(silent=True) or {}
    challenge_key = str(body.get('challenge_key') or '').strip()
    credential = body.get('credential')
    if not challenge_key or not isinstance(credential, dict):
        return jsonify({'success': False, 'error': 'challenge_key and credential required'}), 400
    stored = redis_consume(_wallet_webauthn_key(challenge_key)) if redis_consume else None
    if not stored:
        return jsonify({'success': False, 'error': 'wallet_unlock_challenge_expired'}), 401

    credential_id = str(credential.get('id') or '').strip()
    if credential_id != str(stored.get('credential_id') or ''):
        return jsonify({'success': False, 'error': 'credential_id_mismatch'}), 403

    from api.fresh_passkey_attestation import (
        allowed_fresh_passkey_origins,
        lookup_wallet_passkey_public_key,
        update_wallet_passkey_sign_count,
        verify_wallet_webauthn_assertion,
    )
    from api.passkey_auth import RP_ID

    public_key, sign_count = lookup_wallet_passkey_public_key(credential_id)
    if not public_key:
        return jsonify({'success': False, 'error': 'wallet_passkey_not_registered'}), 403
    ok, reason, new_sign_count = verify_wallet_webauthn_assertion(
        credential=credential,
        expected_challenge=base64.urlsafe_b64decode(stored['challenge']),
        rp_id=RP_ID,
        origin=allowed_fresh_passkey_origins(),
        public_key_b64=public_key,
        sign_count=sign_count,
    )
    if not ok:
        return jsonify({'success': False, 'error': reason}), 403

    update_wallet_passkey_sign_count(credential_id, new_sign_count)
    return _issue_wallet_session_response(
        wallet_id=str(stored['wallet_id']),
        profile_id=str(body.get('profile_id') or 'default'),
        profile_name=str(body.get('profile_name') or 'Personal'),
        extra_payload={'auth_method': 'webauthn'},
    )


@wallet_session_sync_bp.route('/api/wallet/init-first-session', methods=['POST', 'OPTIONS'])
def init_first_session():
    """Retired wallet-id-only bootstrap.

    New wallets bind a passkey and establish a trusted session through the
    server-verified ``session-unlock`` WebAuthn ceremony.
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
    
    response = jsonify({
        'success': False,
        'error': 'first_session_route_retired',
        'message': 'Use the server-verified wallet session-unlock WebAuthn ceremony.',
    })
    response.headers.update(_cors_headers(origin))
    return response, 410


@wallet_session_sync_bp.route('/api/wallet/signal-unlock', methods=['POST', 'OPTIONS'])
def signal_unlock():
    """Create server wallet-session state from an enrolled device assertion."""
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
    wallet_id = str(data.get('wallet_id') or '').strip()
    requested_unlocked_at = int(data.get('unlocked_at') or int(time.time() * 1000))
    requested_expires_at = int(data.get('expires_at') or int(time.time()) + SESSION_DURATION)
    profile_id = str(data.get('profile_id') or 'default')
    profile_name = str(data.get('profile_name') or 'Personal')
    
    if not wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_id required'})
        response.headers.update(_cors_headers(origin))
        return response, 400

    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    session_data = validate_session_token(session_token) if session_token else None
    if not session_data or str(session_data.get('wallet_id') or '') != wallet_id:
        response = jsonify({
            'success': False,
            'error': 'fresh_webauthn_session_required',
            'code': 'fresh_webauthn_session_required',
        })
        response.headers.update(_cors_headers(origin))
        return response, 403

    if not _validate_csrf():
        response = jsonify({'success': False, 'error': 'csrf_validation_failed'})
        response.headers.update(_cors_headers(origin))
        return response, 403

    from api.wallet_authn import verify_assertion_from_body

    verify_result, _verified_fields = verify_assertion_from_body(
        data,
        wallet_id=wallet_id,
        field_names=['unlocked_at', 'expires_at', 'profile_id', 'profile_name'],
    )
    if not verify_result.ok:
        response = jsonify({
            'success': False,
            'error': verify_result.error or 'wallet_assertion_required',
            'code': verify_result.code or 'wallet_assertion_required',
        })
        response.headers.update(_cors_headers(origin))
        return response, 403

    now_ms = int(time.time() * 1000)
    if abs(requested_unlocked_at - now_ms) > 300_000:
        response = jsonify({'success': False, 'error': 'unlock_timestamp_invalid'})
        response.headers.update(_cors_headers(origin))
        return response, 400

    # Use server time and cap the caller's signed duration to the configured
    # session maximum.
    unlocked_at = now_ms
    expires_at = min(
        max(int(time.time()) + 1, requested_expires_at),
        int(time.time()) + SESSION_DURATION,
    )
    
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

    # Set session cookie for bridge iframe
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
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    session_data = validate_session_token(session_token) if session_token else None
    if not session_data:
        response = jsonify({'success': False, 'error': 'valid_session_required'})
        response.headers.update(_cors_headers(origin))
        return response, 401
    if not _validate_csrf():
        response = jsonify({'success': False, 'error': 'csrf_validation_failed'})
        response.headers.update(_cors_headers(origin))
        return response, 403
    wallet_id = str(session_data.get('wallet_id') or '').strip()
    requested_wallet_id = str(data.get('wallet_id') or '').strip()
    if requested_wallet_id and requested_wallet_id != wallet_id:
        response = jsonify({'success': False, 'error': 'wallet_session_mismatch'})
        response.headers.update(_cors_headers(origin))
        return response, 403
    
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
# CROSS-DEVICE SESSION SYNC (REMOVED)
# ============================================================
# The "one passkey per day across all devices" cross-device session sync was
# removed. Wallet unlock is now local-per-device for the user-chosen duration,
# and revocation propagates via the pull-based signed Bloom snapshot
# (/api/revocation/bloom-filter).
#
# These helpers are retained as inert no-ops so existing callers (and tests
# that patch them) keep working without writing/reading the global
# WalletSession table or broadcasting a global wallet_id.
# ============================================================

def _store_global_session(wallet_id: str, unlocked_at: int = 0, expires_at: int = 0,
                          profile_id: str = 'default', profile_name: str = 'Personal',
                          device_hint: str = None):
    """Deprecated no-op: cross-device global session storage was removed."""
    return True


def _get_global_session(wallet_id: str):
    """Deprecated no-op: cross-device global session lookup was removed."""
    return None


def _clear_global_session(wallet_id: str):
    """Deprecated no-op: cross-device global session clearing was removed."""
    return False


@wallet_session_sync_bp.route('/api/wallet/global-session', methods=['POST', 'OPTIONS'])
def check_global_session():
    """
    Deprecated cross-device session check.

    Cross-device "one passkey per day" sync was removed; wallet unlock is now
    local-per-device. This endpoint is retained for backward compatibility with
    older SDKs and always reports no active global session, so callers fall back
    to the local unlock flow. No global wallet_id is stored or broadcast.
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

    response = jsonify({
        'success': True,
        'valid': False,
        'deprecated': True,
        'message': 'Cross-device session sync removed; unlock is local-per-device'
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
    device_id = (body.get("device_id") or "").strip()
    payload = issue_wallet_challenge(wallet_id=wallet_id, device_id=device_id)
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
        device_id=(body.get("device_id") or "legacy").strip() or "legacy",
        device_name=(body.get("device_name") or "").strip(),
        pubkey_b64=(body.get("pubkey") or "").strip(),
        signature_b64=(body.get("signature") or "").strip(),
        enrollment_grant=(body.get("enrollment_grant") or "").strip(),
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


@wallet_session_sync_bp.route("/api/wallet/revoke-device", methods=["POST"])
@cross_origin()
def wallet_revoke_device():
    """Revoke a single enrolled device signing key."""
    from api.wallet_authn import assertion_error_response, revoke_wallet_device, verify_assertion_from_body

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not wallet_id or not device_id:
        return jsonify({"success": False, "error": "wallet_id and device_id required"}), 400

    verify_result, _fields = verify_assertion_from_body(
        body,
        wallet_id=wallet_id,
        field_names=["wallet_id", "device_id"],
    )
    if not verify_result.ok:
        return assertion_error_response(verify_result)

    result = revoke_wallet_device(wallet_id=wallet_id, device_id=device_id)
    if not result.ok:
        return jsonify({"success": False, "error": result.error, "code": result.code}), 403
    response = jsonify({"success": True, "revoked": True, "device_id": device_id})
    response.headers.update(_cors_headers(request.headers.get("Origin")))
    return response


@wallet_session_sync_bp.route("/api/wallet/register-device-passkey", methods=["POST"])
@cross_origin()
def wallet_register_device_passkey():
    """Bind a wallet-scoped WebAuthn passkey to a device enrollment."""
    from api.database import SessionLocal, WalletPasskey
    from api.fresh_passkey_attestation import extract_cose_public_key_b64
    from api.wallet_authn import assertion_error_response, verify_assertion_from_body

    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    credential_id = (body.get("credential_id") or "").strip()
    public_key = (body.get("public_key") or "").strip()
    attestation_object = (body.get("attestation_object") or "").strip()
    attestation_format = (body.get("attestation_format") or "").strip() or None
    device_name = (body.get("device_name") or "").strip() or None

    if not wallet_id or not device_id or not credential_id or not public_key:
        return jsonify({"success": False, "error": "missing_passkey_fields"}), 400

    stored_public_key = public_key
    if attestation_object:
        try:
            stored_public_key = extract_cose_public_key_b64(attestation_object)
        except Exception as exc:
            logger.warning("Wallet passkey COSE extraction failed: %s", exc)

    verify_result, _fields = verify_assertion_from_body(
        body,
        wallet_id=wallet_id,
        field_names=["wallet_id", "device_id", "credential_id"],
    )
    if not verify_result.ok:
        return assertion_error_response(verify_result)

    db = SessionLocal()
    try:
        existing = db.query(WalletPasskey).filter_by(credential_id=credential_id).first()
        if existing and existing.revoked_at:
            return jsonify({"success": False, "error": "passkey_revoked"}), 403
        if not existing:
            db.add(
                WalletPasskey(
                    wallet_id=wallet_id,
                    device_id=device_id,
                    credential_id=credential_id,
                    public_key=stored_public_key,
                    attestation_format=attestation_format,
                    device_name=device_name,
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow(),
                )
            )
        else:
            if attestation_object and stored_public_key:
                existing.public_key = stored_public_key
            existing.last_used_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    response = jsonify({"success": True, "registered": True})
    response.headers.update(_cors_headers(request.headers.get("Origin")))
    return response


# ============================================================
# PRIVACY MODEL
# ============================================================
# - Session (unlock status): Server cookie (stateless JWT), local-per-device
# - Credentials: LOCAL ONLY in each site's IndexedDB
# - Server stores: wallet_id + timestamps ONLY (no user identity, no site visits)
# - Cross-device sync: REMOVED (no global wallet_id stored or broadcast)
# - Redirect auth (v2.30.0+): CLIENT-SIDE ENCRYPTION - wallet secret never touches server
#   * SDK generates encryption key, stores locally
#   * lemma.id client-side JS encrypts wallet data
#   * Encrypted blob returned in URL, decrypted by SDK
#   * Server NEVER sees the wallet_secret or which sites user authenticates to
# - Legacy redirect tokens: For old SDK versions, server stores wallet_secret for 60s
#   * return_url is NOT stored (privacy improvement)
# ============================================================
