"""Transactional Stripe webhook idempotency for billing events."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Tuple

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def process_stripe_billing_webhook(db, event: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Persist event_id and apply handler side effects in one transaction.

    Returns (success, detail). Duplicate event IDs are treated as success no-ops.
    """
    from api.database import StripeWebhookEvent
    from billing.stripe_webhook_handlers import dispatch_stripe_billing_event

    event_id = (event.get("id") or "").strip()
    event_type = (event.get("type") or "").strip()
    if not event_id:
        return False, "missing_event_id"

    existing = db.query(StripeWebhookEvent).filter_by(event_id=event_id).first()
    if existing:
        logger.info("Stripe webhook duplicate ignored event_id=%s", event_id)
        return True, "duplicate"

    row = StripeWebhookEvent(
        event_id=event_id,
        event_type=event_type or "unknown",
        status="processing",
        received_at=datetime.utcnow(),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("Stripe webhook duplicate ignored event_id=%s", event_id)
        return True, "duplicate"

    try:
        handled = dispatch_stripe_billing_event(db, event, commit=False)
        row.status = "processed" if handled else "unmatched"
        row.processed_at = datetime.utcnow()
        db.commit()
        return True, row.status
    except Exception:
        db.rollback()
        logger.exception("Stripe billing webhook transaction failed event_id=%s", event_id)
        return False, "handler_failed"
