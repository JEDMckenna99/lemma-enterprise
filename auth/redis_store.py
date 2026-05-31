"""
Redis Store for Lemma Authentication

Provides Redis-backed storage for:
- Passkey challenges (multi-dyno support)
- Session tokens
- Rate limiting state

Uses Redis if available (production), falls back to in-memory (development).
"""

import os
import json
import logging
import ssl
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Redis URL from environment (Heroku sets this automatically)
REDIS_URL = os.environ.get('REDIS_URL') or os.environ.get('REDIS_TLS_URL')

# Bounded connection pool size per worker process. Heroku Redis Mini caps the
# whole app at 20 connections, and this module is one of several Redis consumers
# per gunicorn worker, so keep each pool small to avoid exhausting the cap.
_MAX_CONNECTIONS = int(os.environ.get('LEMMA_AUTH_REDIS_MAX_CONNECTIONS', '6'))


def _build_redis_kwargs() -> dict:
    """
    Connection kwargs hardened for Heroku Redis:
    - keepalive + health checks survive the provider's 300s idle-connection cull
    - retry-with-backoff transparently recovers from transient connection drops
      (e.g. a refused TLS handshake when the connection cap is momentarily hit),
      instead of silently degrading to per-process in-memory storage
    - explicit ssl.CERT_NONE for the self-signed cert on rediss:// endpoints
    """
    from redis.backoff import ExponentialBackoff
    from redis.retry import Retry
    from redis.exceptions import (
        ConnectionError as RedisConnectionError,
        TimeoutError as RedisTimeoutError,
    )

    kwargs = dict(
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
        max_connections=_MAX_CONNECTIONS,
        retry=Retry(ExponentialBackoff(cap=1.0, base=0.1), retries=3),
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
    )
    if REDIS_URL and REDIS_URL.startswith('rediss://'):
        kwargs['ssl_cert_reqs'] = ssl.CERT_NONE
    return kwargs

# Redis client singleton
_redis_client = None
_redis_lock = threading.Lock()

# In-memory fallback storage
_memory_store = {}
_memory_lock = threading.Lock()


def get_redis_client():
    """
    Get or create the Redis client singleton.

    Returns None if Redis is not available (falls back to in-memory).
    """
    global _redis_client

    if not REDIS_URL:
        return None

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client

        try:
            import redis

            _redis_client = redis.from_url(REDIS_URL, **_build_redis_kwargs())

            # Test connection
            _redis_client.ping()
            logger.info("Redis connection established for auth storage")
            return _redis_client

        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory storage: {e}")
            _redis_client = None
            return None


def store(key: str, value: dict, ttl_seconds: int = 300) -> bool:
    """
    Store a value with optional TTL.

    Args:
        key: Storage key (will be prefixed with 'lemma:')
        value: Dictionary to store (serialized to JSON)
        ttl_seconds: Time-to-live in seconds (default 5 minutes)

    Returns:
        True if stored successfully
    """
    full_key = f"lemma:{key}"

    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.setex(full_key, ttl_seconds, json.dumps(value))
            return True
        except Exception as e:
            logger.error(f"Redis store failed: {e}")
            # Fall through to in-memory

    # In-memory fallback
    with _memory_lock:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        _memory_store[full_key] = {
            'value': value,
            'expires_at': expires_at.isoformat()
        }
    return True


def get(key: str) -> Optional[dict]:
    """
    Retrieve a stored value.

    Args:
        key: Storage key (will be prefixed with 'lemma:')

    Returns:
        The stored dictionary, or None if not found/expired
    """
    full_key = f"lemma:{key}"

    redis_client = get_redis_client()
    if redis_client:
        try:
            data = redis_client.get(full_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get failed: {e}")
            # Fall through to in-memory

    # In-memory fallback
    with _memory_lock:
        entry = _memory_store.get(full_key)
        if not entry:
            return None

        # Check expiration
        expires_at = datetime.fromisoformat(entry['expires_at'])
        if datetime.now(timezone.utc) > expires_at:
            del _memory_store[full_key]
            return None

        return entry['value']


def delete(key: str) -> bool:
    """
    Delete a stored value.

    Args:
        key: Storage key (will be prefixed with 'lemma:')

    Returns:
        True if deleted, False if not found
    """
    full_key = f"lemma:{key}"

    redis_client = get_redis_client()
    if redis_client:
        try:
            result = redis_client.delete(full_key)
            return result > 0
        except Exception as e:
            logger.error(f"Redis delete failed: {e}")
            # Fall through to in-memory

    # In-memory fallback
    with _memory_lock:
        if full_key in _memory_store:
            del _memory_store[full_key]
            return True
        return False


def cleanup_expired() -> int:
    """
    Clean up expired entries from in-memory storage.

    Redis handles expiration automatically, so this only affects
    the in-memory fallback store.

    Returns:
        Number of entries removed
    """
    removed = 0
    now = datetime.now(timezone.utc)

    with _memory_lock:
        expired_keys = [
            k for k, v in _memory_store.items()
            if datetime.fromisoformat(v['expires_at']) < now
        ]
        for k in expired_keys:
            del _memory_store[k]
            removed += 1

    if removed > 0:
        logger.debug(f"Cleaned up {removed} expired entries from memory store")

    return removed


def is_redis_available() -> bool:
    """Check if Redis is available and connected."""
    return get_redis_client() is not None
