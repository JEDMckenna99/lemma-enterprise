"""Durable worker for scheduled data-retention purges (Section 9)."""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


def _worker_sleep_seconds() -> int:
    raw = os.getenv("LEMMA_RETENTION_WORKER_SLEEP_SECONDS", "3600").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


def run_retention_once() -> dict[str, int | bool]:
    from api.config import is_ishuman_didit_purge_enabled
    from api.database import SessionLocal
    from billing.credential_billing import purge_monthly_subject_usage

    db = SessionLocal()
    try:
        deleted = purge_monthly_subject_usage(db)
        return {
            "deleted_monthly_subject_rows": deleted,
            "didit_purge_enabled": is_ishuman_didit_purge_enabled(),
        }
    finally:
        db.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting retention worker")
    while True:
        try:
            result = run_retention_once()
            logger.info(
                "retention_worker deleted_monthly_subject_rows=%s didit_purge_enabled=%s",
                result.get("deleted_monthly_subject_rows"),
                result.get("didit_purge_enabled"),
            )
        except Exception:
            logger.exception("retention worker iteration failed")
        time.sleep(_worker_sleep_seconds())


if __name__ == "__main__":
    raise SystemExit(main())
