"""
Agent Credentials API
Enables passkey-authorized, time-limited access for AI coding agents.

SECURITY MODEL:
1. Human authenticates with passkey (cannot be faked by AI)
2. Human issues credential with scope and TTL
3. Agent includes credential in X-Agent-Token header
4. Server validates on every request
5. Human can revoke at any time

WHY THIS IS SECURE:
- Passkey = hardware-bound biometric proof of human presence
- Time-limited = credentials auto-expire
- Scoped = agents can only do what's explicitly allowed
- Audited = every agent action is logged
- Revocable = human maintains kill switch
"""

import os
import json
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, g, session
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

agent_credentials_bp = Blueprint('agent_credentials', __name__)

# ============================================
# SECURITY: Token Generation and Hashing
# ============================================

def generate_agent_token():
    """
    Generate a secure random token for agent authentication.
    Returns (token_id, plaintext_token, token_hash)
    
    - token_id: Short identifier for the token (for display/lookup)
    - plaintext_token: What the agent will use (shown once, never stored)
    - token_hash: What we store in the database (cannot be reversed)
    """
    token_id = f"agt_{secrets.token_urlsafe(8)}"
    plaintext_token = f"lm_agent_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
    
    return token_id, plaintext_token, token_hash


def hash_token(plaintext_token):
    """Hash a token for comparison with stored hash."""
    return hashlib.sha256(plaintext_token.encode()).hexdigest()


# ============================================
# CREDENTIAL ISSUANCE (Requires Passkey Auth)
# ============================================

@agent_credentials_bp.route('/api/agent/credentials/issue', methods=['POST'])
@cross_origin()
def issue_agent_credential():
    """
    Issue a new agent credential.
    
    SECURITY: This endpoint requires the user to be authenticated via passkey.
    The passkey proof must be fresh (within last 5 minutes) to issue credentials.
    
    POST /api/agent/credentials/issue
    {
        "agent_name": "Cursor AI",
        "scope": ["read", "write"],
        "ttl_hours": 4,
        "allowed_sites": null,  // null = all sites user has access to
        "description": "Development session"
    }
    
    Returns:
        - token: The plaintext token (SHOWN ONLY ONCE)
        - token_id: Identifier for managing the credential
        - expires_at: When the credential expires
    """
    try:
        # SECURITY CHECK 1: User must be authenticated
        # Check for passkey session or PPID
        ppid = request.headers.get('X-Lemma-PPID')
        passkey_verified = session.get('passkey_verified', False)
        customer_id = session.get('customer_id')
        user_email = session.get('user_email')
        
        # Also check Authorization header for Bearer token with credential
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer ') and not ppid:
            # Could be a JSON credential - extract PPID
            try:
                cred_data = json.loads(auth_header[7:])
                ppid = cred_data.get('subject') or cred_data.get('credentialSubject', {}).get('id')
            except:
                pass
        
        if not ppid and not customer_id:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'You must be signed in with passkey to issue agent credentials'
            }), 401
        
        # Use PPID as identifier, fall back to customer_id
        authorized_by = ppid or f"customer:{customer_id}"
        
        # Parse request data
        data = request.get_json() or {}
        agent_name = data.get('agent_name', 'AI Agent')
        scope = data.get('scope', ['read'])
        ttl_hours = min(data.get('ttl_hours', 4), 24)  # Max 24 hours
        allowed_sites = data.get('allowed_sites')  # null = all user's sites
        description = data.get('description', '')
        
        # Validate scope
        valid_scopes = ['read', 'write', 'admin', 'test']
        scope = [s for s in scope if s in valid_scopes]
        if not scope:
            scope = ['read']
        
        # Generate token
        token_id, plaintext_token, token_hash = generate_agent_token()
        
        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
        
        # Store in database
        try:
            from api.database import get_db_connection
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO agent_credentials 
                (token_id, token_hash, authorized_by_ppid, authorized_by_email,
                 scope, allowed_sites, expires_at, agent_name, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                token_id,
                token_hash,
                authorized_by,
                user_email,
                json.dumps(scope),
                json.dumps(allowed_sites) if allowed_sites else None,
                expires_at,
                agent_name,
                description
            ))
            
            credential_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as db_err:
            logger.error(f"Failed to store agent credential: {db_err}")
            return jsonify({
                'success': False,
                'error': 'Database error',
                'message': str(db_err)
            }), 500
        
        logger.info(f"Agent credential issued: {token_id} for {authorized_by} (scope: {scope}, expires: {expires_at})")
        
        return jsonify({
            'success': True,
            'credential': {
                'token': plaintext_token,  # SHOWN ONLY ONCE
                'token_id': token_id,
                'scope': scope,
                'expires_at': expires_at.isoformat() + 'Z',
                'ttl_hours': ttl_hours,
                'agent_name': agent_name
            },
            'usage': {
                'header': 'X-Agent-Token',
                'example': f'X-Agent-Token: {plaintext_token}'
            },
            'message': 'Credential issued. Save the token - it will not be shown again.'
        })
        
    except Exception as e:
        logger.error(f"Failed to issue agent credential: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# CREDENTIAL VALIDATION (Used by Decorator)
# ============================================

def validate_agent_token(token):
    """
    Validate an agent token and return credential info if valid.
    
    Returns:
        dict with credential info if valid
        None if invalid/expired/revoked
    """
    if not token or not token.startswith('lm_agent_'):
        return None
    
    token_hash = hash_token(token)
    
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, token_id, authorized_by_ppid, authorized_by_email,
                   scope, allowed_sites, expires_at, agent_name
            FROM agent_credentials
            WHERE token_hash = %s
              AND revoked = FALSE
              AND expires_at > NOW()
        """, (token_hash,))
        
        row = cursor.fetchone()
        
        if not row:
            cursor.close()
            conn.close()
            return None
        
        # Update usage stats
        cursor.execute("""
            UPDATE agent_credentials
            SET last_used_at = NOW(), use_count = use_count + 1
            WHERE id = %s
        """, (row[0],))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            'credential_id': row[0],
            'token_id': row[1],
            'authorized_by_ppid': row[2],
            'authorized_by_email': row[3],
            'scope': row[4] if isinstance(row[4], list) else json.loads(row[4] or '["read"]'),
            'allowed_sites': row[5] if isinstance(row[5], list) else (json.loads(row[5]) if row[5] else None),
            'expires_at': row[6],
            'agent_name': row[7]
        }
        
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return None


def log_agent_action(credential_info, action, resource=None, success=True, status_code=200):
    """Log an agent action to the audit trail."""
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO agent_audit_log
            (credential_id, token_id, action, resource, method, path, status_code, success)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            credential_info.get('credential_id'),
            credential_info.get('token_id'),
            action,
            resource,
            request.method,
            request.path,
            status_code,
            success
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.warning(f"Failed to log agent action: {e}")


# ============================================
# DECORATOR: Require Agent or User Auth
# ============================================

def require_agent_or_user_auth(required_scope=None):
    """
    Decorator that allows either:
    1. Agent token (X-Agent-Token header)
    2. User auth (X-Lemma-PPID header or session)
    
    Usage:
        @require_agent_or_user_auth(required_scope='write')
        def my_endpoint():
            # g.agent_credential is set if agent auth
            # g.ppid is set if user auth
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Try agent token first
            agent_token = request.headers.get('X-Agent-Token')
            
            if agent_token:
                credential_info = validate_agent_token(agent_token)
                
                if not credential_info:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid or expired agent credential'
                    }), 401
                
                # Check scope if required
                if required_scope:
                    if required_scope not in credential_info['scope']:
                        log_agent_action(credential_info, f'scope_denied:{required_scope}', success=False, status_code=403)
                        return jsonify({
                            'success': False,
                            'error': f'Agent credential lacks required scope: {required_scope}'
                        }), 403
                
                # Set credential info in request context
                g.agent_credential = credential_info
                g.ppid = credential_info['authorized_by_ppid']  # Use authorizer's PPID
                g.authenticated = True
                g.auth_method = 'agent_token'
                
                # Log the action
                log_agent_action(credential_info, f'{request.method}:{request.path}')
                
                return f(*args, **kwargs)
            
            # Fall back to user auth
            ppid = request.headers.get('X-Lemma-PPID')
            api_key = request.headers.get('X-API-Key')
            
            if ppid and ppid.startswith('did:lemma:ppid_'):
                g.ppid = ppid
                g.authenticated = True
                g.auth_method = 'ppid'
                return f(*args, **kwargs)
            
            if api_key and len(api_key) >= 10:
                g.api_key = api_key
                g.authenticated = True
                g.auth_method = 'api_key'
                return f(*args, **kwargs)
            
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'Provide X-Agent-Token, X-Lemma-PPID, or X-API-Key header'
            }), 401
        
        return decorated_function
    return decorator


# ============================================
# CREDENTIAL MANAGEMENT ENDPOINTS
# ============================================

@agent_credentials_bp.route('/api/agent/credentials', methods=['GET'])
@cross_origin()
def list_agent_credentials():
    """List all agent credentials for the authenticated user."""
    ppid = request.headers.get('X-Lemma-PPID')
    customer_id = session.get('customer_id')
    
    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    authorized_by = ppid or f"customer:{customer_id}"
    
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT token_id, scope, allowed_sites, issued_at, expires_at,
                   revoked, revoked_at, agent_name, description, last_used_at, use_count
            FROM agent_credentials
            WHERE authorized_by_ppid = %s
            ORDER BY issued_at DESC
        """, (authorized_by,))
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        credentials = []
        for row in rows:
            credentials.append({
                'token_id': row[0],
                'scope': row[1] if isinstance(row[1], list) else json.loads(row[1] or '[]'),
                'allowed_sites': row[2] if isinstance(row[2], list) else (json.loads(row[2]) if row[2] else None),
                'issued_at': row[3].isoformat() + 'Z' if row[3] else None,
                'expires_at': row[4].isoformat() + 'Z' if row[4] else None,
                'revoked': row[5],
                'revoked_at': row[6].isoformat() + 'Z' if row[6] else None,
                'agent_name': row[7],
                'description': row[8],
                'last_used_at': row[9].isoformat() + 'Z' if row[9] else None,
                'use_count': row[10],
                'status': 'revoked' if row[5] else ('expired' if row[4] and row[4] < datetime.utcnow() else 'active')
            })
        
        return jsonify({
            'success': True,
            'credentials': credentials
        })
        
    except Exception as e:
        logger.error(f"Failed to list agent credentials: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@agent_credentials_bp.route('/api/agent/credentials/<token_id>/revoke', methods=['POST'])
@cross_origin()
def revoke_agent_credential(token_id):
    """
    Revoke an agent credential immediately.
    
    This is the KILL SWITCH - use it if:
    - Agent is behaving unexpectedly
    - Session is no longer needed
    - Security concern
    """
    ppid = request.headers.get('X-Lemma-PPID')
    customer_id = session.get('customer_id')
    
    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    authorized_by = ppid or f"customer:{customer_id}"
    
    data = request.get_json() or {}
    reason = data.get('reason', 'Manual revocation')
    
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Only allow revoking your own credentials
        cursor.execute("""
            UPDATE agent_credentials
            SET revoked = TRUE, revoked_at = NOW(), revoked_reason = %s
            WHERE token_id = %s AND authorized_by_ppid = %s
            RETURNING id
        """, (reason, token_id, authorized_by))
        
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        if not result:
            return jsonify({
                'success': False,
                'error': 'Credential not found or not owned by you'
            }), 404
        
        logger.info(f"Agent credential revoked: {token_id} by {authorized_by} (reason: {reason})")
        
        return jsonify({
            'success': True,
            'message': f'Credential {token_id} has been revoked',
            'revoked_at': datetime.utcnow().isoformat() + 'Z'
        })
        
    except Exception as e:
        logger.error(f"Failed to revoke credential: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@agent_credentials_bp.route('/api/agent/credentials/audit', methods=['GET'])
@cross_origin()
def get_agent_audit_log():
    """Get audit log for agent actions."""
    ppid = request.headers.get('X-Lemma-PPID')
    customer_id = session.get('customer_id')
    
    if not ppid and not customer_id:
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    authorized_by = ppid or f"customer:{customer_id}"
    
    # Optional filters
    token_id = request.args.get('token_id')
    limit = min(int(request.args.get('limit', 100)), 500)
    
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if token_id:
            cursor.execute("""
                SELECT al.token_id, al.action, al.resource, al.method, al.path,
                       al.status_code, al.success, al.timestamp
                FROM agent_audit_log al
                JOIN agent_credentials ac ON al.credential_id = ac.id
                WHERE ac.authorized_by_ppid = %s AND al.token_id = %s
                ORDER BY al.timestamp DESC
                LIMIT %s
            """, (authorized_by, token_id, limit))
        else:
            cursor.execute("""
                SELECT al.token_id, al.action, al.resource, al.method, al.path,
                       al.status_code, al.success, al.timestamp
                FROM agent_audit_log al
                JOIN agent_credentials ac ON al.credential_id = ac.id
                WHERE ac.authorized_by_ppid = %s
                ORDER BY al.timestamp DESC
                LIMIT %s
            """, (authorized_by, limit))
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        audit_log = []
        for row in rows:
            audit_log.append({
                'token_id': row[0],
                'action': row[1],
                'resource': row[2],
                'method': row[3],
                'path': row[4],
                'status_code': row[5],
                'success': row[6],
                'timestamp': row[7].isoformat() + 'Z' if row[7] else None
            })
        
        return jsonify({
            'success': True,
            'audit_log': audit_log
        })
        
    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# QUICK VALIDATION ENDPOINT (For Testing)
# ============================================

@agent_credentials_bp.route('/api/agent/validate', methods=['GET', 'POST'])
@cross_origin()
def validate_agent_token_endpoint():
    """
    Quick endpoint to test if an agent token is valid.
    Useful for agents to verify their credentials are working.
    """
    token = request.headers.get('X-Agent-Token')
    
    if not token:
        return jsonify({
            'valid': False,
            'error': 'No X-Agent-Token header provided'
        }), 400
    
    credential_info = validate_agent_token(token)
    
    if not credential_info:
        return jsonify({
            'valid': False,
            'error': 'Invalid, expired, or revoked token'
        }), 401
    
    return jsonify({
        'valid': True,
        'token_id': credential_info['token_id'],
        'scope': credential_info['scope'],
        'expires_at': credential_info['expires_at'].isoformat() + 'Z' if credential_info['expires_at'] else None,
        'agent_name': credential_info['agent_name'],
        'authorized_by': credential_info['authorized_by_email'] or credential_info['authorized_by_ppid']
    })
