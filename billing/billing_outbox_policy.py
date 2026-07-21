"""Outbox retry policy helpers for Section 8 billing integrity."""

from __future__ import annotations

import os
from datetime import datetime, timedelta


def billing_outbox_max_attempts() -> int:
    raw = os.getenv("LEMMA_BILLING_OUTBOX_MAX_ATTEMPTS", "8").strip()
    try:
        return max(1, min(int(raw), 50))
    except ValueError:
        return 8


def billing_outbox_queue_age_alert_seconds() -> int:
    raw = os.getenv("LEMMA_BILLING_OUTBOX_QUEUE_AGE_ALERT_SECONDS", "3600").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


def compute_next_attempt_at(*, attempts: int, now: datetime | None = None) -> datetime:
    """Exponential backoff capped at one hour."""
    current = now or datetime.utcnow()
    delay_seconds = min(3600, max(60, 2 ** max(0, attempts - 1) * 60))
    return current + timedelta(seconds=delay_seconds)


def outbox_ready_for_retry(row, *, now: datetime | None = None) -> bool:
    current = now or datetime.utcnow()
    next_at = getattr(row, "next_attempt_at", None)
    if next_at is None:
        return True
    return next_at <= current
