"""Section 9 operational readiness: liveness and dependency-aware readiness."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def liveness_payload() -> dict[str, Any]:
    """Process liveness only — no dependency probes."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _check_database() -> tuple[bool, dict[str, Any]]:
    try:
        from api.database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, {"ok": True}
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", exc)
        return False, {"ok": False, "error": str(exc)}


def _check_redis() -> tuple[bool, dict[str, Any]]:
    try:
        from api.redis_client import get_shared_redis, resolve_redis_url

        url = resolve_redis_url()
        if not url:
            return False, {"ok": False, "error": "redis_url_not_configured"}
        client = get_shared_redis(ping=True)
        if client is None:
            return False, {"ok": False, "error": "redis_unavailable"}
        client.ping()
        return True, {"ok": True}
    except Exception as exc:
        logger.warning("Redis readiness check failed: %s", exc)
        return False, {"ok": False, "error": str(exc)}


def _check_crypto() -> tuple[bool, dict[str, Any]]:
    try:
        from lemma_crypto import PyMinimalVerifier

        PyMinimalVerifier()
        return True, {"ok": True}
    except Exception as exc:
        logger.warning("Crypto readiness check failed: %s", exc)
        return False, {"ok": False, "error": str(exc)}


def _check_revocation() -> tuple[bool, dict[str, Any]]:
    try:
        from api.revocation_verifier import revocation_freshness_status

        ready, detail = revocation_freshness_status()
        if not ready:
            age = detail.get("age_seconds")
            max_age = detail.get("max_age_seconds")
            if age is not None and max_age is not None and age >= max_age:
                logger.warning(
                    "revocation_freshness_stale age_seconds=%s max_age_seconds=%s reason=%s",
                    age,
                    max_age,
                    detail.get("reason"),
                )
        return ready, detail
    except Exception as exc:
        logger.warning("Revocation readiness check failed: %s", exc)
        return False, {"ok": False, "error": str(exc)}


def _check_billing_outbox() -> tuple[bool | None, dict[str, Any]]:
    """Informational unless LEMMA_READY_REQUIRE_BILLING_OUTBOX=1."""
    try:
        from api.database import SessionLocal
        from billing.billing_outbox_policy import billing_outbox_queue_age_alert_seconds
        from billing.credential_billing import get_outbox_queue_stats

        db = SessionLocal()
        try:
            stats = get_outbox_queue_stats(db)
        finally:
            db.close()

        threshold = billing_outbox_queue_age_alert_seconds()
        queue_age = stats.get("queue_age_seconds")
        pending = stats.get("pending_count") or 0
        detail = {
            "ok": True,
            "pending_count": pending,
            "queue_age_seconds": queue_age,
            "threshold_seconds": threshold,
        }
        if pending and queue_age is not None and queue_age >= threshold:
            detail["ok"] = False
            detail["reason"] = "queue_age_exceeded"
            logger.warning(
                "billing_outbox_queue_age_seconds=%s pending_count=%s threshold=%s",
                queue_age,
                pending,
                threshold,
            )
        require = _env_truthy("LEMMA_READY_REQUIRE_BILLING_OUTBOX", False)
        if require:
            return bool(detail.get("ok")), detail
        return None, detail
    except Exception as exc:
        logger.warning("Billing outbox readiness check failed: %s", exc)
        detail = {"ok": False, "error": str(exc)}
        if _env_truthy("LEMMA_READY_REQUIRE_BILLING_OUTBOX", False):
            return False, detail
        return None, detail


def readiness_report() -> tuple[dict[str, Any], int]:
    """Build dependency-aware readiness payload and HTTP status code."""
    checks: dict[str, Any] = {}

    db_ok, checks["database"] = _check_database()
    redis_ok, checks["redis"] = _check_redis()
    crypto_ok, checks["crypto"] = _check_crypto()
    rev_ok, checks["revocation"] = _check_revocation()
    billing_required, checks["billing_outbox"] = _check_billing_outbox()

    required = [db_ok, redis_ok, crypto_ok, rev_ok]
    if billing_required is not None:
        required.append(bool(billing_required))

    ready = all(required)
    payload = {
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return payload, 200 if ready else 503
