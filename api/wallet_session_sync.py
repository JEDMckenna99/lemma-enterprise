"""
Wallet Session Sync API

Enables the "One Passkey Per Day" experience by syncing wallet sessions
across sites via secure cookies.

FLOW:
1. User unlocks wallet on lemma.id → Session cookie set (24hr)
2. User visits third-party site → SDK calls /api/wallet/session-sync
3. Cookie validated → Session + credentials returned
4. SDK stores locally → All verifications are local (0 network calls)

PRIVACY:
- No email required
- Credentials are signed blobs (lemma.id can't read contents)
- Only sync calls are logged (not verifications)
"""

from flask import Blueprint, request, jsonify, make_response
import time
import hashlib
import hmac
import os
import json

wallet_session_sync_bp = Blueprint('wallet_session_sync', __name__)

# Session configuration
SESSION_COOKIE_NAME = 'lemma_wallet_session'
SESSION_DURATION = 24 * 60 * 60  # 24 hours in seconds
SESSION_SECRET = os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production')


def generate_session_token(wallet_id: str, unlocked_at: int) -> str:
    """Generate a secure session token for the cookie."""
    payload = f"{wallet_id}:{unlocked_at}:{int(time.time())}"
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
        if len(parts) != 4:
            return None
        
        wallet_id, unlocked_at, created_at, signature = parts
        unlocked_at = int(unlocked_at)
        created_at = int(created_at)
        
        # Verify signature
        payload = f"{wallet_id}:{unlocked_at}:{created_at}"
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
    except Exception as e:
        print(f"Session token validation error: {e}")
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
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    # Get session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_token:
        response = jsonify({
            'success': False,
            'error': 'no_session',
            'message': 'No wallet session. User needs to unlock wallet on lemma.id',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        })
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
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
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    # Get requesting site for credential filtering
    requesting_origin = request.headers.get('Origin', '')
    requesting_site = requesting_origin.replace('https://', '').replace('http://', '').split(':')[0]
    
    # Fetch user's credentials from database
    # For now, return session without credentials (credentials will come from server-side storage)
    # In production, query the credentials table for this wallet_id
    
    try:
        from database import db
        
        # Get user by wallet_id
        user = db.get_user_by_wallet_id(session_data['wallet_id'])
        
        credentials = []
        if user:
            # Get permissions/credentials for this user
            # Filter by requesting site if needed
            all_credentials = db.get_user_credentials(user.id) or []
            
            for cred in all_credentials:
                # Include credential if it matches the requesting site
                # or if it's a global credential (no site restriction)
                cred_site = cred.get('claims', {}).get('siteId', '')
                if not cred_site or cred_site == requesting_site or requesting_site.endswith(cred_site):
                    credentials.append(cred)
        
        response_data = {
            'success': True,
            'session': {
                'valid': True,
                'wallet_id': session_data['wallet_id'],
                'unlocked_at': session_data['unlocked_at'],
                'expires_at': session_data['expires_at'],
                'time_remaining': session_data['expires_at'] - int(time.time())
            },
            'credentials': credentials,
            'synced_at': int(time.time() * 1000)
        }
        
    except Exception as e:
        print(f"Error fetching credentials: {e}")
        # Return session without credentials on error
        response_data = {
            'success': True,
            'session': {
                'valid': True,
                'wallet_id': session_data['wallet_id'],
                'unlocked_at': session_data['unlocked_at'],
                'expires_at': session_data['expires_at'],
                'time_remaining': session_data['expires_at'] - int(time.time())
            },
            'credentials': [],
            'synced_at': int(time.time() * 1000),
            'note': 'Credentials not available from server, use local wallet'
        }
    
    response = jsonify(response_data)
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


@wallet_session_sync_bp.route('/api/wallet/set-session', methods=['POST'])
def set_session():
    """
    Set wallet session cookie after successful passkey unlock.
    Called from lemma.id pages after wallet unlock.
    
    Request body:
        - wallet_id: The user's wallet ID
        - unlocked_at: Timestamp of unlock
    """
    data = request.get_json() or {}
    wallet_id = data.get('wallet_id')
    unlocked_at = data.get('unlocked_at', int(time.time() * 1000))
    
    if not wallet_id:
        return jsonify({'success': False, 'error': 'wallet_id required'}), 400
    
    # Generate session token
    token = generate_session_token(wallet_id, unlocked_at)
    
    # Create response with cookie
    response = jsonify({
        'success': True,
        'session_set': True,
        'expires_at': int(time.time()) + SESSION_DURATION
    })
    
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
    
    return response


@wallet_session_sync_bp.route('/api/wallet/clear-session', methods=['POST'])
def clear_session():
    """Clear wallet session cookie (logout)."""
    response = jsonify({'success': True, 'session_cleared': True})
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')
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
    except Exception as e:
        print(f"Database connection error: {e}")
    return None


def _store_credential_db(wallet_id: str, credential: dict) -> bool:
    """Store credential in database."""
    conn = _get_db_connection()
    if not conn:
        print("⚠️ No database connection, credential not persisted")
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
        
    except Exception as e:
        print(f"Error storing credential: {e}")
        if conn:
            conn.close()
        return False


def _get_credentials_db(wallet_id: str) -> list:
    """Get all credentials for a wallet from database."""
    conn = _get_db_connection()
    if not conn:
        print("⚠️ No database connection, returning empty credentials")
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
        
    except Exception as e:
        print(f"Error fetching credentials: {e}")
        if conn:
            conn.close()
        return []


@wallet_session_sync_bp.route('/api/wallet/sync-credential', methods=['POST', 'OPTIONS'])
def sync_credential():
    """
    Sync a credential to the server for cross-site availability.
    
    Called by the bridge when storing credentials from third-party sites.
    This ensures credentials are available when viewing lemma.id/wallet.
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # Get session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        response = jsonify({'success': False, 'error': 'not_authenticated'})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    session_data = validate_session_token(session_token)
    if not session_data:
        response = jsonify({'success': False, 'error': 'session_expired'})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    wallet_id = session_data['wallet_id']
    data = request.get_json() or {}
    credential = data.get('credential')
    
    if not credential:
        response = jsonify({'success': False, 'error': 'no_credential_provided'})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 400
    
    # Store credential in database
    stored = _store_credential_db(wallet_id, credential)
    
    if stored:
        print(f"✅ Credential synced to database: {credential.get('id')} for wallet {wallet_id}")
    
    # Get updated count
    all_creds = _get_credentials_db(wallet_id)
    
    response = jsonify({
        'success': True,
        'synced': stored,
        'credential_id': credential.get('id'),
        'total_credentials': len(all_creds)
    })
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


@wallet_session_sync_bp.route('/api/wallet/get-credentials', methods=['GET', 'OPTIONS'])
def get_credentials():
    """
    Get all credentials for the authenticated wallet.
    
    Used by lemma.id/wallet to display unified credential list.
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # Get session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        response = jsonify({'success': False, 'error': 'not_authenticated', 'credentials': []})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    session_data = validate_session_token(session_token)
    if not session_data:
        response = jsonify({'success': False, 'error': 'session_expired', 'credentials': []})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    wallet_id = session_data['wallet_id']
    
    # Fetch from database
    credentials = _get_credentials_db(wallet_id)
    print(f"📥 Fetched {len(credentials)} credentials from database for wallet {wallet_id}")
    
    response = jsonify({
        'success': True,
        'credentials': credentials,
        'count': len(credentials)
    })
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


@wallet_session_sync_bp.route('/api/wallet/revoke-credential', methods=['POST', 'OPTIONS'])
def revoke_credential():
    """
    Revoke a credential from the server sync storage.
    
    Called when user revokes a credential from the wallet page.
    This removes it from the unified wallet view.
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # Get session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        response = jsonify({'success': False, 'error': 'not_authenticated'})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    session_data = validate_session_token(session_token)
    if not session_data:
        response = jsonify({'success': False, 'error': 'session_expired'})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 401
    
    wallet_id = session_data['wallet_id']
    data = request.get_json() or {}
    credential_id = data.get('credential_id')
    
    if not credential_id:
        response = jsonify({'success': False, 'error': 'credential_id required'})
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 400
    
    # Revoke from database
    revoked = _revoke_credential_db(wallet_id, credential_id)
    
    if revoked:
        print(f"🗑️ Credential revoked from database: {credential_id} for wallet {wallet_id}")
    
    response = jsonify({
        'success': True,
        'revoked': revoked,
        'credential_id': credential_id
    })
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


def _revoke_credential_db(wallet_id: str, credential_id: str) -> bool:
    """Mark credential as revoked in database (or delete it)."""
    conn = _get_db_connection()
    if not conn:
        print("⚠️ No database connection, credential not revoked from server")
        return False
    
    try:
        cur = conn.cursor()
        
        # Option 1: Delete the credential entirely
        cur.execute("""
            DELETE FROM wallet_credentials 
            WHERE wallet_id = %s AND credential_id = %s
        """, (wallet_id, credential_id))
        
        deleted = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
        return deleted
        
    except Exception as e:
        print(f"Error revoking credential: {e}")
        if conn:
            conn.close()
        return False
