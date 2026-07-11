"""Tiny process-local circuit breaker for outbound HTTP dependencies."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Fail-fast after consecutive failures; half-open after recovery_seconds."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_seconds = max(1.0, float(recovery_seconds))
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if (time.time() - self._opened_at) >= self.recovery_seconds:
                # Half-open: allow one probe.
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                if self._opened_at is None:
                    logger.warning(
                        "Circuit open for %s after %s failures (recovery=%.0fs)",
                        self.name,
                        self._failures,
                        self.recovery_seconds,
                    )
                self._opened_at = time.time()

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
