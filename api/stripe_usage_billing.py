"""
Usage-based Stripe Billing: Checkout onboarding, status API, and webhooks.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from flask import Blueprint, g, jsonify, redirect, request

from auth.decorators import require_customer_or_admin

logger = logging.getLogger(__name__)

try:
    import stripe

    STRIPE_AVAILABLE = True
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
except ImportError:
    STRIPE_AVAILABLE = False
    stripe = None  # type: ignore

stripe_usage_billing_bp = Blueprint("stripe_usage_billing", __name__)


def _stripe_configured() -> bool:
    return bool(STRIPE_AVAILABLE and (os.getenv("STRIPE_SECRET_KEY") or "").strip())


def _customer_for_request():
    from api.customer_accounts import customer_manager

    customer_id = getattr(request, "customer_id", None)
    if customer_id:
        return customer_manager.get_customer(customer_id)

    ppid = getattr(g, "ppid", None)
    if ppid:
        customer = customer_manager.get_customer_by_did(ppid)
        if customer:
            return customer
        try:
            from api.database import PlatformUser, get_db

            db = get_db()
            try:
                account = db.query(PlatformUser).filter_by(user_did=ppid).first()
                billing_id = getattr(account, "billing_customer_id", None) if account else None
                if billing_id:
                    return customer_manager.get_customer(billing_id)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not resolve billing customer for ppid: %s", exc)
    return None


def _resolve_site_for_checkout(db, site_id: str, customer) -> Optional[Dict[str, str]]:
    from api.database import Site

    normalized_site_id = (site_id or "").strip()
    if normalized_site_id:
        site = db.query(Site).filter_by(site_id=normalized_site_id).first()
        if site:
            return {
                "site_id": site.site_id,
                "site_domain": site.site_domain,
                "admin_email": site.admin_email,
            }

    if not customer:
        return None

    sites = list(getattr(customer, "sites", None) or [])
    if sites:
        first = sites[0] or {}
        return {
            "site_id": first.get("site_id") or "",
            "site_domain": first.get("site_domain") or "",
            "admin_email": getattr(customer, "email", None) or getattr(customer, "billing_email", None),
        }
    return None


@stripe_usage_billing_bp.route("/api/billing/usage-checkout", methods=["POST"])
@require_customer_or_admin
def create_usage_checkout():
    """Create a Stripe Checkout session for pay-as-you-go metered billing."""
    if not _stripe_configured():
        return jsonify({"success": False, "error": "stripe_not_configured"}), 500

    from billing.stripe_catalog import catalog_prices_configured, load_catalog_price_ids

    if not catalog_prices_configured():
        return jsonify({
            "success": False,
            "error": "billing_catalog_not_configured",
            "message": "Run scripts/bootstrap_stripe_billing_catalog.py or set LEMMA_STRIPE_PRICE_* env vars.",
        }), 503

    data = request.get_json(silent=True) or {}
    customer = _customer_for_request()
    email = (
        (data.get("email") or "").strip().lower()
        or (getattr(customer, "billing_email", None) or getattr(customer, "email", None) or "")
    ).strip().lower()
    if not email:
        return jsonify({"success": False, "error": "email_required"}), 400

    from api.database import SessionLocal

    db = SessionLocal()
    try:
        site_info = _resolve_site_for_checkout(db, data.get("site_id") or "", customer)
        if not site_info or not site_info.get("site_id"):
            return jsonify({"success": False, "error": "site_required"}), 400

        price_ids = load_catalog_price_ids()
        success_url = (
            data.get("success_url")
            or (request.host_url.rstrip("/") + "/developer/billing?billing=success")
        )
        cancel_url = data.get("cancel_url") or (request.host_url.rstrip("/") + "/developer/billing")

        session_kwargs: Dict[str, Any] = {
            "mode": "subscription",
            "line_items": [
                {"price": price_ids["initial_issuance"]},
                {"price": price_ids["mau_renewal"]},
                {"price": price_ids["doubt_reentry"]},
            ],
            "success_url": success_url + ("&" if "?" in success_url else "?") + "session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": cancel_url,
            "metadata": {
                "lemma_site_id": site_info["site_id"],
                "lemma_site_domain": site_info.get("site_domain") or "",
                "lemma_customer_id": getattr(customer, "customer_id", "") if customer else "",
                "billing_model": "usage_metered",
            },
            "subscription_data": {
                "metadata": {
                    "lemma_site_id": site_info["site_id"],
                    "lemma_customer_id": getattr(customer, "customer_id", "") if customer else "",
                },
            },
        }

        if getattr(customer, "stripe_customer_id", None):
            session_kwargs["customer"] = customer.stripe_customer_id
        else:
            session_kwargs["customer_email"] = email

        checkout_session = stripe.checkout.Session.create(**session_kwargs)
        logger.info(
            "Created usage checkout %s for site=%s email=%s",
            checkout_session.id,
            site_info["site_id"],
            email,
        )
        return jsonify({
            "success": True,
            "session_id": checkout_session.id,
            "url": checkout_session.url,
            "site_id": site_info["site_id"],
        })
    except Exception as exc:
        logger.exception("Usage checkout creation failed")
        return jsonify({"success": False, "error": "checkout_failed", "message": str(exc)}), 500
    finally:
        db.close()


@stripe_usage_billing_bp.route("/api/billing/account-status", methods=["GET"])
@require_customer_or_admin
def billing_account_status():
    """Return billing status for the authenticated developer account."""
    customer = _customer_for_request()
    if not customer:
        return jsonify({"success": True, "billing": None})

    usage = dict(getattr(customer, "monthly_usage", None) or {})
    return jsonify({
        "success": True,
        "billing": {
            "customer_id": customer.customer_id,
            "email": customer.email,
            "stripe_customer_id": customer.stripe_customer_id,
            "subscription_status": customer.subscription_status,
            "stripe_subscription_id": usage.get("stripe_subscription_id"),
            "enforcement_enabled": os.getenv("LEMMA_BILLING_ENFORCEMENT", "0").strip().lower()
            in ("1", "true", "yes", "on"),
        },
    })


@stripe_usage_billing_bp.route("/api/webhooks/stripe-billing", methods=["POST"])
def stripe_billing_webhook():
    """Stripe Billing webhook endpoint (checkout, invoices, subscriptions)."""
    if not _stripe_configured():
        return jsonify({"error": "stripe_not_configured"}), 500

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return jsonify({"error": "webhook_not_configured"}), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return jsonify({"error": "invalid_payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "invalid_signature"}), 400

    from api.database import SessionLocal
    from billing.stripe_webhook_handlers import dispatch_stripe_billing_event

    db = SessionLocal()
    try:
        handled = dispatch_stripe_billing_event(db, event)
        if not handled:
            return jsonify({"received": True, "matched": False}), 200
        return jsonify({"received": True}), 200
    except Exception:
        db.rollback()
        logger.exception("Stripe billing webhook handler failed")
        return jsonify({"error": "handler_failed"}), 500
    finally:
        db.close()


@stripe_usage_billing_bp.route("/developer/billing/success")
def developer_billing_success():
    """Redirect helper after Stripe Checkout."""
    return redirect("/developer/billing?billing=success")
