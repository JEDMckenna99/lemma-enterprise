"""
Gate site-credential issuance on developer billing status.
"""

from __future__ import annotations

import os
from typing import Optional

from billing.credential_billing import resolve_stripe_customer_id_for_site


def billing_enforcement_enabled() -> bool:
    return os.getenv("LEMMA_BILLING_ENFORCEMENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _lookup_subscription_status(db, stripe_customer_id: str) -> Optional[str]:
    from api.database import Customer

    customer = (
        db.query(Customer)
        .filter_by(stripe_customer_id=stripe_customer_id)
        .first()
    )
    if not customer:
        return None
    return (getattr(customer, "subscription_status", None) or "none").strip().lower()


def check_site_billing_allows_issuance(db, target_site: str) -> Optional[str]:
    """
    Return an error code when new credential issuance must be blocked, else None.

    Existing credentials continue to verify locally when billing lapses; only
    lemma.id issuance paths are gated.
    """
    if not billing_enforcement_enabled():
        return None

    stripe_customer_id = resolve_stripe_customer_id_for_site(db, target_site)
    if not stripe_customer_id:
        return None

    status = _lookup_subscription_status(db, stripe_customer_id)
    if status is None:
        return "billing_setup_required"
    if status == "active":
        return None
    if status in ("past_due", "unpaid"):
        return "billing_past_due"
    if status == "canceled":
        return "billing_canceled"
    if status == "none":
        return "billing_setup_required"
    return "billing_inactive"
