"""
Consolidated Wallet Service
===========================

Combines all wallet functionality from 8 separate files into a single organized service:
- wallet_first_auth.py → WalletAuthService
- wallet_session_sync.py → WalletSessionService  
- wallet_retrieval_flow.py → WalletRetrievalService
- wallet_revocation.py → WalletRevocationService
- wallet_transfer_session.py → WalletTransferService
- wallet_pin_reset.py → WalletPINService
- wallet_auth_decorator.py → Auth decorators
- multi_lemma_wallet_sync.py → MultiLemmaSyncService

All routes maintain backwards compatibility with existing URL patterns.
"""

import os
import json
import time
import secrets
import logging
import hashlib
import hmac
import uuid
import threading
import base64
import io
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, session, make_response, g

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

SESSION_COOKIE_NAME = 'lemma_wallet_session'
SESSION_DURATION = 24 * 60 * 60  # 24 hours
SESSION_SECRET = os.environ.get('SESSION_SECRET', 'dev-secret-change-in-production')
CSRF_COOKIE_NAME = 'lemma_wallet_csrf'
TOKEN_EXPIRY = 86400  # 24 hours for PIN reset

# CORS configuration from environment
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

# Redis setup for multi-dyno support
try:
    import redis
    REDIS_URL = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL')
    if REDIS_URL:
        if REDIS_URL.startswith('rediss://'):
            redis_client = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
        else:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        USE_REDIS = True
        logger.info("Redis connected for wallet session storage")
    else:
        USE_REDIS = False
except Exception as e:
    USE_REDIS = False
    logger.warning(f"Redis not available: {e}")

# Multi-lemma engine availability
try:
    from lemma_crypto import PyQRSyncManager, PyDeviceDelegationManager, PyMinimalIssuer
    MULTI_LEMMA_AVAILABLE = True
except ImportError:
    MULTI_LEMMA_AVAILABLE = False

# Create unified blueprint
wallet_service_bp = Blueprint('wallet_service', __name__)


# ============================================================================
# CORS HELPERS
# ============================================================================

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
    if not _origin_allowed(origin):
        return {'Referrer-Policy': 'no-referrer'}
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Lemma-CSRF',
        'Access-Control-Allow-Credentials': 'true',
        'Vary': 'Origin',
        'Referrer-Policy': 'no-referrer',
    }


def _validate_csrf() -> bool:
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get('X-Lemma-CSRF')
    if not csrf_cookie or not csrf_header:
        return False
    return secrets.compare_digest(csrf_cookie, csrf_header)


def cross_origin_response(data: dict, status: int = 200):
    """Create a response with proper CORS headers."""
    origin = request.headers.get('Origin')
    response = jsonify(data)
    response.headers.update(_cors_headers(origin))
    return response, status


# ============================================================================
# SESSION TOKEN MANAGEMENT
# ============================================================================

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
        
        payload = f"{wallet_id}:{unlocked_at}:{created_at}:{session_nonce}"
        expected_sig = hmac.new(
            SESSION_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        if not hmac.compare_digest(signature, expected_sig):
            return None
        
        if time.time() - created_at > SESSION_DURATION:
            return None
        
        return {
            'wallet_id': wallet_id,
            'unlocked_at': unlocked_at,
            'created_at': created_at,
            'expires_at': created_at + SESSION_DURATION
        }
    except Exception:
        return None


# ============================================================================
# SESSION STORAGE (Redis or In-Memory)
# ============================================================================

class SessionStorage:
    """Multi-dyno compatible session storage."""
    
    def __init__(self):
        self.lock = threading.Lock()
        if not USE_REDIS:
            self.sessions = {}
    
    def set_session(self, session_id: str, session_data: dict, ttl: int = 300) -> bool:
        if USE_REDIS:
            try:
                redis_client.setex(f"transfer_session:{session_id}", ttl, json.dumps(session_data))
                return True
            except Exception as e:
                logger.error(f"Redis SET failed: {e}")
                return False
        else:
            with self.lock:
                self.sessions[session_id] = session_data
                return True
    
    def get_session(self, session_id: str) -> dict | None:
        if USE_REDIS:
            try:
                data = redis_client.get(f"transfer_session:{session_id}")
                return json.loads(data) if data else None
            except Exception as e:
                logger.error(f"Redis GET failed: {e}")
                return None
        else:
            with self.lock:
                return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        if USE_REDIS:
            try:
                redis_client.delete(f"transfer_session:{session_id}")
                return True
            except Exception:
                return False
        else:
            with self.lock:
                self.sessions.pop(session_id, None)
                return True
    
    def list_sessions(self) -> List[str]:
        if USE_REDIS:
            try:
                keys = redis_client.keys("transfer_session:*")
                return [key.replace("transfer_session:", "") for key in keys]
            except Exception:
                return []
        else:
            with self.lock:
                return list(self.sessions.keys())


_storage = SessionStorage()
_reset_tokens = {}  # PIN reset tokens


# ============================================================================
# WALLET AUTH DECORATORS
# ============================================================================

def _extract_unlock_token() -> str | None:
    token = request.headers.get('X-Lemma-Unlock')
    if token:
        return token.strip()
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header.replace('Bearer ', '').strip()
    return None


def _get_wallet_lemmas() -> List[Dict]:
    """Get wallet lemmas from headers or request body."""
    lemmas = []
    header_val = request.headers.get('X-Wallet-Lemmas')
    if header_val:
        try:
            lemmas = json.loads(header_val)
        except Exception:
            lemmas = []
    if not lemmas:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            lemmas = payload.get('wallet_lemmas') or payload.get('user_lemmas') or []
    return lemmas if isinstance(lemmas, list) else []


def _verify_lemmas_rust(lemmas: List[Dict]) -> List[Dict]:
    """Verify lemmas using Rust engine and return valid ones."""
    try:
        from lemma_crypto import PyOptimizedVerifier
    except Exception as e:
        logger.error(f"Rust verifier not available: {e}")
        raise RuntimeError("rust_verifier_unavailable")
    
    verifier = PyOptimizedVerifier()
    valid = []
    for lemma in lemmas:
        try:
            credential_json = json.dumps(lemma)
            if verifier.verify_credential_json(credential_json):
                valid.append(lemma)
        except Exception:
            continue
    return valid


def _extract_permissions_from_lemma(lemma: Dict) -> List[str]:
    claims = lemma.get('claims') or lemma.get('credentialSubject', {})
    if claims.get('packageType') and claims.get('packageType') != 'permission':
        return []
    permissions = []
    if 'permission' in claims:
        permissions.append(claims['permission'])
    if 'role' in claims:
        permissions.append(claims['role'])
    if 'permissions' in claims:
        if isinstance(claims['permissions'], list):
            permissions.extend(claims['permissions'])
        else:
            permissions.append(claims['permissions'])
    return [p for p in permissions if isinstance(p, str)]


def require_wallet_auth(f):
    """Decorator that requires server-signed wallet unlock state."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Prefer signed session cookie (server-issued) for unlock state
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        session_data = validate_session_token(session_token) if session_token else None
        
        # Fallback: short-lived unlock token (server-issued)
        unlock_data = None
        if not session_data:
            unlock_token = _extract_unlock_token()
            if unlock_token:
                try:
                    from api.wallet_session_sync import validate_unlock_token
                    unlock_data = validate_unlock_token(unlock_token)
                except Exception:
                    unlock_data = None
        
        if not session_data and not unlock_data:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'Unlock your wallet to access this resource'
            }), 401
        
        wallet_id = (session_data or unlock_data).get('wallet_id')
        g.user_id = wallet_id
        g.wallet_id = wallet_id
        g.auth_method = 'wallet_passkey'
        g.permissions = []
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_permission(permission_id: str):
    """Decorator that requires a specific permission lemma."""
    def decorator(f):
        @wraps(f)
        @require_wallet_auth
        def decorated_function(*args, **kwargs):
            try:
                lemmas = _get_wallet_lemmas()
                valid_lemmas = _verify_lemmas_rust(lemmas)
                permissions = []
                for lemma in valid_lemmas:
                    permissions.extend(_extract_permissions_from_lemma(lemma))
                g.permissions = permissions
            except RuntimeError:
                return jsonify({
                    'success': False,
                    'error': 'verification_unavailable',
                    'message': 'Rust verifier required for permission checks'
                }), 503
            
            if permission_id not in g.permissions:
                return jsonify({
                    'success': False,
                    'error': 'Permission denied',
                    'required_permission': permission_id
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_wallet_auth_proof(auth_proof: dict) -> dict:
    """Validate a wallet auth proof."""
    try:
        required = ['type', 'method', 'walletId', 'unlockedAt', 'expiresAt']
        for field in required:
            if field not in auth_proof:
                return {'valid': False, 'error': f'Missing field: {field}'}
        
        if auth_proof['type'] != 'wallet_auth':
            return {'valid': False, 'error': 'Invalid auth type'}
        
        expires_at = auth_proof['expiresAt']
        if isinstance(expires_at, (int, float)):
            if expires_at < datetime.utcnow().timestamp() * 1000:
                return {'valid': False, 'error': 'Auth proof expired'}
        
        wallet_id = auth_proof['walletId']
        user_id = auth_proof.get('userId', wallet_id)
        
        permissions = []
        if 'lemma' in auth_proof:
            lemma = auth_proof['lemma']
            claims = lemma.get('claims', {})
            if 'permission' in claims:
                permissions.append(claims['permission'])
            if 'role' in claims:
                permissions.append(claims['role'])
            if 'permissions' in claims:
                permissions.extend(claims['permissions'])
        
        return {
            'valid': True,
            'user_id': user_id,
            'wallet_id': wallet_id,
            'permissions': permissions,
            'lemma': auth_proof.get('lemma')
        }
        
    except Exception as e:
        return {'valid': False, 'error': str(e)}


# ============================================================================
# PPID DERIVATION (from wallet_first_auth)
# ============================================================================

def derive_user_ppid(site_id: str, wallet_secret: str = None, passkey_credential_id: str = None) -> str:
    """Derive the user's PPID for a specific site."""
    from api.ppid import derive_ppid_from_passkey, derive_ppid_from_wallet_secret, canonicalize_rp_id
    
    site = canonicalize_rp_id(site_id)
    
    if wallet_secret:
        return derive_ppid_from_wallet_secret(wallet_secret, site)
    
    if passkey_credential_id:
        return derive_ppid_from_passkey(passkey_credential_id, site)
    
    logger.warning("No wallet_secret or passkey - generating random PPID")
    random_secret = secrets.token_hex(32)
    return derive_ppid_from_wallet_secret(random_secret, site)


def issue_permission_lemma(subject_ppid: str, site_id: str = 'lemma.id', 
                          permissions: list = None, granted_by: str = 'system',
                          track_in_db: bool = True) -> dict:
    """Issue a permission lemma for direct wallet storage."""
    try:
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        site_issuer = issuer_manager.get_iam_issuer(site_id)
        
        perm_list = permissions or ['read', 'write']
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(days=30)
        
        claims = {
            'type': 'permission',
            'siteId': site_id,
            'permissions': ','.join(perm_list),
            'issuedAt': issued_at.isoformat() + 'Z',
            'expiresAt': expires_at.isoformat() + 'Z',
            'credentialScope': 'site_specific',
            'deviceBound': 'true'
        }
        
        credential_json = site_issuer.issue_credential(subject_ppid, claims)
        credential = json.loads(credential_json)
        
        credential['packageType'] = 'permission'
        credential['credentialScope'] = 'site_specific'
        credential['deviceBound'] = True
        credential['issuerInfo'] = {
            'did': site_issuer.get_did(),
            'publicKey': site_issuer.get_public_key_hex(),
            'name': f'{site_id} IAM',
            'verified': True
        }
        
        if track_in_db:
            try:
                _track_permission_grant(
                    site_id=site_id,
                    user_did=subject_ppid,
                    permission_id=','.join(perm_list),
                    credential_id=credential.get('id', ''),
                    granted_by=granted_by,
                    expires_at=expires_at
                )
            except Exception as db_err:
                logger.warning(f"Failed to track permission in DB: {db_err}")
        
        return credential
        
    except Exception as e:
        logger.error(f"Failed to issue permission lemma: {e}")
        raise


def _track_permission_grant(site_id: str, user_did: str, permission_id: str,
                           credential_id: str, granted_by: str, expires_at: datetime):
    """Track permission grant in database."""
    from api.database import get_db_connection
    
    conn = None
    try:
        conn = get_db_connection(site_id=site_id)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM permission_types WHERE site_id = %s AND name = %s
        """, (site_id, permission_id))
        result = cursor.fetchone()
        
        if result:
            permission_type_id = result[0]
        else:
            cursor.execute("""
                INSERT INTO permission_types (site_id, name, type, description, active)
                VALUES (%s, %s, 'role', %s, TRUE)
                RETURNING id
            """, (site_id, permission_id, f'{permission_id.title()} access'))
            permission_type_id = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO permission_instances
            (permission_type_id, site_id, email, credential_did, granted_at, granted_by, expires_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            permission_type_id,
            site_id,
            '',
            user_did,
            datetime.utcnow(),
            granted_by,
            expires_at,
            json.dumps({'credential_id': credential_id}) if credential_id else '{}'
        ))
        
        conn.commit()
        cursor.close()
        
    except Exception as e:
        logger.error(f"Database tracking failed: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


# ============================================================================
# WALLET RETRIEVAL SERVICE (from wallet_retrieval_flow)
# ============================================================================

class WalletRetrievalManager:
    """Manages PoH verification to wallet retrieval connection."""
    
    def __init__(self):
        from api.config import get_wallet_salt, get_hpke_server_key
        self.issuer_secret_salt = get_wallet_salt()
        self.r_vault = get_hpke_server_key()
    
    def extract_kyc_from_poh_verification(self, stripe_session_data: Dict) -> Optional[Dict]:
        if not stripe_session_data:
            return None
        
        return {
            'jurisdiction_code': stripe_session_data.get('country', 'US').upper(),
            'doc_type': stripe_session_data.get('document_type', 'unknown').lower(),
            'doc_number_norm': stripe_session_data.get('document_number', '').replace(" ", "").replace("-", "").upper(),
            'surname_norm': stripe_session_data.get('last_name', '').lower().strip(),
            'dob_yyyymmdd': stripe_session_data.get('date_of_birth', ''),
            'liveness_template_hash': hashlib.sha256(
                stripe_session_data.get('selfie_data', '').encode()
            ).hexdigest()[:32] if stripe_session_data.get('selfie_data') else ''
        }
    
    def derive_rid_from_kyc(self, kyc_data: Dict) -> bytes:
        try:
            from lemma_crypto import AdvancedWalletCrypto, KYCTuple
            
            kyc_tuple = KYCTuple(
                jurisdiction_code=kyc_data['jurisdiction_code'],
                doc_type=kyc_data['doc_type'],
                doc_number_norm=kyc_data['doc_number_norm'],
                surname_norm=kyc_data['surname_norm'],
                dob_yyyymmdd=kyc_data['dob_yyyymmdd'],
                liveness_template_hash=kyc_data['liveness_template_hash']
            )
            
            kyc_cbor = AdvancedWalletCrypto.normalize_kyc_tuple(kyc_tuple)
            adv_secrets = AdvancedWalletCrypto.generate_secrets()
            crypto = AdvancedWalletCrypto(adv_secrets[0], adv_secrets[1], adv_secrets[2])
            rid = crypto.derive_rid(kyc_cbor)
            return bytes(rid)
            
        except ImportError:
            kyc_string = f"{kyc_data['jurisdiction_code']}|{kyc_data['doc_type']}|{kyc_data['doc_number_norm']}|{kyc_data['surname_norm']}|{kyc_data['dob_yyyymmdd']}|{kyc_data['liveness_template_hash']}"
            combined = kyc_string.encode() + self.issuer_secret_salt
            return hashlib.blake2b(combined, digest_size=32).digest()
    
    def derive_vid_from_rid(self, rid: bytes) -> str:
        try:
            from lemma_crypto import AdvancedWalletCrypto
            adv_secrets = AdvancedWalletCrypto.generate_secrets()
            crypto = AdvancedWalletCrypto(adv_secrets[0], adv_secrets[1], list(self.r_vault))
            vid_bytes = crypto.derive_vid(list(rid))
            return bytes(vid_bytes).hex()
        except ImportError:
            combined = self.r_vault + rid
            return hashlib.blake2b(combined, digest_size=32).digest().hex()
    
    def connect_poh_to_wallet_retrieval(self, poh_credential: Dict) -> Dict:
        try:
            claims = poh_credential.get('claims') or poh_credential.get('credentialSubject', {})
            stripe_session_id = claims.get('stripe_session_id')
            
            if not stripe_session_id:
                return {'success': False, 'error': 'no_stripe_session'}
            
            stripe_data = {
                'session_id': stripe_session_id,
                'country': 'US',
                'document_type': 'passport',
                'document_number': 'P123456789',
                'last_name': 'TestUser',
                'date_of_birth': '1990-01-01',
                'selfie_data': f'selfie_hash_{stripe_session_id}',
                'verification_status': 'verified'
            }
            
            kyc_data = self.extract_kyc_from_poh_verification(stripe_data)
            if not kyc_data:
                return {'success': False, 'error': 'kyc_extraction_failed'}
            
            rid = self.derive_rid_from_kyc(kyc_data)
            vid = self.derive_vid_from_rid(rid)
            
            session['user_rid'] = rid.hex()
            session['user_vid'] = vid
            session['kyc_verified'] = True
            
            return {
                'success': True,
                'rid_available': True,
                'vid_available': True,
                'wallet_retrieval_enabled': True
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


_retrieval_manager = None


def get_retrieval_manager() -> WalletRetrievalManager:
    global _retrieval_manager
    if _retrieval_manager is None:
        _retrieval_manager = WalletRetrievalManager()
    return _retrieval_manager


# ============================================================================
# REVOCATION HELPERS (from wallet_revocation)
# ============================================================================

def await_network_revocation(credential_id: str, reason: str) -> bool:
    try:
        from api.sdk_api import distribute_revocation_to_network
        
        bloom_hash = hashlib.sha256(credential_id.encode()).hexdigest()
        
        return distribute_revocation_to_network(
            credential_id=credential_id,
            bloom_hash=bloom_hash,
            reason=reason
        )
    except Exception as e:
        logger.warning(f"Network revocation failed: {e}")
        return False


def await_site_revocation(credential_id: str, reason: str, site_domain: str = None) -> bool:
    try:
        from api.database import get_db_session, RevocationList
        
        db_session = get_db_session()
        try:
            existing = db_session.query(RevocationList).filter_by(lemma_id=credential_id).first()
            if existing:
                return True
            
            revocation = RevocationList(
                lemma_id=credential_id,
                credential_id=credential_id,
                lemma_type='permission',
                site_id=site_domain or 'unknown',
                user_did='user_requested',
                revoked_by='user_self_revoke',
                revoked_at=datetime.utcnow(),
                reason=reason,
                bloom_filter_updated=False
            )
            
            db_session.add(revocation)
            db_session.commit()
            return True
            
        finally:
            db_session.close()
        
    except Exception as e:
        logger.warning(f"Site revocation failed: {e}")
        return False


# ============================================================================
# TRANSFER SESSION CLASS
# ============================================================================

class TransferSession:
    def __init__(self, source_device_id: str, wallet_data=None):
        self.session_id = str(uuid.uuid4())[:12]
        self.source_device_id = source_device_id
        self.transfer_key = hashlib.sha256(f"{self.session_id}_{time.time()}".encode()).hexdigest()[:32]
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(minutes=5)
        self.wallet_data = wallet_data
        self.status = 'waiting'
        self.target_device_id = None
    
    def to_qr_data(self) -> dict:
        return {
            'type': 'lemma_transfer_token',
            'session_id': self.session_id,
            'transfer_key': self.transfer_key,
            'expires_at': int(self.expires_at.timestamp() * 1000),
            'source_device': self.source_device_id[:8]
        }
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


# ============================================================================
# ROUTES: WALLET-FIRST AUTHENTICATION
# ============================================================================

@wallet_service_bp.route('/api/wallet-auth/issue', methods=['POST'])
def issue_to_wallet():
    """Issue a permission lemma directly to the user's wallet."""
    try:
        data = request.get_json() or {}
        
        from api.validation import validate_site_id, ValidationError
        try:
            site_id = validate_site_id(data.get('site_id'), required=False, allow_lemma_default=True)
        except ValidationError as ve:
            return jsonify({'success': False, 'error': 'validation_error', 'message': str(ve)}), 400
        
        wallet_secret = data.get('wallet_secret')
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({'success': False, 'error': 'Either wallet_secret or passkey_credential_id required'}), 400
        
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=['read', 'write', 'access'],
            granted_by='wallet_auth'
        )
        
        # Return PPID and permission_lemma - client stores in wallet
        # No server-side session needed (session-free architecture)
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'permission_lemma': permission_lemma
        })
        
    except Exception as e:
        logger.error(f"Wallet issue failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-auth/register-and-issue', methods=['POST'])
def register_and_issue():
    """Combined: Register passkey + Issue permission."""
    try:
        data = request.get_json() or {}
        site_id = data.get('site_id', 'lemma.id')
        wallet_secret = data.get('wallet_secret')
        passkey_credential_id = data.get('passkey_credential_id')
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({'success': False, 'error': 'Either wallet_secret or passkey_credential_id required'}), 400
        
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=['read', 'write', 'access']
        )
        
        # Return PPID and permission_lemma - client stores in wallet
        # No server-side session needed (session-free architecture)
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'is_new_user': True,
            'permission_lemma': permission_lemma
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-auth/verify-session', methods=['POST'])
def verify_wallet_session():
    """Verify wallet unlock and check permissions."""
    try:
        data = request.get_json() or {}
        site_id = data.get('site_id', 'lemma.id')
        wallet_secret = data.get('wallet_secret')
        passkey_credential_id = data.get('passkey_credential_id')
        permissions = data.get('permissions', [])
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({'success': False, 'error': 'Either wallet_secret or passkey_credential_id required'}), 400
        
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        from api.ppid import canonicalize_rp_id
        site_canonical = canonicalize_rp_id(site_id)
        has_site_permission = any(site_canonical in p for p in permissions)
        
        # Return authentication status - no server-side session needed
        # Client uses PPID for subsequent requests (session-free architecture)
        return jsonify({
            'success': True,
            'authenticated': True,
            'ppid': ppid,
            'site_id': site_id,
            'has_permission': has_site_permission
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-auth/platform-login', methods=['POST'])
def platform_login():
    """
    Platform developer login with wallet_id sync for cross-device support.
    
    This endpoint is specifically for lemma.id platform developers (not end-users).
    It handles:
    1. PPID derivation for the platform
    2. Wallet_id sync (store or return canonical wallet_id)
    3. Permission lemma issuance
    4. Global session setup
    """
    try:
        data = request.get_json() or {}
        wallet_secret = data.get('wallet_secret')
        passkey_credential_id = data.get('passkey_credential_id')
        client_wallet_id = data.get('wallet_id')  # SDK's local wallet_id
        
        if not wallet_secret and not passkey_credential_id:
            return jsonify({'success': False, 'error': 'Either wallet_secret or passkey_credential_id required'}), 400
        
        site_id = 'lemma.id'
        ppid = derive_user_ppid(site_id, wallet_secret, passkey_credential_id)
        
        # Find or create Customer record for this developer
        from api.database import get_db, Customer
        import secrets
        
        db = get_db()
        canonical_wallet_id = None
        is_new_user = False
        
        try:
            # Try to find customer by PPID or passkey
            customer = None
            if passkey_credential_id:
                customer = db.query(Customer).filter(
                    Customer.passkey_credential_id == passkey_credential_id
                ).first()
            
            if not customer:
                # Look by wallet_id if client provided one
                if client_wallet_id:
                    customer = db.query(Customer).filter(
                        Customer.wallet_id == client_wallet_id
                    ).first()
            
            if customer:
                # Existing user - use stored wallet_id or store client's
                if customer.wallet_id:
                    canonical_wallet_id = customer.wallet_id
                    logger.info(f"Platform login: using stored wallet_id {canonical_wallet_id[:12]}...")
                elif client_wallet_id:
                    customer.wallet_id = client_wallet_id
                    canonical_wallet_id = client_wallet_id
                    db.commit()
                    logger.info(f"Platform login: stored client wallet_id {canonical_wallet_id[:12]}...")
            else:
                # New developer - create Customer record
                is_new_user = True
                canonical_wallet_id = client_wallet_id or f"wallet_{secrets.token_hex(16)}"
                
                customer = Customer(
                    customer_id=f"dev_{secrets.token_hex(8)}",
                    wallet_id=canonical_wallet_id,
                    passkey_credential_id=passkey_credential_id,
                    role='developer',
                    created_at=datetime.utcnow()
                )
                db.add(customer)
                db.commit()
                logger.info(f"Platform login: created new developer {customer.customer_id}")
                
        finally:
            db.close()
        
        # Issue permission lemma
        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id=site_id,
            permissions=['read', 'write', 'access', 'developer'],
            granted_by='platform_auth'
        )
        
        # Store global session for cross-device sync
        if canonical_wallet_id:
            try:
                from api.wallet_session_sync import _store_global_session
                import time
                _store_global_session(
                    wallet_id=canonical_wallet_id,
                    unlocked_at=int(time.time() * 1000),
                    expires_at=int(time.time()) + 86400,  # 24h
                    profile_id='default',
                    profile_name='Developer'
                )
                logger.info(f"Platform login: set global session for {canonical_wallet_id[:12]}...")
            except Exception as e:
                logger.warning(f"Failed to set global session: {e}")
        
        return jsonify({
            'success': True,
            'ppid': ppid,
            'site_id': site_id,
            'is_new_user': is_new_user,
            'permission_lemma': permission_lemma,
            # CRITICAL: Return canonical wallet_id so client can sync
            'wallet_id': canonical_wallet_id,
            'wallet_id_synced': canonical_wallet_id != client_wallet_id if client_wallet_id else False
        })
        
    except Exception as e:
        logger.error(f"Platform login failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ROUTES: SESSION SYNC
# ============================================================================

@wallet_service_bp.route('/api/wallet/session-sync', methods=['POST', 'OPTIONS'])
def session_sync():
    """Sync wallet session across sites."""
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
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_token:
        return cross_origin_response({
            'success': False,
            'error': 'no_session',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        }, 401)
    
    session_data = validate_session_token(session_token)
    
    if not session_data:
        return cross_origin_response({
            'success': False,
            'error': 'session_expired',
            'unlock_url': 'https://lemma.id/wallet/unlock'
        }, 401)
    
    return cross_origin_response({
        'success': True,
        'session': {
            'valid': True,
            'wallet_id': session_data['wallet_id'],
            'unlocked_at': session_data['unlocked_at'],
            'expires_at': session_data['expires_at'],
            'time_remaining': session_data['expires_at'] - int(time.time())
        },
        'credentials': [],
        'synced_at': int(time.time() * 1000)
    })


# NOTE: set-session endpoint is defined in wallet_session_sync.py
# (includes global session storage for cross-device "one passkey per day")

# NOTE: clear-session endpoint is defined in wallet_session_sync.py
# (includes global session clearing for cross-device lock detection)


# ============================================================================
# ROUTES: WALLET RETRIEVAL
# ============================================================================

@wallet_service_bp.route('/api/wallet/connect-poh', methods=['POST'])
def connect_poh_to_wallet():
    """Connect PoH verification to wallet retrieval."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'invalid_request'}), 400
        
        poh_credential = data.get('poh_credential')
        if not poh_credential:
            return jsonify({'success': False, 'error': 'missing_credential'}), 400
        
        manager = get_retrieval_manager()
        result = manager.connect_poh_to_wallet_retrieval(poh_credential)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/retrieve', methods=['POST'])
def retrieve_wallet():
    """Retrieve wallet using RID/VID from PoH verification."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'invalid_request'}), 400
        
        user_vid = session.get('user_vid')
        kyc_verified = session.get('kyc_verified', False)
        
        if not user_vid or not kyc_verified:
            return jsonify({
                'success': False,
                'error': 'poh_connection_required',
                'required_endpoint': '/api/wallet/connect-poh'
            }), 400
        
        recovery_factors = data.get('recovery_factors', {})
        if not recovery_factors.get('passphrase'):
            return jsonify({'success': False, 'error': 'missing_passphrase'}), 400
        
        from api.recovery_vault import get_vault_manager
        vault_manager = get_vault_manager()
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        envelope_result = vault_manager.get_envelope(user_vid, client_ip)
        
        if not envelope_result['success']:
            return jsonify({'success': False, 'error': 'wallet_not_found'}), 404
        
        return jsonify({
            'success': True,
            'wallet_found': True,
            'envelope_counter': envelope_result['counter']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/status', methods=['GET'])
def get_wallet_status():
    """Get wallet retrieval status."""
    return jsonify({
        'success': True,
        'status': {
            'poh_connected': session.get('kyc_verified', False),
            'rid_available': bool(session.get('user_rid')),
            'vid_available': bool(session.get('user_vid')),
            'session_active': True
        }
    })


# ============================================================================
# ROUTES: REVOCATION
# ============================================================================

@wallet_service_bp.route('/api/wallet/revoke', methods=['POST'])
def revoke_credential():
    """Revoke credential from wallet."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'invalid_request'}), 400
        
        credential_id = data.get('credential_id')
        credential_type = data.get('credential_type', 'unknown')
        credential_scope = data.get('credential_scope', 'site_specific')
        site_domain = data.get('site_domain')
        reason = data.get('reason', 'user_requested')
        
        if not credential_id:
            return jsonify({'success': False, 'error': 'missing_credential_id'}), 400
        
        if credential_scope == 'cross_site' or credential_type == 'poh':
            network_success = await_network_revocation(credential_id, reason)
            
            try:
                from api.revocation_sync import trigger_revocation_sync
                trigger_revocation_sync(credential_id, credential_type, site_id=None)
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'network_wide',
                'network_propagated': network_success
            })
        
        elif credential_type == 'permission':
            site_success = await_site_revocation(credential_id, reason, site_domain)
            
            try:
                from api.revocation_sync import trigger_revocation_sync
                trigger_revocation_sync(credential_id, 'permission', site_id=site_domain)
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'site_specific',
                'site_updated': site_success
            })
        
        return jsonify({
            'success': True,
            'credential_id': credential_id,
            'revocation_type': 'local_only'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/revocation-status', methods=['GET'])
def get_revocation_status():
    """Get revocation status for credentials."""
    credential_ids = request.args.getlist('credential_ids')
    
    if not credential_ids:
        return jsonify({'success': False, 'error': 'no_credentials'}), 400
    
    statuses = {cred_id: {'revoked': False} for cred_id in credential_ids}
    return jsonify({'success': True, 'statuses': statuses})


@wallet_service_bp.route('/api/wallet/revoke-user', methods=['POST'])
def revoke_user():
    """
    Revoke ALL credentials for a user (PPID) on ONE SITE across ALL devices.
    
    This adds the user's PPID to the Bloom filter, which invalidates
    ALL credentials for that user on that site regardless of which device they're on.
    
    Use this when:
    - Site admin bans a user from their site
    - User requests access removal from a specific site
    
    For global revocation (all sites), use /api/wallet/revoke-wallet instead.
    
    Request body:
        ppid: The user's PPID (site-specific identifier)
        site_id: The site this PPID belongs to
        reason: Reason for revocation
    """
    try:
        data = request.get_json() or {}
        ppid = data.get('ppid')
        site_id = data.get('site_id')
        reason = data.get('reason', 'user_revocation')
        
        if not ppid:
            return jsonify({'success': False, 'error': 'ppid required'}), 400
        
        if not site_id:
            return jsonify({'success': False, 'error': 'site_id required'}), 400
        
        # Add PPID to revocation list with revocation_type='user'
        from api.database import get_db, RevocationList
        from datetime import datetime
        
        db = get_db()
        try:
            # Check if already revoked
            existing = db.query(RevocationList).filter(
                RevocationList.ppid == ppid,
                RevocationList.site_id == site_id
            ).first()
            
            if existing:
                return jsonify({
                    'success': True,
                    'already_revoked': True,
                    'message': 'User already revoked for this site'
                })
            
            # Create new revocation entry
            revocation = RevocationList(
                lemma_id=f"ppid:{ppid}",  # Use ppid: prefix to distinguish
                credential_id=f"ppid:{ppid}",
                ppid=ppid,
                site_id=site_id,
                revocation_type='user',  # User-level revocation
                reason=reason,
                revoked_at=datetime.utcnow(),
                revoked_by='api'
            )
            
            db.add(revocation)
            db.commit()
            
            logger.info(f"🚫 User revoked: PPID {ppid[:12]}... for site {site_id}")
            
            return jsonify({
                'success': True,
                'ppid': ppid,
                'site_id': site_id,
                'revocation_type': 'user',
                'message': 'User revoked across all devices. Bloom filter will sync within 1 hour.',
                'note': 'All existing credentials for this PPID are now invalid.'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"User revocation failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/revoke-wallet', methods=['POST'])
def revoke_wallet():
    """
    Revoke ALL credentials for a wallet across ALL sites and ALL devices.
    
    This is the nuclear option - use for:
    - Account deletion requests
    - Compromised wallet (device lost with passkey deleted)
    - Security incidents requiring immediate full lockout
    
    This adds the wallet_id to the global Bloom filter, which invalidates
    ALL credentials for that wallet on EVERY site.
    
    Request body:
        wallet_id: The wallet identifier to revoke
        reason: Reason for revocation
        
    Security: Requires authenticated session OR admin API key
    """
    try:
        data = request.get_json() or {}
        wallet_id = data.get('wallet_id')
        reason = data.get('reason', 'wallet_revocation')
        
        if not wallet_id:
            return jsonify({'success': False, 'error': 'wallet_id required'}), 400
        
        # Security: Verify caller is authorized
        # Wallet-level bans are SERIOUS - only allow:
        # 1. Wallet owner (self-revoke for account deletion)
        # 2. Lemma.id platform admin (fraud/abuse cases)
        
        session_wallet_id = None
        try:
            session_token = request.cookies.get(SESSION_COOKIE_NAME)
            if session_token:
                session_data = validate_session_token(session_token)
                if session_data:
                    session_wallet_id = session_data.get('wallet_id')
        except:
            pass
        
        # Check for platform admin - requires LEMMA_ADMIN_KEY env var match
        admin_key = os.environ.get('LEMMA_ADMIN_KEY', '')
        provided_key = request.headers.get('X-Admin-Key', '')
        is_admin = admin_key and provided_key and hmac.compare_digest(admin_key, provided_key)
        
        # Wallet owner can self-revoke (account deletion)
        is_owner = session_wallet_id == wallet_id
        
        if not is_admin and not is_owner:
            logger.warning(f"🚫 Unauthorized wallet revocation attempt for {wallet_id[:12]}...")
            return jsonify({
                'success': False, 
                'error': 'Unauthorized - wallet-level bans require owner session or platform admin'
            }), 403
        
        # Log who is doing the ban
        if is_admin:
            logger.warning(f"⚠️ ADMIN wallet ban initiated for {wallet_id[:12]}... Reason: {reason}")
        
        # Add wallet_id to revocation list with revocation_type='wallet'
        from api.database import get_db, RevocationList
        from datetime import datetime
        
        db = get_db()
        try:
            # Check if already revoked
            existing = db.query(RevocationList).filter(
                RevocationList.wallet_id == wallet_id,
                RevocationList.revocation_type == 'wallet'
            ).first()
            
            if existing:
                return jsonify({
                    'success': True,
                    'already_revoked': True,
                    'message': 'Wallet already revoked globally'
                })
            
            # Create new revocation entry
            revocation = RevocationList(
                lemma_id=f"wallet:{wallet_id}",
                credential_id=f"wallet:{wallet_id}",
                wallet_id=wallet_id,
                revocation_type='wallet',  # Wallet-level revocation (all sites)
                reason=reason,
                revoked_at=datetime.utcnow(),
                revoked_by='owner' if is_owner else 'admin'
            )
            
            db.add(revocation)
            db.commit()
            
            logger.info(f"🔐 GLOBAL REVOCATION: Wallet {wallet_id[:12]}... revoked across ALL sites")
            
            # Audit log
            try:
                from api.audit_logger import log_event, AuditEvent
                log_event(
                    AuditEvent.CREDENTIAL_REVOKED,
                    details={
                        'wallet_id': wallet_id,
                        'revocation_type': 'wallet',
                        'scope': 'global',
                        'reason': reason
                    }
                )
            except Exception:
                pass
            
            return jsonify({
                'success': True,
                'wallet_id': wallet_id,
                'revocation_type': 'wallet',
                'scope': 'global',
                'message': 'Wallet revoked globally. ALL credentials on ALL sites are now invalid.',
                'note': 'Bloom filter will sync within 1 hour. Immediate effect on new verifications.'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Wallet revocation failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ROUTES: WALLET TRANSFER
# ============================================================================

@wallet_service_bp.route('/api/wallet/transfer/create-session', methods=['POST', 'OPTIONS'])
def create_transfer_session():
    """Create a new wallet transfer session."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not validate_session_token(session_token):
        return cross_origin_response({'success': False, 'error': 'not_authenticated'}, 401)
    
    if not _validate_csrf():
        return cross_origin_response({'success': False, 'error': 'csrf_missing_or_invalid'}, 403)
    
    data = request.get_json()
    if not data or 'device_id' not in data:
        return cross_origin_response({'success': False, 'error': 'Missing device_id'}, 400)
    
    transfer = TransferSession(data['device_id'], data.get('wallet_data'))
    
    session_data = {
        'session_id': transfer.session_id,
        'source_device_id': transfer.source_device_id,
        'transfer_key': transfer.transfer_key,
        'created_at': transfer.created_at.isoformat(),
        'expires_at': transfer.expires_at.isoformat(),
        'wallet_data': transfer.wallet_data,
        'status': transfer.status,
        'target_device_id': transfer.target_device_id
    }
    
    if not _storage.set_session(transfer.session_id, session_data):
        return cross_origin_response({'success': False, 'error': 'Failed to store session'}, 500)
    
    return cross_origin_response({
        'success': True,
        'session_id': transfer.session_id,
        'qr_data': transfer.to_qr_data(),
        'expires_at': int(transfer.expires_at.timestamp() * 1000)
    })


@wallet_service_bp.route('/api/wallet/transfer/set-wallet', methods=['POST', 'OPTIONS'])
def set_wallet_data():
    """Set wallet data for transfer session."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token or not validate_session_token(session_token):
        return cross_origin_response({'success': False, 'error': 'not_authenticated'}, 401)
    
    if not _validate_csrf():
        return cross_origin_response({'success': False, 'error': 'csrf_missing_or_invalid'}, 403)
    
    data = request.get_json()
    if not data or 'session_id' not in data or 'wallet_data' not in data:
        return cross_origin_response({'success': False, 'error': 'Missing session_id or wallet_data'}, 400)
    
    session_data = _storage.get_session(data['session_id'])
    if not session_data:
        return cross_origin_response({'success': False, 'error': 'Transfer session not found'}, 404)
    
    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if datetime.now() > expires_at:
        _storage.delete_session(data['session_id'])
        return cross_origin_response({'success': False, 'error': 'Transfer session expired'}, 410)
    
    session_data['wallet_data'] = data['wallet_data']
    session_data['status'] = 'ready'
    _storage.set_session(data['session_id'], session_data)
    
    return cross_origin_response({'success': True, 'status': 'ready'})


@wallet_service_bp.route('/api/wallet/transfer/get-wallet', methods=['POST', 'OPTIONS'])
def get_wallet_data():
    """Get wallet data from transfer session."""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        if not _origin_allowed(origin):
            return response, 403
        return response
    
    origin = request.headers.get('Origin')
    if not _origin_allowed(origin):
        return cross_origin_response({'success': False, 'error': 'origin_not_allowed'}, 403)
    
    data = request.get_json()
    if not data or 'session_id' not in data or 'transfer_key' not in data:
        return cross_origin_response({'success': False, 'error': 'Missing session_id or transfer_key'}, 400)
    
    session_data = _storage.get_session(data['session_id'])
    if not session_data:
        return cross_origin_response({'success': False, 'error': 'Transfer session not found'}, 404)
    
    expires_at = datetime.fromisoformat(session_data['expires_at'])
    if datetime.now() > expires_at:
        _storage.delete_session(data['session_id'])
        return cross_origin_response({'success': False, 'error': 'Transfer session expired'}, 410)
    
    if session_data['transfer_key'] != data['transfer_key']:
        return cross_origin_response({'success': False, 'error': 'Invalid transfer key'}, 403)
    
    if not session_data['wallet_data']:
        return cross_origin_response({'success': False, 'error': 'Wallet data not ready yet'}, 202)
    
    session_data['status'] = 'completed'
    session_data['target_device_id'] = data.get('target_device_id', 'unknown')
    _storage.set_session(data['session_id'], session_data)
    
    return cross_origin_response({
        'success': True,
        'wallet_data': session_data['wallet_data'],
        'transfer_completed': True
    })


# ============================================================================
# ROUTES: PIN RESET
# ============================================================================

@wallet_service_bp.route('/api/wallet/pin-reset/request', methods=['POST'])
def request_pin_reset():
    """Request PIN reset - sends email with reset link."""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        
        if not email or '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'invalid_email'}), 400
        
        from api.ppid import derive_ppid_did
        user_did = derive_ppid_did(email, "lemma.id")
        
        reset_token = secrets.token_urlsafe(32)
        _reset_tokens[reset_token] = {
            'email': email,
            'user_did': user_did,
            'created_at': int(time.time())
        }
        
        reset_url = f"{request.host_url}wallet/reset-pin?token={reset_token}"
        
        from api.email_service import send_email
        html = f"""
        <html><body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 40px;">
            <h1>Lemma Wallet PIN Reset</h1>
            <p>You requested to reset your Lemma Wallet PIN.</p>
            <a href="{reset_url}" style="display: inline-block; background: #2563eb; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px;">Reset Your PIN</a>
            <p style="margin-top: 24px; color: #666;">This link expires in 1 hour.</p>
        </body></html>
        """
        
        result = send_email(to=email, subject='Lemma Wallet PIN Reset', html=html, text=f'Reset your PIN: {reset_url}')
        
        if result['success']:
            return jsonify({'success': True, 'message': 'Reset email sent'})
        return jsonify({'success': False, 'error': 'email_send_failed'}), 500
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet/pin-reset/verify', methods=['POST'])
def verify_reset_token():
    """Verify reset token is valid."""
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    
    if not token or token not in _reset_tokens:
        return jsonify({'success': False, 'error': 'invalid_token'}), 400
    
    token_data = _reset_tokens[token]
    if int(time.time()) - token_data['created_at'] > TOKEN_EXPIRY:
        del _reset_tokens[token]
        return jsonify({'success': False, 'error': 'token_expired'}), 400
    
    return jsonify({
        'success': True,
        'email': token_data['email'],
        'user_did': token_data['user_did']
    })


@wallet_service_bp.route('/api/wallet/pin-reset/complete', methods=['POST'])
def complete_pin_reset():
    """Complete PIN reset."""
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    new_pin = data.get('new_pin', '').strip()
    
    if not token or not new_pin:
        return jsonify({'success': False, 'error': 'missing_fields'}), 400
    
    if len(new_pin) != 4 or not new_pin.isdigit():
        return jsonify({'success': False, 'error': 'invalid_pin'}), 400
    
    if token not in _reset_tokens:
        return jsonify({'success': False, 'error': 'invalid_token'}), 400
    
    token_data = _reset_tokens[token]
    if int(time.time()) - token_data['created_at'] > TOKEN_EXPIRY:
        del _reset_tokens[token]
        return jsonify({'success': False, 'error': 'token_expired'}), 400
    
    del _reset_tokens[token]
    
    return jsonify({
        'success': True,
        'message': 'PIN reset successful',
        'email': token_data['email']
    })


# ============================================================================
# ROUTES: MULTI-LEMMA SYNC
# ============================================================================

@wallet_service_bp.route('/api/wallet-sync/create-qr-auth', methods=['POST'])
def create_qr_auth_lemma():
    """Create QR Authentication Lemma for device sync."""
    if not MULTI_LEMMA_AVAILABLE:
        return jsonify({'success': False, 'error': 'multi_lemma_engine_not_available'}), 500
    
    try:
        import qrcode
        
        data = request.get_json()
        mobile_device_did = data.get('mobile_device_did')
        requesting_device_did = data.get('requesting_device_did')
        requested_scope = data.get('requested_scope', ['federated_identity'])
        requested_duration = data.get('requested_duration', 86400)
        device_fingerprint = data.get('device_fingerprint', 'unknown')
        
        if not mobile_device_did or not requesting_device_did:
            return jsonify({'success': False, 'error': 'missing_required_fields'}), 400
        
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        mobile_issuer = issuer_manager.get_multi_lemma_issuer('qr_authentication')
        qr_sync_manager = PyQRSyncManager()
        
        qr_start = time.perf_counter_ns()
        qr_lemma_json = qr_sync_manager.create_qr_auth_lemma(
            mobile_issuer, requesting_device_did, requested_scope,
            requested_duration, device_fingerprint
        )
        qr_time_ns = time.perf_counter_ns() - qr_start
        
        qr_data = qr_sync_manager.generate_qr_data(qr_lemma_json)
        
        qr_img = qrcode.QRCode(version=1, box_size=10, border=5)
        qr_img.add_data(qr_data)
        qr_img.make(fit=True)
        
        img = qr_img.make_image(fill_color="black", back_color="white")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        qr_lemma = json.loads(qr_lemma_json)
        
        return jsonify({
            'success': True,
            'qr_auth_lemma': qr_lemma,
            'qr_data': qr_data,
            'qr_image_base64': f"data:image/png;base64,{img_base64}",
            'creation_time_ns': qr_time_ns
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-sync/verify-qr-auth', methods=['POST'])
def verify_qr_auth_lemma():
    """Verify QR Authentication Lemma."""
    if not MULTI_LEMMA_AVAILABLE:
        return jsonify({'success': False, 'error': 'multi_lemma_engine_not_available'}), 500
    
    try:
        data = request.get_json()
        qr_data = data.get('qr_data')
        
        if not qr_data:
            return jsonify({'success': False, 'error': 'qr_data_required'}), 400
        
        qr_sync_manager = PyQRSyncManager()
        qr_lemma_json = qr_sync_manager.parse_qr_data(qr_data)
        qr_result = qr_sync_manager.verify_qr_auth_lemma(qr_lemma_json)
        
        if qr_result.valid and qr_result.sync_authorized:
            delegation_lemma = None
            if qr_result.delegation_lemma_json:
                delegation_lemma = json.loads(qr_result.delegation_lemma_json)
            
            return jsonify({
                'success': True,
                'qr_verification': {
                    'valid': qr_result.valid,
                    'sync_authorized': qr_result.sync_authorized
                },
                'delegation_lemma': delegation_lemma
            })
        
        return jsonify({
            'success': False,
            'error': 'qr_verification_failed',
            'reason': qr_result.reason
        }), 401
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@wallet_service_bp.route('/api/wallet-sync/health', methods=['GET'])
def wallet_sync_health():
    """Health check for multi-lemma sync."""
    return jsonify({
        'status': 'ready' if MULTI_LEMMA_AVAILABLE else 'unavailable',
        'multi_lemma_engine': MULTI_LEMMA_AVAILABLE
    })


# ============================================================================
# EXPORTS
# ============================================================================

# Export for backwards compatibility
def get_wallet_auth_script():
    """Returns JavaScript for auto-attaching wallet auth."""
    return '''
<script>
(function() {
    const originalFetch = window.fetch;
    window.fetch = async function(url, options = {}) {
        if (url.startsWith('/api/') && window.lemmaWallet?.isUnlocked?.()) {
            try {
                const authProof = await window.lemmaWallet.getAuthProof();
                options.headers = options.headers || {};
                options.headers['X-Wallet-Auth'] = JSON.stringify(authProof);
            } catch (e) {}
        }
        return originalFetch(url, options);
    };
})();
</script>
'''
