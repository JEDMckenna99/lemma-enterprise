"""
Lightweight runtime telemetry for admin health views.

Tracks request timestamps in-memory per process so the health endpoint can
report recent request volume without requiring external infrastructure.
"""

from collections import deque
from threading import Lock
import time

_REQUEST_TIMESTAMPS = deque()
_RESPONSE_STATUSES = deque()
_RESPONSE_LATENCIES_MS = deque()
_LOCK = Lock()
_WINDOW_SECONDS = 60.0
_ERROR_WINDOW_SECONDS = 300.0


def record_request(now: float | None = None) -> None:
    """Record a request timestamp and prune stale entries."""
    timestamp = now if now is not None else time.time()
    cutoff = timestamp - _WINDOW_SECONDS
    with _LOCK:
        _REQUEST_TIMESTAMPS.append(timestamp)
        while _REQUEST_TIMESTAMPS and _REQUEST_TIMESTAMPS[0] < cutoff:
            _REQUEST_TIMESTAMPS.popleft()


def record_response(status_code: int, now: float | None = None, duration_ms: float | None = None) -> None:
    """Record response status code and prune stale entries."""
    timestamp = now if now is not None else time.time()
    cutoff = timestamp - _ERROR_WINDOW_SECONDS
    with _LOCK:
        _RESPONSE_STATUSES.append((timestamp, int(status_code)))
        if isinstance(duration_ms, (int, float)):
            _RESPONSE_LATENCIES_MS.append((timestamp, float(duration_ms)))
        while _RESPONSE_STATUSES and _RESPONSE_STATUSES[0][0] < cutoff:
            _RESPONSE_STATUSES.popleft()
        while _RESPONSE_LATENCIES_MS and _RESPONSE_LATENCIES_MS[0][0] < cutoff:
            _RESPONSE_LATENCIES_MS.popleft()


def requests_last_minute(now: float | None = None) -> int:
    """Return count of requests seen in the last 60 seconds."""
    timestamp = now if now is not None else time.time()
    cutoff = timestamp - _WINDOW_SECONDS
    with _LOCK:
        while _REQUEST_TIMESTAMPS and _REQUEST_TIMESTAMPS[0] < cutoff:
            _REQUEST_TIMESTAMPS.popleft()
        return len(_REQUEST_TIMESTAMPS)


def status_summary_last_5m(now: float | None = None) -> dict:
    """Return auth and error counters over the last 5 minutes."""
    timestamp = now if now is not None else time.time()
    cutoff = timestamp - _ERROR_WINDOW_SECONDS
    with _LOCK:
        while _RESPONSE_STATUSES and _RESPONSE_STATUSES[0][0] < cutoff:
            _RESPONSE_STATUSES.popleft()
        while _RESPONSE_LATENCIES_MS and _RESPONSE_LATENCIES_MS[0][0] < cutoff:
            _RESPONSE_LATENCIES_MS.popleft()
        codes = [status for _, status in _RESPONSE_STATUSES]

    return {
        'responses_5m': len(codes),
        'auth_401_5m': sum(1 for c in codes if c == 401),
        'forbidden_403_5m': sum(1 for c in codes if c == 403),
        'server_5xx_5m': sum(1 for c in codes if c >= 500),
    }


def slo_snapshot_last_5m(now: float | None = None) -> dict:
    """Return 5-minute SLO-style signals derived from runtime telemetry."""
    timestamp = now if now is not None else time.time()
    cutoff = timestamp - _ERROR_WINDOW_SECONDS
    with _LOCK:
        while _RESPONSE_STATUSES and _RESPONSE_STATUSES[0][0] < cutoff:
            _RESPONSE_STATUSES.popleft()
        while _RESPONSE_LATENCIES_MS and _RESPONSE_LATENCIES_MS[0][0] < cutoff:
            _RESPONSE_LATENCIES_MS.popleft()
        codes = [status for _, status in _RESPONSE_STATUSES]
        latencies = [lat for _, lat in _RESPONSE_LATENCIES_MS]

    total = len(codes)
    server_errors = sum(1 for c in codes if c >= 500)
    error_rate = round((server_errors / total) * 100.0, 2) if total > 0 else 0.0

    p95_latency = None
    if latencies:
        ordered = sorted(latencies)
        index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
        p95_latency = round(ordered[index], 2)

    return {
        'responses_5m': total,
        'server_5xx_5m': server_errors,
        'error_rate_5m_percent': error_rate,
        'p95_latency_ms_5m': p95_latency,
    }
