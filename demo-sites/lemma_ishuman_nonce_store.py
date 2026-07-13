"""Distributed nonce stores for action-stamp replay protection."""

from __future__ import annotations

import threading
import time
from typing import Optional, Protocol


class NonceStore(Protocol):
    def consume(self, nonce: str, *, site_id: str = "", ttl_seconds: int = 300) -> bool:
        ...


class InMemoryNonceStore:
    """Process-local nonce store for tests and single-process development."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: set[str] = set()

    def consume(self, nonce: str, *, site_id: str = "", ttl_seconds: int = 300) -> bool:
        del site_id, ttl_seconds
        text = str(nonce or "").strip()
        if not text:
            return False
        with self._lock:
            if text in self._seen:
                return False
            self._seen.add(text)
            return True


class RedisNonceStore:
    """Redis-backed nonce store with atomic SET NX semantics."""

    def __init__(self, redis_client=None, *, key_prefix: str = "lemma:action-nonce") -> None:
        self._redis = redis_client
        self._key_prefix = str(key_prefix or "lemma:action-nonce").strip(":")

    def _client(self):
        if self._redis is not None:
            return self._redis
        try:
            from auth.redis_store import get_redis_client
        except ImportError:
            return None
        return get_redis_client()

    def consume(self, nonce: str, *, site_id: str = "", ttl_seconds: int = 300) -> bool:
        text = str(nonce or "").strip()
        if not text:
            return False
        client = self._client()
        if client is None:
            return False
        site = str(site_id or "global").strip() or "global"
        key = f"{self._key_prefix}:{site}:{text}"
        ttl = max(1, int(ttl_seconds or 300))
        try:
            return bool(client.set(key, "1", nx=True, ex=ttl))
        except Exception:
            return False


class StrictNonceStoreAdapter:
    """Wrap a nonce store and fail closed when backend errors in strict mode."""

    def __init__(self, inner, *, strict: bool = True) -> None:
        self._inner = inner
        self._strict = bool(strict)

    def consume(self, nonce: str, *, site_id: str = "", ttl_seconds: int = 300) -> bool:
        if self._inner is None:
            return not self._strict
        consume = getattr(self._inner, "consume", None)
        if not callable(consume):
            return not self._strict
        try:
            return bool(consume(nonce, site_id=site_id, ttl_seconds=ttl_seconds))
        except Exception:
            return not self._strict
