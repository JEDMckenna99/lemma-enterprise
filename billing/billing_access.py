"""
Gate site-credential issuance on developer billing status.
"""

from __future__ import annotations

import os
from typing import Optional

from billing.billing_customer import get_registered_site_billing_context


def billing_enforcement_enabled() -> bool:
    return os.getenv("LEMMA_BILLING_ENFORCEMENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def check_site_billing_allows_issuance(db, target_site: str) -> Optional[str]:
    """
    Return an error code when new credential issuance must be blocked, else None.

    Unregistered hostnames (no sites row) are allowed, demo and first integration.
    Registered relying sites require an active metered subscription when enforcement
    is enabled. Managed isHuman demo sites are always exempt so public demos keep working.
    """
    if not billing_enforcement_enabled():
        return None

    ctx = get_registered_site_billing_context(db, target_site)
    if not ctx.get("is_registered_site"):
        return None

    from api.platform_sites import is_demo_site

    if is_demo_site(ctx.get("site_id")):
        return None

    if not ctx.get("customer"):
        return "billing_setup_required"

    status = (ctx.get("subscription_status") or "none").strip().lower()
    if status == "active":
        return None
    if status in ("past_due", "unpaid"):
        return "billing_past_due"
    if status == "canceled":
        return "billing_canceled"
    return "billing_setup_required"
