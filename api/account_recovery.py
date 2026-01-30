"""
Account Recovery API
Allows developers to recover access using their API key + site_id
"""

import logging
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

account_recovery_bp = Blueprint('account_recovery', __name__)

# In-memory store for recovery tokens (in production, use Redis or database)
# Format: {token_hash: {site_id, admin_email, expires_at, used}}
recovery_tokens = {}


def clean_expired_tokens():
    """Remove expired tokens"""
    now = datetime.now(timezone.utc)
    expired = [k for k, v in recovery_tokens.items() if v['expires_at'] < now]
    for k in expired:
        del recovery_tokens[k]


@account_recovery_bp.route('/api/recovery/initiate', methods=['POST'])
@cross_origin()
def initiate_recovery():
    """
    Initiate account recovery using API key + site_id
    
    This is secure because:
    1. API key proves ownership of the site
    2. Recovery link is sent to admin_email on file (second factor)
    3. Token is time-limited and single-use
    """
    try:
        from api.database import SessionLocal, Site
        from api.rate_limiter import check_rate_limit
        
        data = request.get_json() or {}
        
        api_key = data.get('api_key', '').strip()
        site_id = data.get('site_id', '').strip()
        
        if not api_key or not site_id:
            return jsonify({
                'success': False,
                'error': 'API key and site ID are required'
            }), 400
        
        # Rate limit by IP
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        # Allow 5 attempts per hour per IP
        rate_key = f"recovery:{client_ip}"
        if not check_rate_limit(rate_key, max_requests=5, window_seconds=3600):
            logger.warning(f"Recovery rate limit exceeded for IP {client_ip}")
            return jsonify({
                'success': False,
                'error': 'Too many recovery attempts. Please try again later.'
            }), 429
        
        db = SessionLocal()
        
        try:
            # Look up site
            site = db.query(Site).filter(Site.site_id == site_id).first()
            
            if not site:
                # Don't reveal if site exists
                logger.warning(f"Recovery attempt for non-existent site: {site_id}")
                return jsonify({
                    'success': True,
                    'message': 'If the API key is valid, a recovery link has been sent to the admin email.'
                })
            
            # Validate API key
            # Check multiple sources:
            # 1. sites.api_key column (legacy)
            # 2. site_api_keys table
            # 3. api_keys table (customer API keys)
            api_key_valid = False
            
            # Method 1: Check sites.api_key column (legacy)
            if site.api_key:
                # Direct comparison (if stored as plaintext)
                if site.api_key == api_key:
                    api_key_valid = True
                # Hash comparison (if stored as hash)
                elif hashlib.sha256(api_key.encode()).hexdigest() == site.api_key:
                    api_key_valid = True
            
            # Method 2: Check site_api_keys table
            if not api_key_valid:
                from api.database import get_db_connection
                try:
                    conn = get_db_connection(site_id)
                    cursor = conn.cursor()
                    
                    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                    cursor.execute("""
                        SELECT id FROM site_api_keys 
                        WHERE site_id = %s AND key_hash = %s AND is_active = true
                    """, (site_id, key_hash))
                    
                    if cursor.fetchone():
                        api_key_valid = True
                    
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.debug(f"Error checking site_api_keys: {e}")
            
            # Method 3: Check api_keys table (customer API keys)
            if not api_key_valid:
                from api.database import get_db_connection
                try:
                    conn = get_db_connection(site_id)
                    cursor = conn.cursor()
                    
                    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                    cursor.execute("""
                        SELECT id FROM api_keys 
                        WHERE site_id = %s AND key_hash = %s AND status = 'active'
                    """, (site_id, key_hash))
                    
                    if cursor.fetchone():
                        api_key_valid = True
                        logger.info(f"API key validated via api_keys table for site {site_id}")
                    
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.debug(f"Error checking api_keys: {e}")
            
            if not api_key_valid:
                logger.warning(f"Recovery attempt with invalid API key for site: {site_id}")
                # Don't reveal that the key was wrong
                return jsonify({
                    'success': True,
                    'message': 'If the API key is valid, a recovery link has been sent to the admin email.'
                })
            
            # API key is valid - generate recovery token
            admin_email = site.admin_email
            
            if not admin_email:
                logger.error(f"No admin email for site {site_id}")
                return jsonify({
                    'success': False,
                    'error': 'No admin email configured for this site. Contact support.'
                }), 400
            
            # Generate secure token
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Clean up old tokens
            clean_expired_tokens()
            
            # Store token (expires in 15 minutes)
            recovery_tokens[token_hash] = {
                'site_id': site_id,
                'admin_email': admin_email,
                'expires_at': datetime.now(timezone.utc) + timedelta(minutes=15),
                'used': False,
                'created_ip': client_ip
            }
            
            # Send recovery email
            recovery_url = f"https://lemma.id/recover/complete?token={token}"
            
            try:
                from api.email_service import send_email
                
                send_email(
                    to=admin_email,
                    subject="Lemma.id Account Recovery",
                    html=f"""
                    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                        <div style="text-align: center; margin-bottom: 32px;">
                            <h1 style="color: #1e293b; font-size: 24px; margin: 0;">Account Recovery</h1>
                        </div>
                        
                        <p style="color: #334155; font-size: 16px; line-height: 1.6;">
                            A recovery request was made for site <strong>{site_id}</strong>.
                        </p>
                        
                        <p style="color: #334155; font-size: 16px; line-height: 1.6;">
                            Click the button below to reset your passkey and regain access to your account:
                        </p>
                        
                        <div style="text-align: center; margin: 32px 0;">
                            <a href="{recovery_url}" style="display: inline-block; background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                                Recover Account
                            </a>
                        </div>
                        
                        <p style="color: #64748b; font-size: 14px; line-height: 1.6;">
                            This link expires in 15 minutes and can only be used once.
                        </p>
                        
                        <p style="color: #64748b; font-size: 14px; line-height: 1.6;">
                            If you didn't request this recovery, someone may have access to your API key. 
                            You should rotate your API keys immediately.
                        </p>
                        
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 32px 0;">
                        
                        <p style="color: #94a3b8; font-size: 12px;">
                            Request IP: {client_ip}<br>
                            Site ID: {site_id}
                        </p>
                    </div>
                    """,
                    text=f"""
Account Recovery for {site_id}

A recovery request was made for your Lemma.id account.

Click here to recover your account: {recovery_url}

This link expires in 15 minutes.

If you didn't request this, rotate your API keys immediately.

Request IP: {client_ip}
                    """
                )
                
                logger.info(f"Recovery email sent for site {site_id} to {admin_email[:3]}***")
                
            except Exception as e:
                logger.error(f"Failed to send recovery email: {e}")
                # Still return success to not reveal info
            
            return jsonify({
                'success': True,
                'message': 'If the API key is valid, a recovery link has been sent to the admin email.'
            })
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Recovery initiation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'Recovery failed. Please try again later.'
        }), 500


@account_recovery_bp.route('/api/recovery/validate', methods=['POST'])
@cross_origin()
def validate_recovery_token():
    """Validate a recovery token (used by frontend before showing passkey registration)"""
    try:
        data = request.get_json() or {}
        token = data.get('token', '').strip()
        
        if not token:
            return jsonify({'success': False, 'error': 'Token required'}), 400
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        clean_expired_tokens()
        
        token_data = recovery_tokens.get(token_hash)
        
        if not token_data:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 400
        
        if token_data['used']:
            return jsonify({'success': False, 'error': 'Token already used'}), 400
        
        if token_data['expires_at'] < datetime.now(timezone.utc):
            return jsonify({'success': False, 'error': 'Token expired'}), 400
        
        # Return site info (masked email)
        email = token_data['admin_email']
        masked_email = email[:3] + '***' + email[email.index('@'):] if '@' in email else '***'
        
        return jsonify({
            'success': True,
            'site_id': token_data['site_id'],
            'email': masked_email
        })
        
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        return jsonify({'success': False, 'error': 'Validation failed'}), 500


@account_recovery_bp.route('/api/recovery/complete', methods=['POST'])
@cross_origin()
def complete_recovery():
    """
    Complete account recovery - registers new passkey credential
    """
    try:
        data = request.get_json() or {}
        token = data.get('token', '').strip()
        credential = data.get('credential')  # WebAuthn credential from passkey registration
        
        if not token:
            return jsonify({'success': False, 'error': 'Token required'}), 400
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        clean_expired_tokens()
        
        token_data = recovery_tokens.get(token_hash)
        
        if not token_data:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 400
        
        if token_data['used']:
            return jsonify({'success': False, 'error': 'Token already used'}), 400
        
        if token_data['expires_at'] < datetime.now(timezone.utc):
            return jsonify({'success': False, 'error': 'Token expired'}), 400
        
        # Mark token as used
        recovery_tokens[token_hash]['used'] = True
        
        site_id = token_data['site_id']
        admin_email = token_data['admin_email']
        
        # If credential provided, register it as new passkey
        if credential:
            try:
                from api.passkey_auth import store_passkey_credential
                
                # Store the new passkey credential for this user
                store_passkey_credential(
                    user_email=admin_email,
                    site_id='lemma.id',  # This is for lemma.id platform auth
                    credential_data=credential
                )
                
                logger.info(f"Recovery complete - new passkey registered for {admin_email[:3]}*** (site: {site_id})")
                
            except Exception as e:
                logger.error(f"Failed to store passkey during recovery: {e}")
                return jsonify({'success': False, 'error': 'Failed to register passkey'}), 500
        
        # Log recovery completion
        logger.info(f"Account recovery completed for site {site_id}")
        
        return jsonify({
            'success': True,
            'message': 'Account recovered successfully',
            'site_id': site_id,
            'redirect': '/developer'
        })
        
    except Exception as e:
        logger.error(f"Recovery completion failed: {e}")
        return jsonify({'success': False, 'error': 'Recovery failed'}), 500
