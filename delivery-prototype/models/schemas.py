"""Data models and validation schemas."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from config import DELAY_BUCKET_SECONDS, SENSITIVE_FIELD_PATTERNS


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_log_id() -> str:
    return f"LOG-{uuid.uuid4().hex[:8].upper()}"


def new_event_id() -> str:
    return f"EVT-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class MetricsLog:
    log_id: str
    timestamp: str
    route_type: str
    stop_type: str
    signal_quality: str
    delayed_action: str
    delay_bucket: str
    retry_needed: bool
    sensitive_data_collected: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricsLog":
        validate_metrics_payload(data)
        return cls(
            log_id=str(data.get("log_id") or new_log_id()),
            timestamp=str(data.get("timestamp") or _now_iso()),
            route_type=str(data["route_type"]),
            stop_type=str(data["stop_type"]),
            signal_quality=str(data["signal_quality"]),
            delayed_action=str(data["delayed_action"]),
            delay_bucket=str(data["delay_bucket"]),
            retry_needed=bool(data.get("retry_needed", False)),
            sensitive_data_collected=False,
            note=str(data.get("note") or "")[:200],
        )


def validate_metrics_payload(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("metrics payload must be object")
    for key in data:
        lower = key.lower()
        for pattern in SENSITIVE_FIELD_PATTERNS:
            if pattern in lower:
                raise ValueError(f"sensitive field not allowed: {key}")
    if data.get("sensitive_data_collected") is True:
        raise ValueError("sensitive_data_collected must be false")
    bucket = str(data.get("delay_bucket", ""))
    if bucket not in DELAY_BUCKET_SECONDS:
        raise ValueError(f"invalid delay_bucket: {bucket}")


def bucket_to_seconds(bucket: str) -> int:
    return DELAY_BUCKET_SECONDS.get(bucket, 0)


def aggregate_metrics(logs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(logs)
    by_action: dict[str, int] = {}
    by_stop: dict[str, int] = {}
    by_signal: dict[str, int] = {}
    retries = 0
    time_lost = 0
    worst = "0-2_sec"
    worst_val = 0
    for row in logs:
        action = row.get("delayed_action", "other")
        stop = row.get("stop_type", "other")
        signal = row.get("signal_quality", "unknown")
        bucket = row.get("delay_bucket", "0-2_sec")
        by_action[action] = by_action.get(action, 0) + 1
        by_stop[stop] = by_stop.get(stop, 0) + 1
        by_signal[signal] = by_signal.get(signal, 0) + 1
        if row.get("retry_needed"):
            retries += 1
        secs = bucket_to_seconds(bucket)
        time_lost += secs
        if secs > worst_val:
            worst_val = secs
            worst = bucket
    weak_share = 0.0
    if total:
        weak = sum(
            1 for row in logs
            if row.get("signal_quality") in ("weak", "no_service")
        )
        weak_share = round(100 * weak / total, 1)
    return {
        "total_delay_events": total,
        "delay_events_by_action": by_action,
        "delay_events_by_stop_type": by_stop,
        "delay_events_by_signal": by_signal,
        "estimated_time_lost_seconds": time_lost,
        "estimated_time_lost_minutes": round(time_lost / 60, 1),
        "retry_count": retries,
        "worst_delay_category": worst,
        "weak_no_service_share_percent": weak_share,
        "most_common_delayed_action": max(by_action, key=by_action.get) if by_action else None,
        "most_common_stop_type": max(by_stop, key=by_stop.get) if by_stop else None,
    }


@dataclass
class ShiftSummary:
    date: str
    total_stops: int
    total_packages: int
    shift_length_hours: float
    battery_start: int
    battery_end: int
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
