#!/usr/bin/env python3
"""
Wallet Transfer Session API - QR Trigger Approach
Handles real-time wallet transfers between devices
Multi-dyno compatible with Redis fallback
"""

from flask import Blueprint, request, jsonify, make_response
import json
import time
import uuid
import hashlib
import threading
import os
from datetime import datetime, timedelta

from api.wallet_session_sync import (
    SESSION_COOKIE_NAME,
    validate_session_token,
    _cors_headers,
    _origin_allowed,
    _validate_csrf,
)

# Try Redis first, fallback to in-memory
try:
    import redis
    # Prefer REDISCLOUD_URL (non-SSL) over REDIS_URL (SSL with cert issues)
    REDIS_URL = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL')
    
    if REDIS_URL:
        # Handle SSL Redis with cert issues
        if REDIS_URL.startswith('rediss://'):
            redis_client = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
        else:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            
        # Test connection
        redis_client.ping()
        USE_REDIS = True
        print(f"🔴 REDIS: Connected for multi-dyno session storage")
    else:
        USE_REDIS = False
        print("⚠️ REDIS: No REDIS_URL or REDISCLOUD_URL found, using in-memory storage")
except Exception as e:
    USE_REDIS = False
    print(f"⚠️ REDIS: Connection failed ({type(e).__name__}: {e}), using in-memory storage")

wallet_transfer_bp = Blueprint('wallet_transfer', __name__)

# Multi-dyno compatible session storage
class SessionStorage:
    def __init__(self):
        self.lock = threading.Lock()
        if USE_REDIS:
            print("🔴 REDIS: Using Redis for session storage")
        else:
            self.sessions = {}
            print(f"🔧 IN-MEMORY: Session storage initialized at memory {id(self.sessions)}")
    
    def set_session(self, session_id, session_data):
        """Store session data"""
        if USE_REDIS:
            try:
                # Store as JSON with 5 minute expiry
                redis_client.setex(
                    f"transfer_session:{session_id}",
                    300,  # 5 minutes
                    json.dumps(session_data)
                )
                return True
            except Exception as e:
                print(f"❌ REDIS SET failed: {e}")
                return False
        else:
            with self.lock:
                self.sessions[session_id] = session_data
                return True
    
    def get_session(self, session_id):
        """Retrieve session data"""
        if USE_REDIS:
            try:
                data = redis_client.get(f"transfer_session:{session_id}")
                if data:
                    return json.loads(data)
                return None
            except Exception as e:
                print(f"❌ REDIS GET failed: {e}")
                return None
        else:
            with self.lock:
                return self.sessions.get(session_id)
    
    def delete_session(self, session_id):
        """Delete session data"""
        if USE_REDIS:
            try:
                redis_client.delete(f"transfer_session:{session_id}")
                return True
            except Exception as e:
                print(f"❌ REDIS DELETE failed: {e}")
                return False
        else:
            with self.lock:
                if session_id in self.sessions:
                    del self.sessions[session_id]
                return True
    
    def list_sessions(self):
        """List all session IDs"""
        if USE_REDIS:
            try:
                keys = redis_client.keys("transfer_session:*")
                return [key.replace("transfer_session:", "") for key in keys]
            except Exception as e:
                print(f"❌ REDIS LIST failed: {e}")
                return []
        else:
            with self.lock:
                return list(self.sessions.keys())

# Global session storage instance
_storage = SessionStorage()

# Debug: Track session operations
session_operation_count = 0

def debug_session_state(operation, session_id=None):
    global session_operation_count
    session_operation_count += 1
    session_keys = _storage.list_sessions()
    storage_type = "REDIS" if USE_REDIS else "IN-MEMORY"
    
    print(f"🔍 DEBUG #{session_operation_count}: {operation}")
    print(f"📊 Current sessions: {len(session_keys)} ({storage_type})")
    print(f"📋 Session keys: {session_keys}")
    if session_id:
        print(f"🎯 Target session: {session_id}")
    print("---")

class TransferSession:
    def __init__(self, source_device_id, wallet_data=None):
        self.session_id = str(uuid.uuid4())[:12]  # Short session ID
        self.source_device_id = source_device_id
        self.transfer_key = hashlib.sha256(f"{self.session_id}_{time.time()}".encode()).hexdigest()[:32]
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(minutes=5)
        self.wallet_data = wallet_data
        self.status = 'waiting'  # waiting, ready, completed, expired
        self.target_device_id = None
        
    def to_qr_data(self):
        """Generate minimal data for QR code"""
        return {
            'type': 'lemma_transfer_token',
            'session_id': self.session_id,
            'transfer_key': self.transfer_key,
            'expires_at': int(self.expires_at.timestamp() * 1000),
            'source_device': self.source_device_id[:8]  # Truncated for privacy
        }
    
    def is_expired(self):
        return datetime.now() > self.expires_at

@wallet_transfer_bp.route('/api/wallet/transfer/create-session', methods=['POST', 'OPTIONS'])
def create_transfer_session():
    """
    Create a new wallet transfer session
    Returns QR data for scanning
    
    SECURITY: Only the PIN-protected /wallet page can initiate transfers
    """
    try:
        if request.method == 'OPTIONS':
            response = make_response()
            origin = request.headers.get('Origin')
            response.headers.update(_cors_headers(origin))
            if not _origin_allowed(origin):
                return response, 403
            return response

        origin = request.headers.get('Origin')
        if not _origin_allowed(origin):
            return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403

        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_token or not validate_session_token(session_token):
            response = jsonify({'success': False, 'error': 'not_authenticated'})
            response.headers.update(_cors_headers(origin))
            return response, 401

        if not _validate_csrf():
            response = jsonify({'success': False, 'error': 'csrf_missing_or_invalid'})
            response.headers.update(_cors_headers(origin))
            return response, 403
        
        data = request.get_json()
        
        if not data or 'device_id' not in data:
            response = jsonify({
                'success': False,
                'error': 'Missing device_id'
            })
            response.status_code = 400
            response.headers.update(_cors_headers(origin))
            return response
        
        device_id = data['device_id']
        wallet_data = data.get('wallet_data')  # Optional - can be set later
        
        # Create transfer session
        session = TransferSession(device_id, wallet_data)
        
        # Store session using new storage system
        session_data = {
            'session_id': session.session_id,
            'source_device_id': session.source_device_id,
            'transfer_key': session.transfer_key,
            'created_at': session.created_at.isoformat(),
            'expires_at': session.expires_at.isoformat(),
            'wallet_data': session.wallet_data,
            'status': session.status,
            'target_device_id': session.target_device_id
        }
        
        if not _storage.set_session(session.session_id, session_data):
            response = jsonify({
                'success': False,
                'error': 'Failed to store session'
            })
            response.status_code = 500
            response.headers.update(_cors_headers(origin))
            return response
            
        debug_session_state("SESSION CREATED", session.session_id)
        
        print(f"✅ Created transfer session {session.session_id} for device {device_id[:8]}...")
        
        response = jsonify({
            'success': True,
            'session_id': session.session_id,
            'qr_data': session.to_qr_data(),
            'expires_at': int(session.expires_at.timestamp() * 1000)
        })
        response.headers.update(_cors_headers(origin))
        return response
        
    except Exception as e:
        print(f"❌ Failed to create transfer session: {e}")
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.status_code = 500
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        return response

@wallet_transfer_bp.route('/api/wallet/transfer/set-wallet', methods=['POST', 'OPTIONS'])
def set_wallet_data():
    """
    Set wallet data for an existing transfer session
    
    SECURITY: Only the PIN-protected /wallet page can set wallet data
    """
    try:
        if request.method == 'OPTIONS':
            response = make_response()
            origin = request.headers.get('Origin')
            response.headers.update(_cors_headers(origin))
            if not _origin_allowed(origin):
                return response, 403
            return response

        origin = request.headers.get('Origin')
        if not _origin_allowed(origin):
            return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403

        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_token or not validate_session_token(session_token):
            response = jsonify({'success': False, 'error': 'not_authenticated'})
            response.headers.update(_cors_headers(origin))
            return response, 401

        if not _validate_csrf():
            response = jsonify({'success': False, 'error': 'csrf_missing_or_invalid'})
            response.headers.update(_cors_headers(origin))
            return response, 403
        
        data = request.get_json()
        
        if not data or 'session_id' not in data or 'wallet_data' not in data:
            response = jsonify({
                'success': False,
                'error': 'Missing session_id or wallet_data'
            })
            response.status_code = 400
            response.headers.update(_cors_headers(origin))
            return response
        
        session_id = data['session_id']
        wallet_data = data['wallet_data']
        
        debug_session_state("SET WALLET LOOKUP", session_id)
        
        # Get session from storage
        session_data = _storage.get_session(session_id)
        if not session_data:
            debug_session_state("SESSION NOT FOUND", session_id)
            response = jsonify({
                'success': False,
                'error': 'Transfer session not found'
            })
            response.status_code = 404
            response.headers.update(_cors_headers(origin))
            return response
        
        # Check if expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if datetime.now() > expires_at:
            _storage.delete_session(session_id)
            response = jsonify({
                'success': False,
                'error': 'Transfer session expired'
            })
            response.status_code = 410
            response.headers.update(_cors_headers(origin))
            return response
        
        # Update session data
        session_data['wallet_data'] = wallet_data
        session_data['status'] = 'ready'
        
        if not _storage.set_session(session_id, session_data):
            response = jsonify({
                'success': False,
                'error': 'Failed to update session'
            })
            response.status_code = 500
            response.headers.update(_cors_headers(origin))
            return response
            
        debug_session_state("WALLET DATA SET", session_id)
        print(f"✅ Wallet data set for session {session_id}")
        
        response = jsonify({
            'success': True,
            'status': 'ready'
        })
        response.headers.update(_cors_headers(origin))
        return response
        
    except Exception as e:
        print(f"❌ Failed to set wallet data: {e}")
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.status_code = 500
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        return response

@wallet_transfer_bp.route('/api/wallet/transfer/get-wallet', methods=['POST', 'OPTIONS'])
def get_wallet_data():
    """
    Get wallet data from transfer session
    """
    try:
        if request.method == 'OPTIONS':
            response = make_response()
            origin = request.headers.get('Origin')
            response.headers.update(_cors_headers(origin))
            if not _origin_allowed(origin):
                return response, 403
            return response

        origin = request.headers.get('Origin')
        if not _origin_allowed(origin):
            return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403

        data = request.get_json()
        
        if not data or 'session_id' not in data or 'transfer_key' not in data:
            response = jsonify({
                'success': False,
                'error': 'Missing session_id or transfer_key'
            })
            response.status_code = 400
            response.headers.update(_cors_headers(origin))
            return response
        
        session_id = data['session_id']
        transfer_key = data['transfer_key']
        target_device_id = data.get('target_device_id', 'unknown')
        
        debug_session_state("GET WALLET LOOKUP", session_id)
        
        # Get session from storage
        session_data = _storage.get_session(session_id)
        if not session_data:
            response = jsonify({
                'success': False,
                'error': 'Transfer session not found'
            })
            response.status_code = 404
            response.headers.update(_cors_headers(origin))
            return response
        
        # Check if expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if datetime.now() > expires_at:
            _storage.delete_session(session_id)
            response = jsonify({
                'success': False,
                'error': 'Transfer session expired'
            })
            response.status_code = 410
            response.headers.update(_cors_headers(origin))
            return response
        
        if session_data['transfer_key'] != transfer_key:
            response = jsonify({
                'success': False,
                'error': 'Invalid transfer key'
            })
            response.status_code = 403
            response.headers.update(_cors_headers(origin))
            return response
        
        if not session_data['wallet_data']:
            response = jsonify({
                'success': False,
                'error': 'Wallet data not ready yet'
            })
            response.status_code = 202  # Accepted, but not ready
            response.headers.update(_cors_headers(origin))
            return response
        
        # Mark as completed but keep session for multiple retrievals
        wallet_data = session_data['wallet_data']
        session_data['status'] = 'completed'
        session_data['target_device_id'] = target_device_id
        
        # Keep session alive for cross-browser sync (will auto-expire in 5 minutes)
        _storage.set_session(session_id, session_data)  # Update but don't delete
        
        print(f"✅ Wallet transferred from session {session_id} to device {target_device_id[:8]}...")
        
        response = jsonify({
            'success': True,
            'wallet_data': wallet_data,
            'transfer_completed': True
        })
        response.headers.update(_cors_headers(origin))
        return response
        
    except Exception as e:
        print(f"❌ Failed to get wallet data: {e}")
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.status_code = 500
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        return response

@wallet_transfer_bp.route('/api/wallet/transfer/status/<session_id>', methods=['GET', 'OPTIONS'])
def get_transfer_status(session_id):
    """
    Get transfer session status
    """
    try:
        if request.method == 'OPTIONS':
            response = make_response()
            origin = request.headers.get('Origin')
            response.headers.update(_cors_headers(origin))
            if not _origin_allowed(origin):
                return response, 403
            return response

        origin = request.headers.get('Origin')
        if not _origin_allowed(origin):
            return jsonify({'success': False, 'error': 'origin_not_allowed'}), 403

        transfer_sessions, transfer_lock = get_transfer_sessions()
        with transfer_lock:
            if session_id not in transfer_sessions:
            response = jsonify({
                    'success': False,
                    'error': 'Transfer session not found'
            })
            response.status_code = 404
                response.headers.update(_cors_headers(origin))
                return response
            
            session = transfer_sessions[session_id]
            
            if session.is_expired():
                del transfer_sessions[session_id]
            response = jsonify({
                    'success': False,
                    'error': 'Transfer session expired'
            })
            response.status_code = 410
                response.headers.update(_cors_headers(origin))
                return response
        
        response = jsonify({
            'success': True,
            'status': session.status,
            'expires_at': int(session.expires_at.timestamp() * 1000),
            'has_wallet_data': bool(session.wallet_data)
        })
        response.headers.update(_cors_headers(origin))
        return response
        
    except Exception as e:
        print(f"❌ Failed to get transfer status: {e}")
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.status_code = 500
        origin = request.headers.get('Origin')
        response.headers.update(_cors_headers(origin))
        return response
