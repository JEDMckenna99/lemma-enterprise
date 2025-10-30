"""
Event-Driven Revocation Sync System
====================================
Triggers immediate bloom filter sync across all dynos when credentials are revoked.
Uses Redis pub/sub for multi-dyno communication.

FIXES: VULN-001 (Bloom filter sync delay)
"""

import os
import json
import redis
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize Redis client
try:
    REDIS_URL = os.getenv('REDISCLOUD_URL') or os.getenv('REDIS_URL')
    if REDIS_URL:
        # Handle SSL Redis with cert issues
        if REDIS_URL.startswith('rediss://'):
            redis_client = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
        else:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        
        # Test connection
        redis_client.ping()
        REDIS_AVAILABLE = True
        logger.info("✅ Event-driven revocation sync initialized with Redis pub/sub")
    else:
        REDIS_AVAILABLE = False
        logger.warning("⚠️ Redis not available - revocation sync will use local-only mode")
except Exception as e:
    REDIS_AVAILABLE = False
    logger.warning(f"⚠️ Redis connection failed for revocation sync: {e}")


class RevocationEventBus:
    """
    Multi-dyno revocation event bus using Redis pub/sub
    Triggers immediate bloom filter sync across all nodes
    """
    
    REVOCATION_CHANNEL = 'lemma:revocations'
    
    def __init__(self):
        self.subscribed = False
        self.pubsub = None
        self.listener_thread = None
        
        if REDIS_AVAILABLE:
            try:
                # Create pub/sub connection
                self.pubsub = redis_client.pubsub()
                self.pubsub.subscribe(self.REVOCATION_CHANNEL)
                
                # Start listener thread
                self.listener_thread = threading.Thread(
                    target=self._listen_for_revocations,
                    daemon=True,
                    name='RevocationListener'
                )
                self.listener_thread.start()
                self.subscribed = True
                
                logger.info(f"✅ Subscribed to revocation events on channel: {self.REVOCATION_CHANNEL}")
            except Exception as e:
                logger.error(f"❌ Failed to start revocation listener: {e}")
                self.subscribed = False
    
    def _listen_for_revocations(self):
        """
        Background thread that listens for revocation events
        and triggers immediate bloom filter sync
        """
        logger.info("🎧 Revocation listener thread started")
        
        try:
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    try:
                        # Parse revocation event
                        event_data = json.loads(message['data'])
                        credential_id = event_data.get('credential_id')
                        credential_type = event_data.get('credential_type')
                        timestamp = event_data.get('timestamp')
                        
                        logger.info(f"📢 Revocation event received: {credential_id} (type: {credential_type})")
                        logger.info(f"   Timestamp: {timestamp}")
                        logger.info(f"   Channel: {self.REVOCATION_CHANNEL}")
                        
                        # Trigger IMMEDIATE bloom filter sync on this dyno
                        self._sync_bloom_filter_immediately(credential_id)
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing revocation event: {e}")
        except Exception as e:
            logger.error(f"❌ Revocation listener crashed: {e}")
            self.subscribed = False
    
    def _sync_bloom_filter_immediately(self, credential_id: str):
        """
        Immediately add revoked credential to bloom filter
        Called when revocation event is received
        """
        try:
            from api.permission_verification import sync_single_revocation
            
            start_time = time.perf_counter()
            success = sync_single_revocation(credential_id)
            sync_time_ms = (time.perf_counter() - start_time) * 1000
            
            if success:
                logger.info(f"✅ Bloom filter updated for {credential_id} in {sync_time_ms:.2f}ms")
            else:
                logger.warning(f"⚠️ Bloom filter sync failed for {credential_id}")
                
        except Exception as e:
            logger.error(f"❌ Bloom filter sync error for {credential_id}: {e}")
    
    def publish_revocation(self, credential_id: str, credential_type: str = 'unknown') -> bool:
        """
        Publish revocation event to all dynos
        This triggers IMMEDIATE bloom filter sync across the cluster
        
        Args:
            credential_id: ID of revoked credential
            credential_type: Type ('poh', 'permission', etc.)
            
        Returns:
            True if published successfully
        """
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis not available - revocation event not published")
            # Still sync locally
            self._sync_bloom_filter_immediately(credential_id)
            return False
        
        try:
            event_data = {
                'credential_id': credential_id,
                'credential_type': credential_type,
                'timestamp': time.time(),
                'source': 'revocation_api'
            }
            
            # Publish to all subscribers (including this dyno)
            subscribers = redis_client.publish(
                self.REVOCATION_CHANNEL,
                json.dumps(event_data)
            )
            
            logger.info(f"📤 Revocation event published to {subscribers} dynos")
            logger.info(f"   Credential: {credential_id}")
            logger.info(f"   Type: {credential_type}")
            logger.info(f"   Channel: {self.REVOCATION_CHANNEL}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to publish revocation event: {e}")
            # Fallback to local sync
            self._sync_bloom_filter_immediately(credential_id)
            return False


# Global event bus (singleton)
_event_bus: Optional[RevocationEventBus] = None


def get_event_bus() -> RevocationEventBus:
    """Get or create global revocation event bus"""
    global _event_bus
    if _event_bus is None:
        _event_bus = RevocationEventBus()
    return _event_bus


def trigger_revocation_sync(credential_id: str, credential_type: str = 'unknown') -> bool:
    """
    Trigger IMMEDIATE revocation sync across all dynos
    
    This is the main entry point for revoking credentials.
    It will:
    1. Publish event to Redis pub/sub
    2. All dynos (including this one) receive the event
    3. Each dyno immediately updates its bloom filter
    4. Total propagation time: <100ms (vs 60 seconds before)
    
    Args:
        credential_id: ID of credential to revoke
        credential_type: Type of credential ('poh', 'permission', etc.)
        
    Returns:
        True if event published successfully
    """
    event_bus = get_event_bus()
    return event_bus.publish_revocation(credential_id, credential_type)


def is_listening() -> bool:
    """Check if this dyno is listening for revocation events"""
    event_bus = get_event_bus()
    return event_bus.subscribed

