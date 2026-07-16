"""
Shared Redis client factory for lemma.id.

Heroku Redis Mini caps the *app* at ~20 connections. Historically each module
created its own redis.from_url() pool (often max_connections=4–6). With
WEB_CONCURRENCY>=2 that exhausts the cap and causes silent degrade-to-memory.

Use one shared client per (url, decode_responses) key per process.
Flask-Limiter still opens its own storage pool via URI, keep LEMMA_REDIS_MAX_CONNECTIONS
conservative so the shared pool + limiter fit under the provider cap.
"""

from __future__ import annotations

import logging
import os
import ssl
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_clients: dict[tuple[str, bool], Any] = {}
_lock = threading.Lock()


def resolve_redis_url(*, prefer_cloud: bool = False) -> Optional[str]:
    """Pick Redis URL. prefer_cloud uses REDISCLOUD_URL first (pub/sub / velocity)."""
    if prefer_cloud:
        return (
            os.getenv("REDISCLOUD_URL")
            or os.getenv("REDIS_URL")
            or os.getenv("REDIS_TLS_URL")
        )
    return (
        os.getenv("REDIS_URL")
        or os.getenv("REDIS_TLS_URL")
        or os.getenv("REDISCLOUD_URL")
    )


def _build_kwargs(*, decode_responses: bool) -> dict:
    from redis.backoff import ExponentialBackoff
    from redis.exceptions import (
        ConnectionError as RedisConnectionError,
        TimeoutError as RedisTimeoutError,
    )
    from redis.retry import Retry

    max_connections = int(
        os.getenv("LEMMA_REDIS_MAX_CONNECTIONS")
        or os.getenv("LEMMA_DB_REDIS_MAX_CONNECTIONS")
        or os.getenv("LEMMA_AUTH_REDIS_MAX_CONNECTIONS")
        or "8"
    )
    return dict(
        decode_responses=decode_responses,
        socket_connect_timeout=5,
        socket_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
        max_connections=max_connections,
        retry=Retry(ExponentialBackoff(cap=1.0, base=0.1), retries=3),
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
    )


def get_shared_redis(
    *,
    decode_responses: bool = True,
    prefer_cloud: bool = False,
    url: Optional[str] = None,
    required: bool = False,
    ping: bool = True,
) -> Any:
    """
    Return a process-wide shared Redis client, or None if unavailable.

    Args:
        decode_responses: String responses (default True).
        prefer_cloud: Prefer REDISCLOUD_URL when set.
        url: Explicit URL override.
        required: Raise if URL missing / connect fails.
        ping: Ping on first connect (default True).
    """
    redis_url = (url or resolve_redis_url(prefer_cloud=prefer_cloud) or "").strip()
    if not redis_url:
        if required:
            raise Exception("REDIS_URL not set in environment")
        return None

    key = (redis_url, bool(decode_responses))
    with _lock:
        existing = _clients.get(key)
        if existing is not None:
            return existing

        try:
            import redis

            kwargs = _build_kwargs(decode_responses=decode_responses)
            if redis_url.startswith("rediss://"):
                kwargs["ssl_cert_reqs"] = ssl.CERT_NONE

            client = redis.from_url(redis_url, **kwargs)
            if ping:
                client.ping()
            _clients[key] = client
            logger.info(
                "Shared Redis connected (decode_responses=%s, max_connections=%s)",
                decode_responses,
                kwargs["max_connections"],
            )
            return client
        except Exception as exc:
            logger.warning("Shared Redis connection failed: %s", exc)
            if required:
                raise
            return None


def reset_shared_redis_for_tests() -> None:
    """Drop cached clients (unit tests only)."""
    with _lock:
        _clients.clear()
