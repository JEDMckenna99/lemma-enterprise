#!/usr/bin/env python3
"""
Wallet Transfer Session API - QR Trigger Approach
Handles real-time wallet transfers between devices
Multi-dyno compatible with Redis fallback
"""

from flask import Blueprint, request, jsonify, Response
from flask_cors import cross_origin
import json
import time
import uuid
import hashlib
import threading
import os
from datetime import datetime, timedelta

# Try Redis first, fallback to in-memory
try:
    import redis
    REDIS_URL = os.environ.get('REDIS_URL') or os.environ.get('REDISCLOUD_URL')
    print(f"🔍 REDIS DEBUG: REDIS_URL={os.environ.get('REDIS_URL')}")
    print(f"🔍 REDIS DEBUG: REDISCLOUD_URL={os.environ.get('REDISCLOUD_URL')}")
    print(f"🔍 REDIS DEBUG: Final URL={REDIS_URL}")
    
    if REDIS_URL:
        print(f"🔴 REDIS: Attempting connection to {REDIS_URL[:30]}...")
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # Test connection
        ping_result = redis_client.ping()
        print(f"🔴 REDIS: Ping result: {ping_result}")
        USE_REDIS = True
        print(f"🔴 REDIS: Connected successfully for session storage")
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

@wallet_transfer_bp.route('/api/wallet/transfer/create-session', methods=['POST'])
@cross_origin()
def create_transfer_session():
    """
    Create a new wallet transfer session
    Returns QR data for scanning
    """
    try:
        data = request.get_json()
        
        if not data or 'device_id' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing device_id'
            }), 400
        
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
            return jsonify({
                'success': False,
                'error': 'Failed to store session'
            }), 500
            
        debug_session_state("SESSION CREATED", session.session_id)
        
        print(f"✅ Created transfer session {session.session_id} for device {device_id[:8]}...")
        
        return jsonify({
            'success': True,
            'session_id': session.session_id,
            'qr_data': session.to_qr_data(),
            'expires_at': int(session.expires_at.timestamp() * 1000)
        })
        
    except Exception as e:
        print(f"❌ Failed to create transfer session: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@wallet_transfer_bp.route('/api/wallet/transfer/set-wallet', methods=['POST'])
@cross_origin()
def set_wallet_data():
    """
    Set wallet data for an existing transfer session
    """
    try:
        data = request.get_json()
        
        if not data or 'session_id' not in data or 'wallet_data' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing session_id or wallet_data'
            }), 400
        
        session_id = data['session_id']
        wallet_data = data['wallet_data']
        
        debug_session_state("SET WALLET LOOKUP", session_id)
        
        # Get session from storage
        session_data = _storage.get_session(session_id)
        if not session_data:
            debug_session_state("SESSION NOT FOUND", session_id)
            return jsonify({
                'success': False,
                'error': 'Transfer session not found'
            }), 404
        
        # Check if expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if datetime.now() > expires_at:
            _storage.delete_session(session_id)
            return jsonify({
                'success': False,
                'error': 'Transfer session expired'
            }), 410
        
        # Update session data
        session_data['wallet_data'] = wallet_data
        session_data['status'] = 'ready'
        
        if not _storage.set_session(session_id, session_data):
            return jsonify({
                'success': False,
                'error': 'Failed to update session'
            }), 500
            
        debug_session_state("WALLET DATA SET", session_id)
        print(f"✅ Wallet data set for session {session_id}")
        
        return jsonify({
            'success': True,
            'status': 'ready'
        })
        
    except Exception as e:
        print(f"❌ Failed to set wallet data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@wallet_transfer_bp.route('/api/wallet/transfer/get-wallet', methods=['POST'])
@cross_origin()
def get_wallet_data():
    """
    Get wallet data from transfer session
    """
    try:
        data = request.get_json()
        
        if not data or 'session_id' not in data or 'transfer_key' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing session_id or transfer_key'
            }), 400
        
        session_id = data['session_id']
        transfer_key = data['transfer_key']
        target_device_id = data.get('target_device_id', 'unknown')
        
        debug_session_state("GET WALLET LOOKUP", session_id)
        
        # Get session from storage
        session_data = _storage.get_session(session_id)
        if not session_data:
            return jsonify({
                'success': False,
                'error': 'Transfer session not found'
            }), 404
        
        # Check if expired
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if datetime.now() > expires_at:
            _storage.delete_session(session_id)
            return jsonify({
                'success': False,
                'error': 'Transfer session expired'
            }), 410
        
        if session_data['transfer_key'] != transfer_key:
            return jsonify({
                'success': False,
                'error': 'Invalid transfer key'
            }), 403
        
        if not session_data['wallet_data']:
            return jsonify({
                'success': False,
                'error': 'Wallet data not ready yet'
            }), 202  # Accepted, but not ready
        
        # Mark as completed but keep session for multiple retrievals
        wallet_data = session_data['wallet_data']
        session_data['status'] = 'completed'
        session_data['target_device_id'] = target_device_id
        
        # Keep session alive for cross-browser sync (will auto-expire in 5 minutes)
        _storage.set_session(session_id, session_data)  # Update but don't delete
        
        print(f"✅ Wallet transferred from session {session_id} to device {target_device_id[:8]}...")
        
        return jsonify({
            'success': True,
            'wallet_data': wallet_data,
            'transfer_completed': True
        })
        
    except Exception as e:
        print(f"❌ Failed to get wallet data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@wallet_transfer_bp.route('/api/wallet/transfer/status/<session_id>', methods=['GET'])
@cross_origin()
def get_transfer_status(session_id):
    """
    Get transfer session status
    """
    try:
        transfer_sessions, transfer_lock = get_transfer_sessions()
        with transfer_lock:
            if session_id not in transfer_sessions:
                return jsonify({
                    'success': False,
                    'error': 'Transfer session not found'
                }), 404
            
            session = transfer_sessions[session_id]
            
            if session.is_expired():
                del transfer_sessions[session_id]
                return jsonify({
                    'success': False,
                    'error': 'Transfer session expired'
                }), 410
        
        return jsonify({
            'success': True,
            'status': session.status,
            'expires_at': int(session.expires_at.timestamp() * 1000),
            'has_wallet_data': bool(session.wallet_data)
        })
        
    except Exception as e:
        print(f"❌ Failed to get transfer status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
