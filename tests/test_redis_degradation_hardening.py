import os
import time

os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from auth import session_manager
from api import rate_limiter as api_rate_limiter


def test_session_revocation_check_fail_open_by_default(monkeypatch):
    monkeypatch.delenv("LEMMA_SESSION_REVOCATION_DEGRADED_MODE", raising=False)
    monkeypatch.setattr("auth.redis_store.get", lambda _key: (_ for _ in ()).throw(RuntimeError("redis down")))

    token = "wallet123:0:1234567890:nonce:sig"
    assert session_manager._is_session_revoked(token, "wallet123", 1234567890) is False


def test_session_revocation_check_fail_closed_mode(monkeypatch):
    monkeypatch.setenv("LEMMA_SESSION_REVOCATION_DEGRADED_MODE", "fail_closed")
    monkeypatch.setattr("auth.redis_store.get", lambda _key: (_ for _ in ()).throw(RuntimeError("redis down")))

    token = "wallet123:0:1234567890:nonce:sig"
    assert session_manager._is_session_revoked(token, "wallet123", 1234567890) is True


def test_api_rate_limiter_memory_fallback_check_rate_limit(monkeypatch):
    monkeypatch.setenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE", "memory")
    monkeypatch.setattr(api_rate_limiter, "REDIS_AVAILABLE", False)
    api_rate_limiter._memory_counters.clear()

    key = f"test:{int(time.time())}"
    assert api_rate_limiter.check_rate_limit(key, max_requests=2, window_seconds=60) is True
    assert api_rate_limiter.check_rate_limit(key, max_requests=2, window_seconds=60) is True
    assert api_rate_limiter.check_rate_limit(key, max_requests=2, window_seconds=60) is False


def test_api_rate_limiter_fail_open_check_rate_limit(monkeypatch):
    monkeypatch.setenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE", "fail_open")
    monkeypatch.setattr(api_rate_limiter, "REDIS_AVAILABLE", False)

    key = f"test-open:{int(time.time())}"
    assert api_rate_limiter.check_rate_limit(key, max_requests=1, window_seconds=60) is True
    assert api_rate_limiter.check_rate_limit(key, max_requests=1, window_seconds=60) is True
