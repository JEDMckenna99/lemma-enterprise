"""
Report lemma.id credential billing events to Stripe Billing Meters.

Dry-run and reporting-disabled modes return ``skipped`` — never ``reported``.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from billing.stripe_catalog import METER_EVENTS

logger = logging.getLogger(__name__)

_stripe_available = False
_stripe = None

try:
    import stripe as _stripe_mod

    _stripe = _stripe_mod
    _stripe_available = True
except ImportError:
    pass


OUTCOME_REPORTED = "reported"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


@dataclass(frozen=True)
class MeterReportResult:
    outcome: str
    detail: str = ""

    @property
    def reported(self) -> bool:
        return self.outcome == OUTCOME_REPORTED


def stripe_meter_reporting_enabled() -> bool:
    if os.getenv("LEMMA_STRIPE_METER_REPORTING", "1").strip().lower() in ("0", "false", "no"):
        return False
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    return bool(key) and _stripe_available


def _configure_stripe() -> bool:
    if not _stripe_available:
        return False
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        return False
    _stripe.api_key = key
    return True


def _is_duplicate_meter_identifier(exc: Exception) -> bool:
    if not _stripe_available:
        return False
    if isinstance(exc, _stripe.error.InvalidRequestError):
        code = (getattr(exc, "code", None) or "").strip().lower()
        if code in {"resource_already_exists", "idempotency_key_in_use"}:
            return True
        message = (getattr(exc, "user_message", None) or str(exc)).lower()
        if "already exists" in message and "identifier" in message:
            return True
    return False


def report_meter_event(
    *,
    event_type: str,
    stripe_customer_id: str,
    site_id: str,
    month: str,
    event_id: str,
    unit_count: int = 1,
) -> MeterReportResult:
    """
    Emit one Stripe Billing Meter event.

    Returns ``reported`` only when Stripe accepted the event (or duplicate identifier).
    """
    event_name = METER_EVENTS.get(event_type)
    if not event_name:
        logger.warning("Unknown billing event_type=%s, not reported", event_type)
        return MeterReportResult(OUTCOME_FAILED, "unknown_event_type")

    if not stripe_customer_id:
        logger.info(
            "Billing meter skipped (no Stripe customer): event=%s site=%s month=%s",
            event_name,
            site_id,
            month,
        )
        return MeterReportResult(OUTCOME_SKIPPED, "missing_stripe_customer")

    identifier = event_id

    payload = {
        "stripe_customer_id": stripe_customer_id,
        "value": str(max(1, int(unit_count))),
        "site_id": site_id,
        "month": month,
        "event_type": event_type,
    }
    if not stripe_meter_reporting_enabled():
        logger.info("Billing meter (dry-run): %s id=%s", event_name, identifier)
        return MeterReportResult(OUTCOME_SKIPPED, "reporting_disabled")

    if not _configure_stripe():
        logger.info("Billing meter (no Stripe key): %s id=%s", event_name, identifier)
        return MeterReportResult(OUTCOME_SKIPPED, "stripe_not_configured")

    try:
        _stripe.billing.MeterEvent.create(
            event_name=event_name,
            identifier=identifier,
            payload=payload,
            timestamp=int(time.time()),
        )
        logger.info("Reported Stripe meter event %s for site=%s", event_name, site_id)
        return MeterReportResult(OUTCOME_REPORTED, "stripe_accepted")
    except Exception as exc:
        if _is_duplicate_meter_identifier(exc):
            logger.info(
                "Stripe meter duplicate identifier accepted id=%s site=%s",
                identifier,
                site_id,
            )
            return MeterReportResult(OUTCOME_REPORTED, "duplicate_identifier")
        logger.error("Failed to report Stripe meter event %s: %s", event_name, exc)
        return MeterReportResult(OUTCOME_FAILED, str(exc)[:500])
