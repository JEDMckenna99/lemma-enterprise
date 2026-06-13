"""
Lemma billing customer provisioning and site ↔ customer resolution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from api.site_ppid_revocation import resolve_site_by_domain

logger = logging.getLogger(__name__)


def find_customer_by_email(db, email: str):
    from api.database import Customer

    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    return (
        db.query(Customer)
        .filter(Customer.email.ilike(normalized))
        .first()
    )


def get_registered_site_billing_context(db, target_site: str) -> Dict[str, Any]:
    """Return billing context for a relying site hostname."""
    site = resolve_site_by_domain(db, target_site)
    if not site:
        return {"is_registered_site": False}

    email = (getattr(site, "admin_email", None) or "").strip().lower()
    customer = find_customer_by_email(db, email) if email else None
    subscription_status = None
    stripe_customer_id = None
    if customer:
        subscription_status = (getattr(customer, "subscription_status", None) or "none").strip().lower()
        stripe_customer_id = (getattr(customer, "stripe_customer_id", None) or "").strip() or None

    return {
        "is_registered_site": True,
        "site_id": getattr(site, "site_id", None),
        "site_domain": getattr(site, "site_domain", None),
        "admin_email": email,
        "customer": customer,
        "customer_id": getattr(customer, "customer_id", None) if customer else None,
        "subscription_status": subscription_status,
        "stripe_customer_id": stripe_customer_id,
    }


def ensure_billing_customer(
    db,
    *,
    ppid: str,
    email: str,
    name: Optional[str] = None,
    company: Optional[str] = None,
    wallet_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Ensure a lemma customers row (+ Stripe customer) exists for a developer PPID.

    Returns the hydrated Customer dataclass from customer_manager, or None on failure.
    """
    from api.customer_accounts import customer_manager
    from api.database import PlatformUser
    from api.platform_account import upsert_platform_account

    normalized_email = (email or "").strip().lower()
    if not ppid or not normalized_email:
        return None

    existing = customer_manager.get_customer_by_did(ppid)
    if not existing:
        existing = customer_manager.get_customer_by_email(normalized_email)

    if existing:
        customer_id = existing.customer_id
    else:
        result = customer_manager.create_customer(
            email=normalized_email,
            name=name or normalized_email.split("@", 1)[0],
            company=company or "",
            billing_email=normalized_email,
            customer_did=ppid,
            wallet_id=wallet_id,
            display_name=name or normalized_email.split("@", 1)[0],
            skip_default_api_key=True,
        )
        if not result.get("success"):
            logger.warning("ensure_billing_customer create failed: %s", result.get("error"))
            return None
        customer_id = result["customer_id"]
        existing = customer_manager.get_customer(customer_id)

    account = db.query(PlatformUser).filter_by(user_did=ppid).first()
    if account and getattr(account, "billing_customer_id", None) != customer_id:
        upsert_platform_account(
            ppid,
            billing_customer_id=customer_id,
            email=normalized_email,
            db=db,
        )
        db.commit()

    return existing


def link_customer_to_site(
    db,
    *,
    customer_id: str,
    site_id: str,
    site_domain: str,
    admin_email: str,
    company_name: str = "Lemma Developer",
) -> None:
    """Ensure sites table row exists and points at the billing customer."""
    try:
        from api.storage_helpers import upsert_site_to_postgres

        upsert_site_to_postgres(
            site_id=site_id,
            site_domain=site_domain,
            customer_id=customer_id,
            company_name=company_name,
            admin_email=admin_email,
            environment="production",
            site_label=site_domain,
        )
    except Exception as exc:
        logger.warning("Could not upsert site %s for billing: %s", site_id, exc)
