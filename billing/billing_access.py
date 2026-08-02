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

    When enforcement is enabled, only registered sites (Section 3 registration path)
    with an active metered subscription may issue billable credentials. Unregistered
    hostnames are blocked. Managed platform/demo sites (lemma.id + isHuman demos)
    are always exempt — the product cannot bill itself to let people sign in.

    Free-tier "Sign in with lemma.id" (passkey login, no site registration) requires
    ``LEMMA_BILLING_ENFORCEMENT`` to stay off — enabling enforcement blocks issuance
    for unregistered hostnames and breaks the no-registration login product.
    """
    if not billing_enforcement_enabled():
        return None

    from api.platform_owner import is_platform_site
    from api.platform_sites import is_demo_site, is_managed_platform_site

    # Hostname check first so platform dogfood/sign-in cannot fail closed on
    # a missing/mis-linked sites row while enforcement is on.
    if is_platform_site(target_site):
        return None

    ctx = get_registered_site_billing_context(db, target_site)
    if not ctx.get("is_registered_site"):
        return "billing_site_unregistered"

    site_id = ctx.get("site_id")
    if is_demo_site(site_id) or is_managed_platform_site(site_id) or is_platform_site(site_id):
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
