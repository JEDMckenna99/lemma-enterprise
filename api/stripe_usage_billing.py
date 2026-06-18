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


def _site_info_from_row(site) -> Dict[str, str]:
    return {
        "site_id": site.site_id,
        "site_domain": site.site_domain,
        "admin_email": site.admin_email,
    }


def _resolve_site_for_checkout(
    db,
    site_id: str,
    customer,
    ppid: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Resolve a registered site for Stripe Checkout metadata.

    Mirrors developer site catalog resolution: explicit site_id, customer JSON,
    admin_email linkage, then wallet PPID ownership (SiteAdmin / grants).
    """
    from api.database import Site

    normalized_site_id = (site_id or "").strip()
    if normalized_site_id:
        site = db.query(Site).filter_by(site_id=normalized_site_id).first()
        if site:
            return _site_info_from_row(site)

    if customer:
        sites = list(getattr(customer, "sites", None) or [])
        if sites:
            first = sites[0] or {}
            resolved_site_id = (first.get("site_id") or "").strip()
            if resolved_site_id:
                site = db.query(Site).filter_by(site_id=resolved_site_id).first()
                if site:
                    return _site_info_from_row(site)
                return {
                    "site_id": resolved_site_id,
                    "site_domain": first.get("site_domain") or "",
                    "admin_email": getattr(customer, "email", None) or getattr(customer, "billing_email", None),
                }

        email = (
            getattr(customer, "billing_email", None) or getattr(customer, "email", None) or ""
        ).strip().lower()
        if email:
            site = db.query(Site).filter(Site.admin_email.ilike(email)).first()
            if site:
                return _site_info_from_row(site)

    if ppid:
        from api.developer_api import _get_owned_site_ids

        owned_site_ids = _get_owned_site_ids(db, ppid)
        if owned_site_ids:
            site = db.query(Site).filter(Site.site_id == owned_site_ids[0]).first()
            if site:
                return _site_info_from_row(site)

    return None


@stripe_usage_billing_bp.route("/api/billing/usage-checkout", methods=["POST"])
@require_customer_or_admin
def create_usage_checkout():
    """Create a Stripe Checkout session for pay-as-you-go metered billing."""
    if not _stripe_configured():
        return jsonify({"success": False, "error": "stripe_not_configured"}), 500

    data = request.get_json(silent=True) or {}
    ppid = getattr(g, "ppid", None)
    customer = _customer_for_request()
    email = (
        (data.get("email") or "").strip().lower()
        or (getattr(customer, "billing_email", None) or getattr(customer, "email", None) or "")
    ).strip().lower()

    from api.database import PlatformUser, SessionLocal
    from billing.billing_customer import ensure_billing_customer

    db = SessionLocal()
    try:
        if not email and ppid:
            account = db.query(PlatformUser).filter_by(user_did=ppid).first()
            email = (getattr(account, "email", None) or "").strip().lower()

        if not email:
            return jsonify({
                "success": False,
                "error": "email_required",
                "message": "Provide billing email to start Checkout.",
            }), 400

        if not customer and ppid:
            customer = ensure_billing_customer(
                db,
                ppid=ppid,
                email=email,
                wallet_id=getattr(db.query(PlatformUser).filter_by(user_did=ppid).first(), "wallet_id", None),
            )

        site_info = _resolve_site_for_checkout(
            db,
            data.get("site_id") or "",
            customer,
            ppid=ppid,
        )
        if not site_info or not site_info.get("site_id"):
            return jsonify({
                "success": False,
                "error": "site_required",
                "message": "Register a site first, then return to billing setup.",
            }), 400

        from billing.stripe_catalog import catalog_prices_configured, load_catalog_price_ids

        if not catalog_prices_configured():
            return jsonify({
                "success": False,
                "error": "billing_catalog_not_configured",
                "message": "Run scripts/bootstrap_stripe_billing_catalog.py or set LEMMA_STRIPE_PRICE_* env vars.",
            }), 503

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
                "lemma_owner_ppid": ppid or "",
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
    from api.database import SessionLocal
    from billing.billing_customer import get_registered_site_billing_context

    customer = _customer_for_request()
    ppid = getattr(g, "ppid", None)

    merged_sites: list = []
    if customer:
        from api.customer_accounts import _collect_developer_site_catalog

        merged_sites, _merged_keys = _collect_developer_site_catalog(customer, ppid)

    onboarding = {
        "has_customer": customer is not None,
        "has_site": bool(merged_sites),
        "subscription_active": False,
        "next_step": "register_site",
    }

    if customer:
        onboarding["has_site"] = bool(merged_sites)
        onboarding["subscription_active"] = (customer.subscription_status or "").lower() == "active"
        if not merged_sites:
            onboarding["next_step"] = "register_site"
        elif (customer.subscription_status or "none").lower() != "active":
            onboarding["next_step"] = "complete_checkout"
        else:
            onboarding["next_step"] = "ready"

    db = SessionLocal()
    try:
        if customer:
            email = (
                getattr(customer, "billing_email", None) or getattr(customer, "email", None) or ""
            ).strip().lower()
            if email:
                from api.database import Site

                linked_site = db.query(Site).filter(Site.admin_email.ilike(email)).first()
                if linked_site:
                    onboarding["has_site"] = True
                    if (customer.subscription_status or "none").lower() != "active":
                        onboarding["next_step"] = "complete_checkout"
                    else:
                        onboarding["next_step"] = "ready"

        if customer and onboarding.get("has_site"):
            first_site = merged_sites[0] if merged_sites else {}
            domain = first_site.get("site_domain") or ""
            email = (
                getattr(customer, "billing_email", None) or getattr(customer, "email", None) or ""
            ).strip().lower()
            if not domain and email:
                linked = db.query(Site).filter(Site.admin_email.ilike(email)).first()
                domain = linked.site_domain if linked else ""
            if domain:
                ctx = get_registered_site_billing_context(db, domain)
                onboarding["site_billing"] = {
                    "site_id": ctx.get("site_id"),
                    "site_domain": ctx.get("site_domain"),
                    "subscription_status": ctx.get("subscription_status"),
                }
    finally:
        db.close()

    if not customer:
        return jsonify({
            "success": True,
            "billing": None,
            "onboarding": {**onboarding, "next_step": "provide_email"},
            "ppid": ppid,
        })

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
        "onboarding": onboarding,
        "sites": merged_sites,
        "ppid": ppid,
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
