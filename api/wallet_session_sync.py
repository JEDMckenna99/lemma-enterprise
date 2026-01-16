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


# Database-backed credential storage
# Uses wallet_credentials table for persistent, scalable storage

def _get_db_connection():
    """Get database connection."""
    try:
        import psycopg2
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            # Heroku uses postgres:// but psycopg2 needs postgresql://
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            return psycopg2.connect(database_url, sslmode='require')
    except Exception:
        pass  # PRIVACY: Silent failure
    return None


def _store_credential_db(wallet_id: str, credential: dict) -> bool:
    """Store credential in database."""
    conn = _get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Extract metadata from credential
        cred_id = credential.get('id', '')
        site_id = credential.get('claims', {}).get('siteId', credential.get('claims', {}).get('site_id', ''))
        site_domain = credential.get('claims', {}).get('siteDomain', site_id)
        package_type = credential.get('packageType', 'permission')
        
        # Upsert credential
        cur.execute("""
            INSERT INTO wallet_credentials (wallet_id, credential_id, site_id, site_domain, credential_data, package_type, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (wallet_id, credential_id) 
            DO UPDATE SET 
                credential_data = EXCLUDED.credential_data,
                site_domain = EXCLUDED.site_domain,
                updated_at = NOW()
        """, (wallet_id, cred_id, site_id, site_domain, json.dumps(credential), package_type))
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except Exception:
        if conn:
            conn.close()
        return False


def _get_credentials_db(wallet_id: str) -> list:
    """Get all credentials for a wallet from database."""
    conn = _get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT credential_data FROM wallet_credentials 
            WHERE wallet_id = %s AND revoked = FALSE
            ORDER BY created_at DESC
        """, (wallet_id,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        credentials = []
        for row in rows:
            try:
                cred = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                credentials.append(cred)
            except:
                pass
        
        return credentials
        
    except Exception:
        if conn:
            conn.close()
        return []


@wallet_session_sync_bp.route('/api/wallet/sync-credential', methods=['POST', 'OPTIONS'])
def sync_credential():
    """
    DEPRECATED: Credential sync to server is disabled for privacy.
    
    Credentials are stored locally in each site's IndexedDB.
    This endpoint returns success but does NOT store credentials on the server.
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
    
    # PRIVACY: Return success but don't store anything
    # Credentials stay in local IndexedDB only
    data = request.get_json() or {}
    credential = data.get('credential', {})
    
    response = jsonify({
        'success': True,
        'synced': False,  # Not actually synced to server
        'credential_id': credential.get('id'),
        'note': 'Credentials stored locally only (privacy mode)'
    })
    response.headers.update(_cors_headers(origin))
    return response


@wallet_session_sync_bp.route('/api/wallet/revoke-credential', methods=['POST', 'OPTIONS'])
def revoke_credential():
    """
    DEPRECATED: Server-side revocation is disabled for privacy.
    
    Credentials are managed locally in each site's IndexedDB.
    This endpoint returns success but does NOT modify any server data.
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
    credential_id = data.get('credential_id')
    
    # PRIVACY: Return success but don't modify anything on server
    # Revocation is handled locally in IndexedDB
    response = jsonify({
        'success': True,
        'revoked': True,  # Assumed revoked locally
        'credential_id': credential_id,
        'note': 'Credentials managed locally only (privacy mode)'
    })
    response.headers.update(_cors_headers(origin))
    return response


def _revoke_credential_db(wallet_id: str, credential_id: str) -> bool:
    """Mark credential as revoked in database (soft delete)."""
    conn = _get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Soft delete - mark as revoked with timestamp
        cur.execute("""
            UPDATE wallet_credentials 
            SET revoked = TRUE, revoked_at = NOW(), updated_at = NOW()
            WHERE wallet_id = %s AND credential_id = %s
        """, (wallet_id, credential_id))
        
        affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return affected > 0
        
    except Exception:
        if conn:
            conn.close()
        return False


@wallet_session_sync_bp.route('/api/wallet/get-credentials', methods=['GET', 'OPTIONS'])
def get_credentials():
    """
    DEPRECATED: Server-side credential storage is disabled for privacy.
    
    Credentials are stored locally in each site's IndexedDB.
    This endpoint returns empty list - use local IndexedDB instead.
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
    
    # PRIVACY: Return empty - credentials are stored locally only
    response = jsonify({
        'success': True,
        'credentials': [],
        'count': 0,
        'note': 'Credentials stored locally only (privacy mode). Use wallet.getCredentials() for local credentials.'
    })
    response.headers.update(_cors_headers(origin))
    return response
