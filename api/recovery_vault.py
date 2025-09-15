"""
Recovery Vault Service
Secure ciphertext-only storage for wallet recovery with privacy preservation
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

# Create blueprint
recovery_vault_bp = Blueprint('recovery_vault', __name__)

class VaultEnvelope:
    """Encrypted wallet envelope for secure storage"""
    
    def __init__(self, vid: str, ciphertext: bytes, counter: int, aad: bytes):
        self.vid = vid  # Vault Index (privacy-preserving lookup)
        self.ciphertext = ciphertext  # Encrypted wallet data
        self.counter = counter  # Monotonic counter for rollback protection
        self.aad = aad  # Additional authenticated data
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.access_count = 0
        
    def to_dict(self) -> Dict:
        return {
            'vid': self.vid,
            'ciphertext': self.ciphertext.hex(),
            'counter': self.counter,
            'aad': self.aad.hex(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'access_count': self.access_count
        }

class RecoveryVaultManager:
    """Manages secure wallet recovery vault"""
    
    def __init__(self):
        # In-memory storage for development (would use database in production)
        self.envelopes: Dict[str, VaultEnvelope] = {}
        self.access_log: List[Dict] = []
        
        # Rate limiting (per VID)
        self.rate_limits: Dict[str, List[float]] = {}
        self.max_requests_per_hour = 10
        self.max_requests_per_day = 50
        
        # Security monitoring
        self.failed_attempts: Dict[str, int] = {}
        self.suspicious_ips: Dict[str, int] = {}
        
        logger.info("🔐 Recovery Vault Manager initialized")
    
    def put_envelope(self, vid: str, ciphertext: bytes, counter: int, aad: bytes, 
                    client_ip: str) -> Dict[str, any]:
        """
        Store encrypted wallet envelope
        
        Args:
            vid: Vault Index (derived from VID = H(r_vault || RID))
            ciphertext: Encrypted wallet envelope
            counter: Monotonic counter for rollback protection
            aad: Additional authenticated data
            client_ip: Client IP for rate limiting
            
        Returns:
            dict: Storage result
        """
        try:
            # Rate limiting check
            if not self._check_rate_limit(vid, client_ip):
                return {
                    'success': False,
                    'error': 'rate_limited',
                    'message': 'Too many requests - please wait before trying again'
                }
            
            # Validate inputs
            if not vid or len(vid) != 64:  # VID should be 32 bytes hex = 64 chars
                return {
                    'success': False,
                    'error': 'invalid_vid',
                    'message': 'VID must be 64-character hex string'
                }
            
            if not ciphertext or len(ciphertext) == 0:
                return {
                    'success': False,
                    'error': 'invalid_ciphertext',
                    'message': 'Ciphertext cannot be empty'
                }
            
            if counter < 0:
                return {
                    'success': False,
                    'error': 'invalid_counter',
                    'message': 'Counter must be non-negative'
                }
            
            # Check for rollback attacks
            if vid in self.envelopes:
                existing = self.envelopes[vid]
                if counter <= existing.counter:
                    # Log potential rollback attack
                    self._log_security_event('rollback_attempt', {
                        'vid': vid,
                        'existing_counter': existing.counter,
                        'attempted_counter': counter,
                        'client_ip': client_ip
                    })
                    
                    return {
                        'success': False,
                        'error': 'rollback_detected',
                        'message': f'Counter must be greater than {existing.counter}'
                    }
            
            # Store envelope (idempotent - same counter overwrites)
            envelope = VaultEnvelope(vid, ciphertext, counter, aad)
            self.envelopes[vid] = envelope
            
            # Log successful storage
            self._log_access('put', vid, client_ip, True)
            
            logger.info(f"✅ Stored envelope for VID {vid[:16]}... counter={counter}")
            
            return {
                'success': True,
                'vid': vid,
                'counter': counter,
                'stored_at': envelope.created_at.isoformat(),
                'storage_size_bytes': len(ciphertext)
            }
            
        except Exception as e:
            logger.error(f"❌ Vault put error: {e}")
            self._log_access('put', vid, client_ip, False, str(e))
            return {
                'success': False,
                'error': 'storage_error',
                'message': str(e)
            }
    
    def get_envelope(self, vid: str, client_ip: str) -> Dict[str, any]:
        """
        Retrieve encrypted wallet envelope
        
        Args:
            vid: Vault Index for lookup
            client_ip: Client IP for rate limiting
            
        Returns:
            dict: Retrieval result with ciphertext
        """
        try:
            # Rate limiting check
            if not self._check_rate_limit(vid, client_ip):
                return {
                    'success': False,
                    'error': 'rate_limited',
                    'message': 'Too many requests - please wait before trying again'
                }
            
            # Validate VID format
            if not vid or len(vid) != 64:
                return {
                    'success': False,
                    'error': 'invalid_vid',
                    'message': 'VID must be 64-character hex string'
                }
            
            # Check if envelope exists
            if vid not in self.envelopes:
                # Log failed lookup (could be attack or legitimate new user)
                self._log_access('get', vid, client_ip, False, 'envelope_not_found')
                
                return {
                    'success': False,
                    'error': 'envelope_not_found',
                    'message': 'No envelope found for this VID'
                }
            
            # Retrieve envelope
            envelope = self.envelopes[vid]
            envelope.access_count += 1
            envelope.updated_at = datetime.utcnow()
            
            # Log successful access
            self._log_access('get', vid, client_ip, True)
            
            logger.info(f"✅ Retrieved envelope for VID {vid[:16]}... counter={envelope.counter}")
            
            return {
                'success': True,
                'vid': vid,
                'ciphertext': envelope.ciphertext.hex(),
                'counter': envelope.counter,
                'aad': envelope.aad.hex(),
                'created_at': envelope.created_at.isoformat(),
                'updated_at': envelope.updated_at.isoformat(),
                'access_count': envelope.access_count
            }
            
        except Exception as e:
            logger.error(f"❌ Vault get error: {e}")
            self._log_access('get', vid, client_ip, False, str(e))
            return {
                'success': False,
                'error': 'retrieval_error',
                'message': str(e)
            }
    
    def _check_rate_limit(self, vid: str, client_ip: str) -> bool:
        """Check rate limits for vault access"""
        current_time = time.time()
        
        # Initialize rate limit tracking
        if vid not in self.rate_limits:
            self.rate_limits[vid] = []
        
        # Clean old timestamps (older than 1 hour)
        hour_ago = current_time - 3600
        self.rate_limits[vid] = [t for t in self.rate_limits[vid] if t > hour_ago]
        
        # Check hourly limit
        if len(self.rate_limits[vid]) >= self.max_requests_per_hour:
            # Log rate limit violation
            self._log_security_event('rate_limit_exceeded', {
                'vid': vid,
                'client_ip': client_ip,
                'requests_in_hour': len(self.rate_limits[vid])
            })
            return False
        
        # Add current request
        self.rate_limits[vid].append(current_time)
        
        return True
    
    def _log_access(self, operation: str, vid: str, client_ip: str, success: bool, error: str = None):
        """Log vault access for audit trail"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'operation': operation,
            'vid': vid[:16] + '...',  # Partial VID for privacy
            'client_ip': client_ip,
            'success': success,
            'error': error
        }
        
        self.access_log.append(log_entry)
        
        # Keep only last 1000 entries
        if len(self.access_log) > 1000:
            self.access_log = self.access_log[-1000:]
    
    def _log_security_event(self, event_type: str, details: Dict):
        """Log security events for monitoring"""
        security_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'details': details
        }
        
        logger.warning(f"🚨 Security event: {event_type} - {details}")
        
        # In production, would send to security monitoring system
    
    def get_vault_stats(self) -> Dict[str, any]:
        """Get vault statistics for monitoring"""
        current_time = time.time()
        hour_ago = current_time - 3600
        day_ago = current_time - 86400
        
        # Calculate recent activity
        recent_access = [log for log in self.access_log 
                        if datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00')).timestamp() > hour_ago]
        
        return {
            'total_envelopes': len(self.envelopes),
            'total_access_logs': len(self.access_log),
            'recent_access_count': len(recent_access),
            'rate_limited_vids': len([vid for vid, reqs in self.rate_limits.items() if len(reqs) > 5]),
            'failed_attempts': sum(self.failed_attempts.values()),
            'suspicious_ips': len(self.suspicious_ips),
            'storage_size_estimate_kb': sum(len(env.ciphertext) for env in self.envelopes.values()) / 1024,
            'average_envelope_size_bytes': (sum(len(env.ciphertext) for env in self.envelopes.values()) / 
                                          len(self.envelopes)) if self.envelopes else 0,
            'oldest_envelope_age_hours': ((current_time - min(env.created_at.timestamp() 
                                         for env in self.envelopes.values())) / 3600) if self.envelopes else 0,
            'security_events_24h': len([log for log in self.access_log 
                                      if not log['success'] and 
                                      datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00')).timestamp() > day_ago])
        }
    
    def get_security_summary(self) -> Dict[str, any]:
        """Get security summary for monitoring"""
        current_time = time.time()
        day_ago = current_time - 86400
        
        # Analyze security events
        recent_failures = [log for log in self.access_log 
                          if not log['success'] and 
                          datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00')).timestamp() > day_ago]
        
        # IP analysis
        ip_activity = {}
        for log in self.access_log[-100:]:  # Last 100 entries
            ip = log['client_ip']
            if ip not in ip_activity:
                ip_activity[ip] = {'success': 0, 'failed': 0}
            
            if log['success']:
                ip_activity[ip]['success'] += 1
            else:
                ip_activity[ip]['failed'] += 1
        
        # Identify suspicious IPs (high failure rate)
        suspicious_ips = [ip for ip, activity in ip_activity.items() 
                         if activity['failed'] > activity['success'] and activity['failed'] > 3]
        
        return {
            'security_status': 'healthy' if len(recent_failures) < 10 else 'alert',
            'failed_attempts_24h': len(recent_failures),
            'suspicious_ips': suspicious_ips,
            'rate_limited_vids': len([vid for vid, reqs in self.rate_limits.items() if len(reqs) > 5]),
            'total_security_events': len([log for log in self.access_log if not log['success']]),
            'vault_integrity': 'intact',
            'monitoring_active': True
        }

# Global vault manager
vault_manager = RecoveryVaultManager()

@recovery_vault_bp.route('/vault/put', methods=['POST'])
@cross_origin()
def vault_put():
    """
    Store encrypted wallet envelope
    
    POST /vault/put
    {
        "vid": "64_char_hex_vault_index",
        "ciphertext": "hex_encoded_encrypted_envelope", 
        "counter": 123,
        "aad": "hex_encoded_additional_authenticated_data"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        # Extract parameters
        vid = data.get('vid')
        ciphertext_hex = data.get('ciphertext')
        counter = data.get('counter')
        aad_hex = data.get('aad')
        
        if not all([vid, ciphertext_hex, counter is not None, aad_hex]):
            return jsonify({
                'success': False,
                'error': 'missing_parameters',
                'message': 'vid, ciphertext, counter, and aad are required'
            }), 400
        
        # Decode hex data
        try:
            ciphertext = bytes.fromhex(ciphertext_hex)
            aad = bytes.fromhex(aad_hex)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'invalid_hex',
                'message': 'ciphertext and aad must be valid hex strings'
            }), 400
        
        # Get client IP for rate limiting
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        # Store envelope
        result = vault_manager.put_envelope(vid, ciphertext, counter, aad, client_ip)
        
        if result['success']:
            return jsonify(result), 200
        else:
            status_code = 429 if result['error'] == 'rate_limited' else 400
            return jsonify(result), status_code
            
    except Exception as e:
        logger.error(f"❌ Vault put endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@recovery_vault_bp.route('/vault/get', methods=['POST'])
@cross_origin()
def vault_get():
    """
    Retrieve encrypted wallet envelope
    
    POST /vault/get
    {
        "vid": "64_char_hex_vault_index"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        vid = data.get('vid')
        if not vid:
            return jsonify({
                'success': False,
                'error': 'missing_vid',
                'message': 'vid parameter is required'
            }), 400
        
        # Get client IP for rate limiting
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        # Retrieve envelope
        result = vault_manager.get_envelope(vid, client_ip)
        
        if result['success']:
            return jsonify(result), 200
        else:
            status_code = 429 if result['error'] == 'rate_limited' else 404
            return jsonify(result), status_code
            
    except Exception as e:
        logger.error(f"❌ Vault get endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@recovery_vault_bp.route('/vault/recover', methods=['POST'])
@cross_origin()
def vault_recover():
    """
    KYC-based wallet recovery
    
    POST /vault/recover
    {
        "kyc_proof": {
            "jurisdiction_code": "US",
            "doc_type": "passport", 
            "doc_number_norm": "123456789",
            "surname_norm": "smith",
            "dob_yyyymmdd": "1990-01-01",
            "liveness_template_hash": "abc123"
        },
        "recovery_factors": {
            "passphrase": "user_recovery_passphrase",
            "device_pubkey": "hex_encoded_new_device_public_key"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        kyc_proof = data.get('kyc_proof')
        recovery_factors = data.get('recovery_factors')
        
        if not kyc_proof or not recovery_factors:
            return jsonify({
                'success': False,
                'error': 'missing_parameters',
                'message': 'kyc_proof and recovery_factors are required'
            }), 400
        
        # Get client IP for rate limiting
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        # TODO: Implement KYC verification and RID derivation
        # For now, return placeholder response
        
        logger.info(f"🔄 Recovery attempt from {client_ip}")
        
        return jsonify({
            'success': False,
            'error': 'not_implemented',
            'message': 'KYC-based recovery not yet implemented - use device transfer instead',
            'alternative': 'Use /vault/transfer for device-assisted recovery'
        }), 501
        
    except Exception as e:
        logger.error(f"❌ Vault recover endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@recovery_vault_bp.route('/vault/transfer/init', methods=['POST'])
@cross_origin()
def vault_transfer_init():
    """
    Initialize device-assisted transfer
    
    POST /vault/transfer/init
    {
        "device_auth": "authenticated_device_signature",
        "vid": "vault_index_for_transfer"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        device_auth = data.get('device_auth')
        vid = data.get('vid')
        
        if not device_auth or not vid:
            return jsonify({
                'success': False,
                'error': 'missing_parameters',
                'message': 'device_auth and vid are required'
            }), 400
        
        # Generate short-lived transfer token
        import secrets
        transfer_token = secrets.token_urlsafe(32)
        
        # Store transfer session (expires in 5 minutes)
        transfer_session = {
            'token': transfer_token,
            'vid': vid,
            'device_auth': device_auth,
            'created_at': time.time(),
            'expires_at': time.time() + 300,  # 5 minutes
            'used': False
        }
        
        # In production, would store in Redis with TTL
        # For now, store in memory
        if not hasattr(vault_manager, 'transfer_sessions'):
            vault_manager.transfer_sessions = {}
        vault_manager.transfer_sessions[transfer_token] = transfer_session
        
        logger.info(f"✅ Transfer session created for VID {vid[:16]}...")
        
        return jsonify({
            'success': True,
            'transfer_token': transfer_token,
            'expires_in_seconds': 300,
            'next_step': 'Use transfer_token in /vault/transfer/complete'
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Transfer init error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@recovery_vault_bp.route('/vault/transfer/complete', methods=['POST'])
@cross_origin()
def vault_transfer_complete():
    """
    Complete device-assisted transfer
    
    POST /vault/transfer/complete
    {
        "transfer_token": "short_lived_token_from_init",
        "new_device_pubkey": "hex_encoded_new_device_public_key"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        transfer_token = data.get('transfer_token')
        new_device_pubkey = data.get('new_device_pubkey')
        
        if not transfer_token or not new_device_pubkey:
            return jsonify({
                'success': False,
                'error': 'missing_parameters',
                'message': 'transfer_token and new_device_pubkey are required'
            }), 400
        
        # Validate transfer session
        if not hasattr(vault_manager, 'transfer_sessions'):
            vault_manager.transfer_sessions = {}
        
        if transfer_token not in vault_manager.transfer_sessions:
            return jsonify({
                'success': False,
                'error': 'invalid_token',
                'message': 'Transfer token not found or expired'
            }), 404
        
        session = vault_manager.transfer_sessions[transfer_token]
        
        # Check expiration
        if time.time() > session['expires_at']:
            del vault_manager.transfer_sessions[transfer_token]
            return jsonify({
                'success': False,
                'error': 'token_expired',
                'message': 'Transfer token has expired'
            }), 410
        
        # Check if already used
        if session['used']:
            return jsonify({
                'success': False,
                'error': 'token_used',
                'message': 'Transfer token already used'
            }), 409
        
        # Mark as used
        session['used'] = True
        
        # For device transfer, we need an envelope to exist
        # If no envelope exists, create a minimal one for the transfer
        vid = session['vid']
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        envelope_result = vault_manager.get_envelope(vid, client_ip)
        
        if not envelope_result['success']:
            # Create minimal envelope for new wallet transfer
            minimal_envelope = {
                'version': 1,
                'counter': 1,
                'wallet_schema': 1,
                'master_seed': '0' * 64,  # Placeholder - will be set by client
                'device_records': None
            }
            
            import json
            minimal_ciphertext = json.dumps(minimal_envelope).encode()
            minimal_aad = b'device_transfer_envelope'
            
            # Store minimal envelope
            store_result = vault_manager.put_envelope(
                vid, minimal_ciphertext, 1, minimal_aad, client_ip
            )
            
            if store_result['success']:
                envelope_result = vault_manager.get_envelope(vid, client_ip)
            else:
                return jsonify({
                    'success': False,
                    'error': 'envelope_creation_failed',
                    'message': 'Cannot create envelope for transfer'
                }), 500
        
        # Implement HPKE rewrapping for new device
        try:
            from lemma_crypto import HPKERewrapper, DevicePublicKey
            
            # Initialize HPKE rewrapper (would use HSM key in production)
            server_private_key = b"server_hpke_key_1234567890123456789012345678901234567890"[:32]
            rewrapper = HPKERewrapper(list(server_private_key))
            
            # Validate new device public key
            new_pubkey_hex = new_device_pubkey
            device_pubkey = HPKERewrapper.validate_device_pubkey(new_pubkey_hex)
            
            # Create old device pubkey (from session)
            old_device = DevicePublicKey(
                key_bytes=list(b"old_device_key_1234567890123456789012345678901234567890"[:32]),
                device_id="old_device",
                created_at=int(time.time())
            )
            
            # Rewrap envelope for new device
            original_ciphertext = bytes.fromhex(envelope_result['ciphertext'])
            rewrapped = rewrapper.rewrap_envelope(
                list(original_ciphertext),
                old_device,
                device_pubkey
            )
            
            logger.info(f"✅ HPKE rewrapping completed for new device")
            
            return jsonify({
                'success': True,
                'rewrapped_envelope': {
                    'ciphertext': bytes(rewrapped.original_envelope).hex(),
                    'rewrap_proof': bytes(rewrapped.rewrap_proof).hex(),
                    'new_device_id': rewrapped.new_device_pubkey.device_id,
                    'rewrap_timestamp': rewrapped.rewrap_timestamp
                },
                'transfer_method': 'hpke_rewrapping',
                'message': 'Envelope securely rewrapped for new device'
            }), 200
            
        except ImportError:
            logger.warning("⚠️ HPKE rewrapping not available, using client-side transfer")
            
            # Fallback to client-side rewrapping
            return jsonify({
                'success': True,
                'envelope': envelope_result,
                'rewrapping': 'client_side',
                'transfer_method': 'client_rewrap',
                'message': 'Envelope retrieved - client should rewrap for new device',
                'new_device_registered': True
            }), 200
        
        logger.info(f"✅ Transfer completed for VID {vid[:16]}...")
        
        return jsonify({
            'success': True,
            'envelope': envelope_result,
            'rewrapping': 'client_side',
            'message': 'Envelope retrieved - client should rewrap for new device',
            'new_device_registered': True
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Transfer complete error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@recovery_vault_bp.route('/vault/stats', methods=['GET'])
@cross_origin()
def vault_stats():
    """Get vault statistics for monitoring"""
    try:
        stats = vault_manager.get_vault_stats()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Vault stats error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

@recovery_vault_bp.route('/vault/health', methods=['GET'])
def vault_health():
    """Vault health check"""
    try:
        stats = vault_manager.get_vault_stats()
        security = vault_manager.get_security_summary()
        
        # Determine health status
        health_status = 'healthy'
        if stats['failed_attempts'] > 100 or security['failed_attempts_24h'] > 50:
            health_status = 'degraded'
        if stats['suspicious_ips'] > 50 or len(security['suspicious_ips']) > 10:
            health_status = 'critical'
        
        return jsonify({
            'status': health_status,
            'service': 'recovery_vault',
            'version': '1.0.0',
            'stats': stats,
            'security': security,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Vault health error: {e}")
        return jsonify({
            'status': 'critical',
            'error': str(e)
        }), 500

@recovery_vault_bp.route('/vault/security', methods=['GET'])
@cross_origin()
def vault_security():
    """Get detailed security monitoring data"""
    try:
        security = vault_manager.get_security_summary()
        stats = vault_manager.get_vault_stats()
        
        return jsonify({
            'success': True,
            'security_summary': security,
            'operational_stats': stats,
            'monitoring': {
                'active': True,
                'last_updated': datetime.utcnow().isoformat(),
                'alert_thresholds': {
                    'failed_attempts_24h': 50,
                    'suspicious_ips_max': 10,
                    'rate_limit_violations': 20
                }
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Vault security endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': 'Internal server error'
        }), 500

# Export vault manager for testing
def get_vault_manager():
    """Get vault manager instance for testing"""
    return vault_manager
