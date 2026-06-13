"""
Pure handlers for Stripe Billing webhooks (checkout + invoices + subscriptions).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
PAST_DUE_SUBSCRIPTION_STATUSES = {"past_due", "unpaid"}
INACTIVE_SUBSCRIPTION_STATUSES = {"canceled", "incomplete_expired"}


def map_stripe_subscription_status(stripe_status: Optional[str]) -> str:
    normalized = (stripe_status or "").strip().lower()
    if normalized in ACTIVE_SUBSCRIPTION_STATUSES:
        return "active"
    if normalized in PAST_DUE_SUBSCRIPTION_STATUSES:
        return "past_due"
    if normalized in INACTIVE_SUBSCRIPTION_STATUSES:
        return "canceled"
    if normalized == "incomplete":
        return "none"
    return "none"


def _find_customer(
    db,
    *,
    stripe_customer_id: Optional[str] = None,
    email: Optional[str] = None,
):
    from api.database import Customer

    if stripe_customer_id:
        row = db.query(Customer).filter_by(stripe_customer_id=stripe_customer_id).first()
        if row:
            return row

    normalized_email = (email or "").strip().lower()
    if normalized_email:
        return (
            db.query(Customer)
            .filter(Customer.email.ilike(normalized_email))
            .first()
        )
    return None


def _apply_customer_billing_update(
    db,
    customer,
    *,
    stripe_customer_id: Optional[str] = None,
    subscription_status: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
) -> None:
    if stripe_customer_id:
        customer.stripe_customer_id = stripe_customer_id
    if subscription_status:
        customer.subscription_status = subscription_status
    if stripe_subscription_id:
        usage = dict(getattr(customer, "monthly_usage", None) or {})
        usage["stripe_subscription_id"] = stripe_subscription_id
        customer.monthly_usage = usage
    db.commit()


def handle_checkout_session_completed(db, session_obj: Dict[str, Any]) -> bool:
    stripe_customer_id = session_obj.get("customer")
    email = session_obj.get("customer_email") or session_obj.get("customer_details", {}).get("email")
    metadata = session_obj.get("metadata") or {}
    subscription_id = session_obj.get("subscription")

    customer = _find_customer(db, stripe_customer_id=stripe_customer_id, email=email)
    if not customer and email:
        logger.warning("Checkout completed but no lemma customer for email=%s", email)
        return False

    if not customer:
        return False

    _apply_customer_billing_update(
        db,
        customer,
        stripe_customer_id=stripe_customer_id or customer.stripe_customer_id,
        subscription_status="active",
        stripe_subscription_id=subscription_id,
    )
    logger.info(
        "Billing checkout linked customer=%s site=%s subscription=%s",
        customer.customer_id,
        metadata.get("lemma_site_id"),
        subscription_id,
    )
    return True


def handle_invoice_paid(db, invoice_obj: Dict[str, Any]) -> bool:
    stripe_customer_id = invoice_obj.get("customer")
    subscription_id = invoice_obj.get("subscription")
    customer = _find_customer(db, stripe_customer_id=stripe_customer_id)
    if not customer:
        logger.warning("invoice.paid with unknown Stripe customer %s", stripe_customer_id)
        return False

    _apply_customer_billing_update(
        db,
        customer,
        stripe_customer_id=stripe_customer_id,
        subscription_status="active",
        stripe_subscription_id=subscription_id,
    )
    return True


def handle_invoice_payment_failed(db, invoice_obj: Dict[str, Any]) -> bool:
    stripe_customer_id = invoice_obj.get("customer")
    customer = _find_customer(db, stripe_customer_id=stripe_customer_id)
    if not customer:
        logger.warning("invoice.payment_failed with unknown Stripe customer %s", stripe_customer_id)
        return False

    _apply_customer_billing_update(
        db,
        customer,
        stripe_customer_id=stripe_customer_id,
        subscription_status="past_due",
    )
    logger.info("Billing past_due for customer=%s", customer.customer_id)
    return True


def handle_subscription_updated(db, subscription_obj: Dict[str, Any]) -> bool:
    stripe_customer_id = subscription_obj.get("customer")
    subscription_id = subscription_obj.get("id")
    status = map_stripe_subscription_status(subscription_obj.get("status"))

    customer = _find_customer(db, stripe_customer_id=stripe_customer_id)
    if not customer:
        logger.warning("subscription update with unknown Stripe customer %s", stripe_customer_id)
        return False

    _apply_customer_billing_update(
        db,
        customer,
        stripe_customer_id=stripe_customer_id,
        subscription_status=status,
        stripe_subscription_id=subscription_id,
    )
    return True


def handle_subscription_deleted(db, subscription_obj: Dict[str, Any]) -> bool:
    stripe_customer_id = subscription_obj.get("customer")
    customer = _find_customer(db, stripe_customer_id=stripe_customer_id)
    if not customer:
        return False

    _apply_customer_billing_update(
        db,
        customer,
        stripe_customer_id=stripe_customer_id,
        subscription_status="canceled",
    )
    logger.info("Billing canceled for customer=%s", customer.customer_id)
    return True


def dispatch_stripe_billing_event(db, event: Dict[str, Any]) -> bool:
    """Route a verified Stripe event dict to the appropriate handler."""
    event_type = event.get("type")
    data_obj = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        return handle_checkout_session_completed(db, data_obj)
    if event_type == "invoice.paid":
        return handle_invoice_paid(db, data_obj)
    if event_type == "invoice.payment_failed":
        return handle_invoice_payment_failed(db, data_obj)
    if event_type == "customer.subscription.updated":
        return handle_subscription_updated(db, data_obj)
    if event_type == "customer.subscription.deleted":
        return handle_subscription_deleted(db, data_obj)

    logger.debug("Unhandled Stripe billing event type: %s", event_type)
    return True
