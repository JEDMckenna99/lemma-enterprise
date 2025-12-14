"""
Server-Sent Events (SSE) Endpoint for Real-Time Revocation Notifications
=========================================================================

Provides real-time revocation events to clients via SSE.
Clients subscribe to this endpoint and receive immediate notifications
when credentials are revoked, enabling instant cache invalidation.

ARCHITECTURE:
- Uses Redis pub/sub for multi-dyno event distribution
- SSE for real-time client notification (no polling needed)
- Site-targeted filtering: clients only receive relevant events

SECURITY:
- No authentication required (events contain no sensitive data)
- Events only contain credential_id, site_id, and timestamp
- Clients filter events based on their site domain
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


def generate_sse_events():
    """
    Generator that yields SSE events from Redis pub/sub
    
    Yields:
        SSE-formatted event strings
    """
    # Create a queue to receive messages from the Redis listener
    event_queue = Queue()
    
    # Send initial connection event
    yield "event: connected\ndata: {}\n\n"
    
    if not REDIS_AVAILABLE:
        # Without Redis, just keep connection alive with heartbeats
        logger.info("SSE: Redis not available, using heartbeat-only mode")
        while True:
            # Send heartbeat every 30 seconds to keep connection alive
            yield ": heartbeat\n\n"
            time.sleep(30)
    
    # Create a separate Redis connection for pub/sub (required by redis-py)
    try:
        if REDIS_URL.startswith('rediss://'):
            pubsub_redis = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
        else:
            pubsub_redis = redis.from_url(REDIS_URL, decode_responses=True)
        
        pubsub = pubsub_redis.pubsub()
        pubsub.subscribe(REVOCATION_CHANNEL)
        
        logger.info(f"SSE: Subscribed to {REVOCATION_CHANNEL}")
        
        # Start background thread to listen for messages
        def listen_for_messages():
            try:
                for message in pubsub.listen():
                    if message['type'] == 'message':
                        event_queue.put(message['data'])
            except Exception as e:
                logger.error(f"SSE listener error: {e}")
                event_queue.put(None)  # Signal termination
        
        listener_thread = threading.Thread(target=listen_for_messages, daemon=True)
        listener_thread.start()
        
        # Main event loop
        heartbeat_interval = 30  # seconds
        last_heartbeat = time.time()
        
        while True:
            try:
                # Try to get a message with timeout
                try:
                    message_data = event_queue.get(timeout=5)
                    
                    if message_data is None:
                        # Listener terminated
                        break
                    
                    # Parse and forward the event
                    try:
                        event = json.loads(message_data)
                        
                        # Format as SSE event
                        sse_data = json.dumps({
                            'credential_id': event.get('credential_id'),
                            'credential_type': event.get('credential_type'),
                            'site_id': event.get('site_id'),  # None = global
                            'timestamp': event.get('timestamp')
                        })
                        
                        yield f"event: revocation\ndata: {sse_data}\n\n"
                        logger.debug(f"SSE: Sent revocation event for {event.get('credential_id')}")
                        
                    except json.JSONDecodeError:
                        logger.warning(f"SSE: Invalid JSON in message: {message_data[:100]}")
                        
                except Empty:
                    # No message received, check if we need to send heartbeat
                    pass
                
                # Send heartbeat if needed
                now = time.time()
                if now - last_heartbeat >= heartbeat_interval:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                    
            except GeneratorExit:
                # Client disconnected
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
        # Fall back to heartbeat-only mode
        while True:
            yield ": heartbeat\n\n"
            time.sleep(30)


@revocation_events_bp.route('/api/events/revocations', methods=['GET', 'OPTIONS'])
@cross_origin()
def revocation_event_stream():
    """
    Server-Sent Events endpoint for real-time revocation notifications
    
    Clients connect to this endpoint and receive events when credentials
    are revoked anywhere in the network. Events include site_id for 
    client-side filtering (Site A ignores events from Site B).
    
    Event format:
        event: revocation
        data: {"credential_id": "...", "site_id": "...", "timestamp": ...}
    
    Connection behavior:
        - Sends "connected" event on initial connection
        - Sends "revocation" events when credentials are revoked
        - Sends heartbeats every 30 seconds to keep connection alive
        - Reconnects automatically on client-side (EventSource behavior)
    
    Returns:
        SSE stream (Content-Type: text/event-stream)
    """
    if request.method == 'OPTIONS':
        # Handle CORS preflight
        response = Response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
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
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
            'Access-Control-Allow-Origin': request.headers.get('Origin', '*'),
            'Access-Control-Allow-Credentials': 'true'
        }
    )
    
    return response


@revocation_events_bp.route('/api/events/revocations/status', methods=['GET'])
@cross_origin()
def revocation_events_status():
    """
    Health check for the revocation events system
    
    Returns:
        JSON with system status
    """
    return {
        'success': True,
        'redis_available': REDIS_AVAILABLE,
        'channel': REVOCATION_CHANNEL,
        'message': 'SSE revocation events endpoint active'
    }, 200

