from __future__ import annotations

import os
from datetime import datetime, timezone


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def freshness_max_age_seconds(risk_tier: str) -> int:
    tier = str(risk_tier or "low").strip().lower()
    if tier == "critical":
        return max(1, _int_env("LEMMA_FRESHNESS_MAX_AGE_CRITICAL_SECONDS", 10))
    if tier == "high":
        return max(1, _int_env("LEMMA_FRESHNESS_MAX_AGE_HIGH_SECONDS", 30))
    return max(1, _int_env("LEMMA_FRESHNESS_MAX_AGE_LOW_SECONDS", 120))


def freshness_age_seconds(last_sync_epoch_seconds: float | None) -> float | None:
    if last_sync_epoch_seconds is None:
        return None
    now = datetime.now(timezone.utc).timestamp()
    return max(0.0, float(now - float(last_sync_epoch_seconds)))


def is_fresh_enough(risk_tier: str, last_sync_epoch_seconds: float | None) -> tuple[bool, float | None, int]:
    age = freshness_age_seconds(last_sync_epoch_seconds)
    max_age = freshness_max_age_seconds(risk_tier)
    if age is None:
        return False, None, max_age
    return age <= max_age, age, max_age

