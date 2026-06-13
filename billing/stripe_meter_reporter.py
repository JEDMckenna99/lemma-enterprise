"""
Report lemma.id credential billing events to Stripe Billing Meters.

When Stripe is unavailable (tests, missing key), events are logged only.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

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


def report_meter_event(
    *,
    event_type: str,
    stripe_customer_id: str,
    site_id: str,
    ppid_hash: str,
    month: str,
    credential_id: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Emit one Stripe Billing Meter event.

    Returns True when reported (or accepted in dry-run log mode), False on skip/error.
    """
    event_name = METER_EVENTS.get(event_type)
    if not event_name:
        logger.warning("Unknown billing event_type=%s — not reported", event_type)
        return False

    if not stripe_customer_id:
        logger.info(
            "Billing meter skipped (no Stripe customer): event=%s site=%s month=%s",
            event_name,
            site_id,
            month,
        )
        return False

    identifier = f"{site_id}:{ppid_hash}:{event_name}:{month}:{credential_id}"

    payload = {
        "stripe_customer_id": stripe_customer_id,
        "value": "1",
        "site_id": site_id,
        "ppid_hash": ppid_hash,
        "month": month,
        "credential_id": credential_id,
        "event_type": event_type,
    }
    if extra_metadata:
        payload.update(extra_metadata)

    if not stripe_meter_reporting_enabled():
        logger.info("Billing meter (dry-run): %s id=%s", event_name, identifier)
        return True

    if not _configure_stripe():
        logger.info("Billing meter (no Stripe key): %s id=%s", event_name, identifier)
        return False

    try:
        _stripe.billing.MeterEvent.create(
            event_name=event_name,
            identifier=identifier,
            payload=payload,
            timestamp=int(time.time()),
        )
        logger.info("Reported Stripe meter event %s for site=%s", event_name, site_id)
        return True
    except Exception as exc:
        logger.error("Failed to report Stripe meter event %s: %s", event_name, exc)
        return False
