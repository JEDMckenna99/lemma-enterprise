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
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Redis URL from environment (Heroku sets this automatically)
REDIS_URL = os.environ.get('REDIS_URL') or os.environ.get('REDIS_TLS_URL')

# In-memory fallback storage
_memory_store = {}
_memory_lock = threading.Lock()


def get_redis_client():
    """
    Get the shared Redis client.

    Returns None if Redis is not available (falls back to in-memory).
    """
    if not REDIS_URL:
        return None

    try:
        from api.redis_client import get_shared_redis

        return get_shared_redis()
    except Exception as e:
        logger.warning(f"Redis connection failed, using in-memory storage: {e}")
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


def store_nx(key: str, value: dict, ttl_seconds: int = 300) -> bool:
    """Store a value only if the key does not already exist.

    Returns True when this caller created the key, False when it already
    existed or the write failed closed.
    """
    full_key = f"lemma:{key}"
    payload = json.dumps(value)

    redis_client = get_redis_client()
    if redis_client:
        try:
            created = redis_client.set(full_key, payload, nx=True, ex=ttl_seconds)
            return bool(created)
        except Exception as e:
            logger.error(f"Redis store_nx failed: {e}")
            return False

    with _memory_lock:
        entry = _memory_store.get(full_key)
        if entry:
            expires_at = datetime.fromisoformat(entry["expires_at"])
            if datetime.now(timezone.utc) <= expires_at:
                return False
            del _memory_store[full_key]
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        _memory_store[full_key] = {
            "value": value,
            "expires_at": expires_at.isoformat(),
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


def consume(key: str) -> Optional[dict]:
    """Atomically retrieve and delete one-time state.

    Redis ``GETDEL`` provides the production atomicity guarantee. The
    in-memory fallback performs the same operation under the module lock for
    development and tests. Redis errors fail closed rather than falling
    through to a different store that may contain stale state.
    """
    full_key = f"lemma:{key}"

    redis_client = get_redis_client()
    if redis_client:
        try:
            data = redis_client.getdel(full_key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis consume failed: {e}")
            return None

    with _memory_lock:
        entry = _memory_store.pop(full_key, None)
        if not entry:
            return None
        expires_at = datetime.fromisoformat(entry['expires_at'])
        if datetime.now(timezone.utc) > expires_at:
            return None
        return entry['value']


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
