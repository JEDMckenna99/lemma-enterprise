"""Durable worker loop for pending isHuman billing outbox rows."""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


def _worker_sleep_seconds() -> int:
    raw = os.getenv("LEMMA_BILLING_OUTBOX_WORKER_SLEEP_SECONDS", "60").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 60


def _worker_batch_limit() -> int:
    raw = os.getenv("LEMMA_BILLING_OUTBOX_WORKER_BATCH", "100").strip()
    try:
        return max(1, min(int(raw), 1000))
    except ValueError:
        return 100


def run_outbox_worker_once() -> dict[str, int | float | None]:
    from api.database import SessionLocal
    from billing.billing_outbox_policy import billing_outbox_queue_age_alert_seconds
    from billing.credential_billing import get_outbox_queue_stats, retry_pending_billing_outbox

    db = SessionLocal()
    try:
        result = retry_pending_billing_outbox(db, limit=_worker_batch_limit())
        stats = get_outbox_queue_stats(db)
        result.update(stats)
        threshold = billing_outbox_queue_age_alert_seconds()
        queue_age = stats.get("queue_age_seconds")
        if stats.get("pending_count") and queue_age is not None and queue_age >= threshold:
            logger.warning(
                "billing_outbox_queue_age_seconds=%s pending_count=%s threshold=%s",
                queue_age,
                stats.get("pending_count"),
                threshold,
            )
        return result
    finally:
        db.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting billing outbox worker")
    while True:
        try:
            result = run_outbox_worker_once()
            logger.info(
                "billing_outbox_worker selected=%s reported=%s failed=%s dead_letter=%s pending=%s queue_age=%s",
                result.get("selected"),
                result.get("reported"),
                result.get("failed"),
                result.get("dead_letter"),
                result.get("pending_count"),
                result.get("queue_age_seconds"),
            )
        except Exception:
            logger.exception("billing outbox worker iteration failed")
        time.sleep(_worker_sleep_seconds())


if __name__ == "__main__":
    raise SystemExit(main())
