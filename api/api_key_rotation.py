"""Shared API key rotation grace window helpers."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


def rotation_grace_hours() -> int:
    raw = os.getenv("LEMMA_API_KEY_ROTATION_GRACE_HOURS", "24")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 24
    return max(1, min(value, 168))


def grace_expires_at(now: datetime | None = None) -> datetime:
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(hours=rotation_grace_hours())


def _parse_grace(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def api_key_status_is_valid(status: str | None, grace_expires_at_value: str | None = None) -> bool:
    normalized = (status or "active").strip().lower()
    if normalized == "active":
        return True
    if normalized == "rotation_pending":
        expires = _parse_grace(grace_expires_at_value)
        if expires is None:
            return True
        return expires > datetime.now(timezone.utc)
    return False


def is_legacy_plaintext_site_api_key(value: str | None) -> bool:
    candidate = (value or "").strip()
    if not candidate or candidate.startswith("__hash_only__"):
        return False
    return candidate.startswith("lm_") or candidate.startswith("lemma_")
