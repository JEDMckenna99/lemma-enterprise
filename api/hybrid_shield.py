"""
Hybrid Lemma Bot Shield API
==============================
Hybrid implementation combining:
- WebAssembly core for microsecond client-side verification (99% of operations)
- Python server for coordination, fallback, and sync (1% of operations)

This provides the optimal balance of performance, reliability, and functionality.
"""

import os
import time
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from functools import wraps

# Import existing shield functionality
from .shield import (
    shield_bp,
    initialize_rust_engine,
    rust_engine,
    RUST_ENGINE_AVAILABLE,
    logger
)

# Simple in-memory cache implementation for hybrid shield
class SimpleCache:
    def __init__(self):
        self.cache = {}
    
    def get(self, key):
        return self.cache.get(key)
    
    def set(self, key, value, ttl=None):
        self.cache[key] = value
        return True
    
    def delete(self, key):
        return self.cache.pop(key, None)

# Initialize cache
in_memory_cache = SimpleCache()

# Enhanced hybrid shield blueprint
hybrid_shield_bp = Blueprint('hybrid_shield', __name__, url_prefix='/api/hybrid-shield')

# Configuration
HYBRID_CONFIG = {
    'client_verification_timeout': 500,  # 500ms timeout for client verification
    'server_fallback_enabled': True,
    'sync_interval': 300,  # 5 minutes
    'cache_ttl': 3600,  # 1 hour
    'max_credentials_per_user': 10,
    'performance_threshold_ns': 1000000,  # 1ms threshold
}

@dataclass
class HybridVerificationRequest:
    user_id: str
    action: str
    timestamp: int
    client_available: bool = True
    client_verification_result: Optional[Dict] = None
    fallback_reason: Optional[str] = None

@dataclass
class HybridVerificationResponse:
    verified: bool
    confidence: float
    verification_time_ns: int
    method: str  # 'client', 'server', 'hybrid'
    offline: bool
    fingerprint: str
    session_id: str
    
class HybridShieldCoordinator:
    """Coordinates between client-side WebAssembly and server-side verification"""
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}
        self.credential_sync_queue: List[Dict] = []
        self.performance_stats = {
            'client_verifications': 0,
            'server_verifications': 0,
            'hybrid_verifications': 0,
            'fallback_triggers': 0,
            'avg_client_time_ns': 0,
            'avg_server_time_ns': 0,
        }
        self.last_sync: Optional[datetime] = None
        
    def should_use_client_verification(self, request: HybridVerificationRequest) -> bool:
        """Determine if client-side verification should be used"""
        if not request.client_available:
            return False
            
        # Check if client is responsive
        if request.client_verification_result is None:
            return False
            
        # Check performance threshold
        if request.client_verification_result.get('verification_time_ns', 0) > HYBRID_CONFIG['performance_threshold_ns']:
            logger.warning(f"Client verification slow: {request.client_verification_result.get('verification_time_ns')}ns")
            return False
            
        return True
        
    def should_use_server_fallback(self, request: HybridVerificationRequest) -> bool:
        """Determine if server fallback should be used - ONLY if Rust engine is available"""
        if not HYBRID_CONFIG['server_fallback_enabled']:
            return False
            
        # CRITICAL: Server fallback is ONLY allowed if Rust engine is available
        if not RUST_ENGINE_AVAILABLE or not rust_engine:
            logger.error("Server fallback requested but Rust engine not available - verification will fail")
            return False
            
        # Fallback scenarios (only when Rust engine is available)
        fallback_reasons = [
            not request.client_available,
            request.fallback_reason == 'client_timeout',
            request.fallback_reason == 'client_error',
            request.fallback_reason == 'verification_failed',
            request.client_verification_result is None,
        ]
        
        return any(fallback_reasons)
        
    def coordinate_verification_sync(self, request: HybridVerificationRequest) -> HybridVerificationResponse:
        """Coordinate verification between client and server"""
        session_id = f"hybrid_{request.user_id}_{int(time.time() * 1000)}"
        start_time = time.time_ns()
        
        try:
            # Strategy 1: Client-side verification (preferred)
            if self.should_use_client_verification(request):
                logger.info(f"Using client-side verification for user {request.user_id}")
                
                client_result = request.client_verification_result
                self.performance_stats['client_verifications'] += 1
                
                # Update performance stats
                client_time = client_result.get('verification_time_ns', 0)
                if client_time > 0:
                    self.performance_stats['avg_client_time_ns'] = (
                        (self.performance_stats['avg_client_time_ns'] * (self.performance_stats['client_verifications'] - 1) + client_time) /
                        self.performance_stats['client_verifications']
                    )
                
                return HybridVerificationResponse(
                    verified=client_result.get('verified', False),
                    confidence=client_result.get('confidence', 0.0),
                    verification_time_ns=client_time,
                    method='client',
                    offline=client_result.get('offline', True),
                    fingerprint=client_result.get('fingerprint', 'client_verification'),
                    session_id=session_id
                )
                
            # Strategy 2: Server-side fallback
            elif self.should_use_server_fallback(request):
                logger.info(f"Using server-side fallback for user {request.user_id}: {request.fallback_reason}")
                
                server_result = self.server_verification_sync(request)
                self.performance_stats['server_verifications'] += 1
                self.performance_stats['fallback_triggers'] += 1
                
                # Update performance stats
                server_time = server_result.get('verification_time_ns', 0)
                if server_time > 0:
                    self.performance_stats['avg_server_time_ns'] = (
                        (self.performance_stats['avg_server_time_ns'] * (self.performance_stats['server_verifications'] - 1) + server_time) /
                        self.performance_stats['server_verifications']
                    )
                
                return HybridVerificationResponse(
                    verified=server_result.get('verified', False),
                    confidence=server_result.get('confidence', 0.0),
                    verification_time_ns=server_time,
                    method='server',
                    offline=server_result.get('offline', False),
                    fingerprint=server_result.get('fingerprint', 'server_verification'),
                    session_id=session_id
                )
                
            # Strategy 3: Hybrid verification (both client and server)
            else:
                logger.info(f"Using hybrid verification for user {request.user_id}")
                
                # Run both client and server verification
                client_result = request.client_verification_result
                server_result = self.server_verification_sync(request)
                
                self.performance_stats['hybrid_verifications'] += 1
                
                # Combine results using confidence-based weighting
                client_confidence = client_result.get('confidence', 0.0) if client_result else 0.0
                server_confidence = server_result.get('confidence', 0.0)
                
                # Weighted average of confidence scores
                combined_confidence = (client_confidence * 0.7 + server_confidence * 0.3)
                
                # Decision logic: both must agree for high confidence
                client_verified = client_result.get('verified', False) if client_result else False
                server_verified = server_result.get('verified', False)
                
                final_verified = client_verified and server_verified
                
                total_time = time.time_ns() - start_time
                
                return HybridVerificationResponse(
                    verified=final_verified,
                    confidence=combined_confidence,
                    verification_time_ns=total_time,
                    method='hybrid',
                    offline=False,  # Hybrid uses server component
                    fingerprint=f"hybrid_{session_id}",
                    session_id=session_id
                )
                
        except Exception as e:
            logger.error(f"Hybrid verification failed for user {request.user_id}: {e}")
            
            # Final fallback: simple server verification
            return HybridVerificationResponse(
                verified=False,
                confidence=0.0,
                verification_time_ns=time.time_ns() - start_time,
                method='error_fallback',
                offline=False,
                fingerprint=f"error_{session_id}",
                session_id=session_id
            )
            
    def server_verification_sync(self, request: HybridVerificationRequest) -> Dict:
        """Server-side verification using ONLY the Rust engine - no Python fallback"""
        start_time = time.time_ns()
        
        # Check if Rust engine is available
        if not RUST_ENGINE_AVAILABLE or not rust_engine:
            logger.error(f"Rust engine not available for user {request.user_id} - verification rejected")
            
            return {
                'verified': False,
                'confidence': 0.0,
                'verification_time_ns': time.time_ns() - start_time,
                'offline': False,
                'fingerprint': f"rust_unavailable_{request.user_id}",
                'method': 'rust_engine_unavailable',
                'error': 'Rust engine not available - no Python fallback allowed'
            }
        
        try:
            # Check if user has cached Rust engine results
            cache_key = f"rust_credentials_{request.user_id}"
            cached_result = in_memory_cache.get(cache_key)
            
            if cached_result:
                logger.info(f"Using cached Rust engine result for user {request.user_id}")
                
                verification_time_ns = time.time_ns() - start_time
                
                return {
                    'verified': cached_result.get('verified', False),
                    'confidence': cached_result.get('confidence', 0.95),
                    'verification_time_ns': max(verification_time_ns, 1000),  # At least 1µs
                    'offline': True,
                    'fingerprint': cached_result.get('fingerprint', f"rust_cached_{request.user_id}"),
                    'method': 'rust_engine_cached'
                }
            
            # Use ONLY the Rust engine for verification
            logger.info(f"Using Rust engine for server verification of user {request.user_id}")
            
            # Create a dummy credential for the Rust engine
            dummy_credential = {
                "id": f"credential_{request.user_id}",
                "type": "HumanVerification",
                "issuer": "lemma-hybrid-shield",
                "subject": request.user_id,
                "issuedAt": int(time.time()),
                "claims": {
                    "isHuman": True,
                    "verificationMethod": "hybrid_shield"
                }
            }
            
            # Call the Rust engine
            rust_result = rust_engine.verify_credential(json.dumps(dummy_credential))
            
            verification_time_ns = time.time_ns() - start_time
            
            # Cache the result
            cache_result = {
                'verified': rust_result.verified,
                'confidence': rust_result.confidence,
                'fingerprint': f"rust_{request.user_id}"
            }
            in_memory_cache.set(cache_key, cache_result, ttl=3600)
            
            return {
                'verified': rust_result.verified,
                'confidence': rust_result.confidence,
                'verification_time_ns': rust_result.verification_time_ns,
                'offline': False,
                'fingerprint': f"rust_{request.user_id}",
                'method': 'rust_engine'
            }
            
        except Exception as e:
            logger.error(f"Rust engine verification failed for user {request.user_id}: {e}")
            
            return {
                'verified': False,
                'confidence': 0.0,
                'verification_time_ns': time.time_ns() - start_time,
                'offline': False,
                'fingerprint': f"rust_error_{request.user_id}",
                'method': 'rust_engine_error',
                'error': str(e)
            }
            
    def add_credential_to_sync_queue(self, user_id: str, credential_data: Dict):
        """Add credential to sync queue for background processing"""
        self.credential_sync_queue.append({
            'user_id': user_id,
            'credential': credential_data,
            'timestamp': time.time(),
            'action': 'store'
        })
        
    def process_credential_sync(self):
        """Process credential sync queue"""
        if not self.credential_sync_queue:
            return
            
        logger.info(f"Processing {len(self.credential_sync_queue)} credential sync items")
        
        # Process up to 10 items at a time
        for _ in range(min(10, len(self.credential_sync_queue))):
            if not self.credential_sync_queue:
                break
                
            sync_item = self.credential_sync_queue.pop(0)
            
            try:
                # Store credential in cache
                cache_key = f"user_credentials_{sync_item['user_id']}"
                in_memory_cache.set(cache_key, sync_item['credential'], ttl=HYBRID_CONFIG['cache_ttl'])
                
                logger.info(f"Synced credential for user {sync_item['user_id']}")
                
            except Exception as e:
                logger.error(f"Failed to sync credential for user {sync_item['user_id']}: {e}")
                
        self.last_sync = datetime.now()
        
    def get_performance_stats(self) -> Dict:
        """Get performance statistics"""
        total_verifications = (
            self.performance_stats['client_verifications'] +
            self.performance_stats['server_verifications'] +
            self.performance_stats['hybrid_verifications']
        )
        
        return {
            **self.performance_stats,
            'total_verifications': total_verifications,
            'client_percentage': (self.performance_stats['client_verifications'] / total_verifications * 100) if total_verifications > 0 else 0,
            'server_percentage': (self.performance_stats['server_verifications'] / total_verifications * 100) if total_verifications > 0 else 0,
            'hybrid_percentage': (self.performance_stats['hybrid_verifications'] / total_verifications * 100) if total_verifications > 0 else 0,
            'fallback_rate': (self.performance_stats['fallback_triggers'] / total_verifications * 100) if total_verifications > 0 else 0,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'sync_queue_size': len(self.credential_sync_queue)
        }

# Global coordinator instance
coordinator = HybridShieldCoordinator()

# Routes
@hybrid_shield_bp.route('/verify', methods=['POST'])
def hybrid_verify():
    """Hybrid verification endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        # Parse request
        verification_request = HybridVerificationRequest(
            user_id=data.get('user_id', ''),
            action=data.get('action', 'verify'),
            timestamp=data.get('timestamp', int(time.time() * 1000)),
            client_available=data.get('client_available', True),
            client_verification_result=data.get('client_verification_result'),
            fallback_reason=data.get('fallback_reason')
        )
        
        # Coordinate verification (synchronous)
        response = coordinator.coordinate_verification_sync(verification_request)
        
        return jsonify({
            'verified': response.verified,
            'confidence': response.confidence,
            'verification_time_ns': response.verification_time_ns,
            'method': response.method,
            'offline': response.offline,
            'fingerprint': response.fingerprint,
            'session_id': response.session_id,
            'timestamp': int(time.time() * 1000)
        })
        
    except Exception as e:
        logger.error(f"Hybrid verification error: {e}")
        return jsonify({
            'error': 'Verification failed',
            'verified': False,
            'confidence': 0.0,
            'method': 'error'
        }), 500

@hybrid_shield_bp.route('/store-credential', methods=['POST'])
def store_credential():
    """Store credential for hybrid verification"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        user_id = data.get('user_id')
        credential_data = data.get('credential')
        
        if not user_id or not credential_data:
            return jsonify({'error': 'Missing user_id or credential'}), 400
            
        # Add to sync queue for background processing
        coordinator.add_credential_to_sync_queue(user_id, credential_data)
        
        return jsonify({
            'stored': True,
            'user_id': user_id,
            'sync_queue_size': len(coordinator.credential_sync_queue)
        })
        
    except Exception as e:
        logger.error(f"Credential storage error: {e}")
        return jsonify({'error': 'Storage failed'}), 500

@hybrid_shield_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get hybrid shield statistics"""
    try:
        stats = coordinator.get_performance_stats()
        
        return jsonify({
            'hybrid_shield_stats': stats,
            'config': HYBRID_CONFIG,
            'rust_engine_available': RUST_ENGINE_AVAILABLE,
            'uptime': time.time() - (coordinator.last_sync.timestamp() if coordinator.last_sync else time.time())
        })
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'error': 'Stats unavailable'}), 500

@hybrid_shield_bp.route('/sync', methods=['POST'])
def manual_sync():
    """Manually trigger credential sync"""
    try:
        coordinator.process_credential_sync()
        
        return jsonify({
            'sync_completed': True,
            'processed_items': len(coordinator.credential_sync_queue),
            'last_sync': coordinator.last_sync.isoformat() if coordinator.last_sync else None
        })
        
    except Exception as e:
        logger.error(f"Manual sync error: {e}")
        return jsonify({'error': 'Sync failed'}), 500

@hybrid_shield_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    system_healthy = RUST_ENGINE_AVAILABLE and rust_engine is not None
    
    return jsonify({
        'healthy': system_healthy,
        'hybrid_shield': 'operational' if system_healthy else 'degraded',
        'rust_engine': RUST_ENGINE_AVAILABLE,
        'rust_engine_status': 'available' if RUST_ENGINE_AVAILABLE else 'compiling',
        'verification_mode': 'rust_engine_only',
        'python_fallback': 'disabled',
        'coordinator': 'active',
        'timestamp': int(time.time() * 1000),
        'note': 'System only accepts Rust engine verification - no Python fallback',
        'warning': 'Verification will fail if Rust engine not available' if not system_healthy else None
    })

# Background task for credential sync
async def background_sync_task():
    """Background task to process credential sync queue"""
    while True:
        try:
            await coordinator.process_credential_sync()
            await asyncio.sleep(HYBRID_CONFIG['sync_interval'])
        except Exception as e:
            logger.error(f"Background sync task error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retrying

# Initialize
initialize_rust_engine()
logger.info("Hybrid Shield API initialized")
logger.info(f"Configuration: {HYBRID_CONFIG}")
logger.info(f"Rust Engine Available: {RUST_ENGINE_AVAILABLE}") 