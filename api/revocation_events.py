"""
Server-Sent Events (SSE) Endpoint for Real-Time Platform Events
================================================================

Provides real-time events to clients via SSE, covering:
1. Credential revocations — instant cache invalidation
2. Session invalidation — instant cross-device lock/unlock detection

ARCHITECTURE:
- Uses Redis pub/sub for multi-dyno event distribution
- SSE for real-time client notification (no polling needed)
- Site-targeted filtering: clients only receive relevant events
- Two Redis channels: lemma:revocations + lemma:sessions

EVENT TYPES:
- "revocation"           — credential revoked (credential_id, site_id, timestamp)
- "session_invalidated"  — wallet locked on another device (wallet_id, timestamp)
- "session_restored"     — wallet unlocked on another device (wallet_id, expires_at, timestamp)

SECURITY:
- No authentication required (events contain no sensitive data)
- Revocation events only contain credential_id, site_id, and timestamp
- Session events only contain wallet_id and timestamps (no secrets)
- Clients filter events based on their wallet_id / site domain
"""

import os
import json
import logging
import time
import threading
from queue import Queue, Empty
from flask import Blueprint, Response, request, stream_with_context
from flask_cors import cross_origin

logger = logging.getLogger(__name__)

revocation_events_bp = Blueprint('revocation_events', __name__)

# Redis connection for pub/sub
try:
    import redis
    REDIS_URL = os.getenv('REDISCLOUD_URL') or os.getenv('REDIS_URL')
    if REDIS_URL:
        if REDIS_URL.startswith('rediss://'):
            redis_client = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
        else:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        REDIS_AVAILABLE = True
        logger.info("SSE revocation events: Redis available")
    else:
        REDIS_AVAILABLE = False
        redis_client = None
        logger.warning("SSE revocation events: Redis not available (REDIS_URL not set)")
except Exception as e:
    REDIS_AVAILABLE = False
    redis_client = None
    logger.warning(f"SSE revocation events: Redis connection failed: {e}")

REVOCATION_CHANNEL = 'lemma:revocations'
SESSION_CHANNEL = 'lemma:sessions'
# Keepalive interval must stay comfortably below Gunicorn worker timeout
# to avoid sync worker restarts on long-lived SSE streams.
SSE_HEARTBEAT_SECONDS = 10
# Gunicorn sync workers will be aborted near the global timeout (commonly 30s).
# Rotate SSE streams proactively so clients reconnect before worker timeout.
SSE_MAX_STREAM_SECONDS = 20


def publish_session_event(wallet_id: str, event_type: str, expires_at: int = None) -> bool:
    """
    Publish a session event to the SSE channel via Redis pub/sub.
    
    Called when a wallet is locked or unlocked to notify all connected clients
    instantly, replacing the need for 60-second polling heartbeats.
    
    Args:
        wallet_id: The wallet identifier (used for client-side filtering)
        event_type: 'session_invalidated' or 'session_restored'
        expires_at: Session expiry timestamp (only for session_restored)
        
    Returns:
        True if published successfully
    """
    if not REDIS_AVAILABLE:
        logger.warning("SSE: Redis not available - session event not published")
        return False
    
    try:
        event_data = {
            'event_type': event_type,
            'wallet_id': wallet_id,
            'timestamp': time.time(),
        }
        if expires_at is not None:
            event_data['expires_at'] = expires_at
        
        subscribers = redis_client.publish(
            SESSION_CHANNEL,
            json.dumps(event_data)
        )
        
        logger.info(f"SSE: Published {event_type} for wallet {wallet_id[:8]}... to {subscribers} subscribers")
        return True
        
    except Exception as e:
        logger.error(f"SSE: Failed to publish session event: {e}")
        return False


def _format_revocation_sse(event: dict) -> str:
    """Format a revocation event as an SSE string."""
    sse_data = json.dumps({
        'credential_id': event.get('credential_id'),
        'credential_type': event.get('credential_type'),
        'site_id': event.get('site_id'),
        'timestamp': event.get('timestamp')
    })
    return f"event: revocation\ndata: {sse_data}\n\n"


def _format_session_sse(event: dict) -> str:
    """Format a session event as an SSE string."""
    event_type = event.get('event_type', 'session_invalidated')
    sse_data = json.dumps({
        'wallet_id': event.get('wallet_id'),
        'timestamp': event.get('timestamp'),
        'expires_at': event.get('expires_at'),
    })
    return f"event: {event_type}\ndata: {sse_data}\n\n"


def generate_sse_events():
    """
    Generator that yields SSE events from Redis pub/sub.
    
    Subscribes to two channels:
    - lemma:revocations — credential revocation events
    - lemma:sessions    — session lock/unlock events
    
    Yields:
        SSE-formatted event strings
    """
    event_queue = Queue()
    stream_started_at = time.time()
    
    # Send initial connection event with supported event types
    yield "event: connected\ndata: {\"types\": [\"revocation\", \"session_invalidated\", \"session_restored\"]}\n\n"
    
    if not REDIS_AVAILABLE:
        logger.info("SSE: Redis not available, using heartbeat-only mode")
        while True:
            if time.time() - stream_started_at >= SSE_MAX_STREAM_SECONDS:
                yield "event: reconnect\ndata: {\"reason\":\"stream_rotate\"}\n\n"
                break
            yield ": heartbeat\n\n"
            time.sleep(SSE_HEARTBEAT_SECONDS)
    
    # Create a separate Redis connection for pub/sub (required by redis-py)
    try:
        if REDIS_URL.startswith('rediss://'):
            pubsub_redis = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
        else:
            pubsub_redis = redis.from_url(REDIS_URL, decode_responses=True)
        
        pubsub = pubsub_redis.pubsub()
        pubsub.subscribe(REVOCATION_CHANNEL, SESSION_CHANNEL)
        
        logger.info(f"SSE: Subscribed to {REVOCATION_CHANNEL} and {SESSION_CHANNEL}")
        
        # Start background thread to listen for messages
        def listen_for_messages():
            try:
                for message in pubsub.listen():
                    if message['type'] == 'message':
                        # Tag with source channel so the main loop can dispatch
                        event_queue.put((message['channel'], message['data']))
            except Exception as e:
                logger.error(f"SSE listener error: {e}")
                event_queue.put(None)  # Signal termination
        
        listener_thread = threading.Thread(target=listen_for_messages, daemon=True)
        listener_thread.start()
        
        # Main event loop
        heartbeat_interval = SSE_HEARTBEAT_SECONDS
        last_heartbeat = time.time()
        
        while True:
            try:
                if time.time() - stream_started_at >= SSE_MAX_STREAM_SECONDS:
                    # Ask client to reconnect before worker timeout is reached.
                    yield "event: reconnect\ndata: {\"reason\":\"stream_rotate\"}\n\n"
                    break

                try:
                    # Short timeout keeps loop responsive and guarantees
                    # regular heartbeats under low event volume.
                    item = event_queue.get(timeout=1)
                    
                    if item is None:
                        break
                    
                    channel, message_data = item
                    
                    try:
                        event = json.loads(message_data)
                        
                        # Dispatch based on source channel
                        if channel == REVOCATION_CHANNEL:
                            yield _format_revocation_sse(event)
                            logger.debug(f"SSE: Sent revocation event for {event.get('credential_id')}")
                        elif channel == SESSION_CHANNEL:
                            yield _format_session_sse(event)
                            logger.debug(f"SSE: Sent {event.get('event_type')} for wallet {event.get('wallet_id', '')[:8]}...")
                        else:
                            logger.warning(f"SSE: Unknown channel: {channel}")
                        
                    except json.JSONDecodeError:
                        logger.warning(f"SSE: Invalid JSON in message: {message_data[:100]}")
                        
                except Empty:
                    pass
                
                # Send heartbeat if needed
                now = time.time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                    
            except GeneratorExit:
                logger.info("SSE: Client disconnected")
                break
            except Exception as e:
                logger.error(f"SSE event loop error: {e}")
                break
        
        # Cleanup
        pubsub.unsubscribe()
        pubsub.close()
        
    except Exception as e:
        logger.error(f"SSE: Failed to setup Redis pub/sub: {e}")
        while True:
            if time.time() - stream_started_at >= SSE_MAX_STREAM_SECONDS:
                yield "event: reconnect\ndata: {\"reason\":\"stream_rotate\"}\n\n"
                break
            yield ": heartbeat\n\n"
            time.sleep(SSE_HEARTBEAT_SECONDS)


@revocation_events_bp.route('/api/events/revocations', methods=['GET', 'OPTIONS'])
def revocation_event_stream():
    """
    Server-Sent Events endpoint for real-time platform events.
    
    Streams two categories of events:
    
    1. Revocation events (credential invalidation):
        event: revocation
        data: {"credential_id": "...", "site_id": "...", "timestamp": ...}
    
    2. Session events (cross-device lock/unlock detection):
        event: session_invalidated
        data: {"wallet_id": "...", "timestamp": ...}
        
        event: session_restored
        data: {"wallet_id": "...", "expires_at": ..., "timestamp": ...}
    
    Connection behavior:
        - Sends "connected" event on initial connection (lists supported types)
        - Sends heartbeats every 30 seconds to keep connection alive
        - Reconnects automatically on client-side (EventSource behavior)
    
    Returns:
        SSE stream (Content-Type: text/event-stream)
    """
    origin = request.headers.get('Origin', '*')
    
    if request.method == 'OPTIONS':
        response = Response()
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Cache-Control'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    logger.info(f"SSE: New client connected from {request.remote_addr}")
    
    response = Response(
        stream_with_context(generate_sse_events()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true'
        }
    )
    
    return response


@revocation_events_bp.route('/api/events/revocations/status', methods=['GET'])
@cross_origin()
def revocation_events_status():
    """
    Health check for the SSE event system.
    
    Returns:
        JSON with system status including both channels
    """
    return {
        'success': True,
        'redis_available': REDIS_AVAILABLE,
        'channels': {
            'revocations': REVOCATION_CHANNEL,
            'sessions': SESSION_CHANNEL,
        },
        'event_types': ['revocation', 'session_invalidated', 'session_restored'],
        'message': 'SSE event stream endpoint active'
    }, 200

