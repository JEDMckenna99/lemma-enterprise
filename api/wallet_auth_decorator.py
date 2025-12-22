"""
Wallet-Based Authentication Decorators
======================================

Use these decorators to protect routes with wallet-based authentication.
When a user unlocks their wallet with a passkey and has a valid lemma for lemma.id,
they are automatically signed in across the platform.

Usage:
    @require_wallet_auth
    def protected_route():
        # g.user_id contains the authenticated user
        return jsonify({'user': g.user_id})
    
    @require_permission('admin')
    def admin_route():
        # Only users with 'admin' permission can access
        return jsonify({'admin': True})
"""

from functools import wraps
from flask import request, jsonify, g
import logging
import json
import base64
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================
# WALLET AUTH DECORATOR
# ============================================

def require_wallet_auth(f):
    """
    Decorator that requires wallet-based authentication.
    
    Checks for:
    1. X-Wallet-Auth header containing auth proof
    2. Or Cookie containing auth proof
    3. Or Authorization: Bearer <wallet_token>
    
    Sets g.user_id, g.wallet_id, g.auth_method on success.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_proof = None
        
        # Try to get auth proof from various sources
        # 1. X-Wallet-Auth header (preferred)
        if 'X-Wallet-Auth' in request.headers:
            try:
                auth_proof = json.loads(request.headers.get('X-Wallet-Auth'))
            except json.JSONDecodeError:
                pass
        
        # 2. Authorization: Bearer header
        if not auth_proof and 'Authorization' in request.headers:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer wallet_'):
                try:
                    # Token is base64 encoded auth proof
                    token = auth_header.replace('Bearer ', '')
                    auth_proof = json.loads(base64.b64decode(token.encode()).decode())
                except Exception:
                    pass
        
        # 3. Cookie
        if not auth_proof:
            cookie = request.cookies.get('lemma_wallet_auth')
            if cookie:
                try:
                    auth_proof = json.loads(base64.b64decode(cookie.encode()).decode())
                except Exception:
                    pass
        
        if not auth_proof:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'Unlock your wallet to access this resource'
            }), 401
        
        # Validate auth proof
        validation = validate_wallet_auth_proof(auth_proof)
        if not validation['valid']:
            return jsonify({
                'success': False,
                'error': validation['error'],
                'message': 'Wallet authentication failed'
            }), 401
        
        # Set user context
        g.user_id = validation['user_id']
        g.wallet_id = validation['wallet_id']
        g.auth_method = 'wallet_passkey'
        g.permissions = validation.get('permissions', [])
        
        logger.info(f"✅ Wallet auth: user={g.user_id}, wallet={g.wallet_id}")
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_permission(permission_id):
    """
    Decorator that requires a specific permission lemma.
    
    Usage:
        @require_permission('admin')
        def admin_only():
            ...
    """
    def decorator(f):
        @wraps(f)
        @require_wallet_auth
        def decorated_function(*args, **kwargs):
            # Check if user has required permission
            if permission_id not in g.permissions:
                logger.warning(f"🚫 Permission denied: {g.user_id} missing '{permission_id}'")
                return jsonify({
                    'success': False,
                    'error': 'Permission denied',
                    'required_permission': permission_id,
                    'message': f"You need '{permission_id}' permission to access this resource"
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_lemma(issuer=None, claim_type=None):
    """
    Decorator that requires a valid lemma from a specific issuer or with specific claims.
    
    Usage:
        @require_lemma(issuer='did:web:lemma.id')
        def lemma_holders_only():
            ...
        
        @require_lemma(claim_type='premium_member')
        def premium_only():
            ...
    """
    def decorator(f):
        @wraps(f)
        @require_wallet_auth
        def decorated_function(*args, **kwargs):
            lemma = g.get('lemma')
            
            # Check issuer
            if issuer and (not lemma or lemma.get('issuer') != issuer):
                return jsonify({
                    'success': False,
                    'error': 'Invalid issuer',
                    'required_issuer': issuer
                }), 403
            
            # Check claim type
            if claim_type:
                claims = lemma.get('claims', {}) if lemma else {}
                if claims.get('type') != claim_type:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid claim type',
                        'required_claim_type': claim_type
                    }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================
# VALIDATION HELPERS
# ============================================

def validate_wallet_auth_proof(auth_proof):
    """
    Validate a wallet auth proof.
    
    Returns:
        {
            'valid': True/False,
            'error': 'reason if invalid',
            'user_id': 'user_xxx',
            'wallet_id': 'wallet_xxx',
            'permissions': ['admin', 'user', ...]
        }
    """
    try:
        # Check required fields
        required = ['type', 'method', 'walletId', 'unlockedAt', 'expiresAt']
        for field in required:
            if field not in auth_proof:
                return {'valid': False, 'error': f'Missing field: {field}'}
        
        # Check type
        if auth_proof['type'] != 'wallet_auth':
            return {'valid': False, 'error': 'Invalid auth type'}
        
        # Check expiration
        expires_at = auth_proof['expiresAt']
        if isinstance(expires_at, (int, float)):
            if expires_at < datetime.utcnow().timestamp() * 1000:
                return {'valid': False, 'error': 'Auth proof expired'}
        
        # Extract user info
        wallet_id = auth_proof['walletId']
        user_id = auth_proof.get('userId', wallet_id)  # Fallback to wallet_id
        
        # Extract permissions from lemma if present
        permissions = []
        if 'lemma' in auth_proof:
            lemma = auth_proof['lemma']
            claims = lemma.get('claims', {})
            
            # Get permission from claims
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
        logger.error(f"❌ Auth proof validation error: {e}")
        return {'valid': False, 'error': str(e)}


# ============================================
# CLIENT-SIDE HELPER (for JavaScript)
# ============================================

def get_wallet_auth_script():
    """
    Returns JavaScript that automatically attaches wallet auth to requests.
    Include this in your base template.
    """
    return '''
<script>
// Automatically attach wallet auth to fetch requests
(function() {
    const originalFetch = window.fetch;
    
    window.fetch = async function(url, options = {}) {
        // Only modify requests to our API
        if (url.startsWith('/api/') || url.startsWith('https://lemma.id/api/')) {
            // Get auth proof from wallet if unlocked
            if (window.lemmaWallet && window.lemmaWallet.isUnlocked && window.lemmaWallet.isUnlocked()) {
                try {
                    const authProof = await window.lemmaWallet.getAuthProof();
                    options.headers = options.headers || {};
                    options.headers['X-Wallet-Auth'] = JSON.stringify(authProof);
                } catch (e) {
                    console.warn('Could not get wallet auth proof:', e);
                }
            }
        }
        return originalFetch(url, options);
    };
    
    console.log('🔐 Wallet auth auto-attach enabled');
})();
</script>
'''
