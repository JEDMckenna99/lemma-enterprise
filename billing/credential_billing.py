"""
Classify and record billable site-credential events.

lemma.id owns usage classification; Stripe collects payment via Billing Meters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from api.usage_tracking import _hash_ppid_for_mau, track_site_proof_mau
from billing.stripe_catalog import METER_EVENTS, UNIT_AMOUNTS_CENTS
from billing.stripe_meter_reporter import report_meter_event

logger = logging.getLogger(__name__)

ISSUE_MODE_SITE_PROOF = "site_proof"
ISSUE_MODE_FRESH_IDV = "fresh_idv"

EVENT_INITIAL_ISSUANCE = "initial_issuance"
EVENT_MAU_RENEWAL = "mau_renewal"
EVENT_DOUBT_REENTRY = "doubt_reentry"


@dataclass(frozen=True)
class BillingEventResult:
    event_type: Optional[str]
    meter_event_name: Optional[str]
    unit_amount_cents: int
    stripe_customer_id: Optional[str]
    reported_to_stripe: bool
    month: str


def normalize_issue_mode(value: Optional[str]) -> str:
    mode = (value or ISSUE_MODE_SITE_PROOF).strip().lower()
    if mode == ISSUE_MODE_FRESH_IDV:
        return ISSUE_MODE_FRESH_IDV
    return ISSUE_MODE_SITE_PROOF


def classify_billing_event(
    *,
    issue_mode: str,
    had_prior_derived: bool,
    first_issuance_month: Optional[str],
    current_month: str,
) -> Optional[str]:
    """
    Return a billable event type, or None when no charge applies.

    Rules:
      - fresh_idv + prior derived row  -> doubt_reentry ($0.35)
      - fresh_idv + no prior derived  -> initial_issuance (mislabeled first visit)
      - site_proof + no prior derived -> initial_issuance ($0.35)
      - site_proof + prior derived, month after first issuance -> mau_renewal ($0.01)
      - site_proof + prior derived, still in issuance month -> None (free)
    """
    mode = normalize_issue_mode(issue_mode)

    if mode == ISSUE_MODE_FRESH_IDV:
        if had_prior_derived:
            return EVENT_DOUBT_REENTRY
        return EVENT_INITIAL_ISSUANCE

    if not had_prior_derived:
        return EVENT_INITIAL_ISSUANCE

    if first_issuance_month and current_month > first_issuance_month:
        return EVENT_MAU_RENEWAL
    return None


def had_prior_derived_credential(
    db,
    *,
    target_site: str,
    ppid: str,
    exclude_credential_id: Optional[str] = None,
) -> bool:
    from api.database import DerivedCredential

    if not target_site or not ppid:
        return False
    rows = (
        db.query(DerivedCredential)
        .filter_by(target_site=target_site, derived_ppid=ppid)
        .all()
    )
    if exclude_credential_id:
        rows = [
            row
            for row in rows
            if getattr(row, "derived_credential_id", None) != exclude_credential_id
        ]
    return len(rows) > 0


def first_issuance_month_for_ppid(db, *, target_site: str, ppid: str) -> Optional[str]:
    from api.database import DerivedCredential

    if not target_site or not ppid:
        return None
    rows = (
        db.query(DerivedCredential)
        .filter_by(target_site=target_site, derived_ppid=ppid)
        .all()
    )
    if not rows:
        return None
    earliest = min(
        rows,
        key=lambda row: getattr(row, "created_at", None) or datetime.min,
    )
    if not getattr(earliest, "created_at", None):
        return None
    return earliest.created_at.strftime("%Y-%m")


def resolve_stripe_customer_id_for_site(db, target_site: str) -> Optional[str]:
    """Look up Stripe customer id from registered site admin email."""
    from api.database import Customer
    from api.site_ppid_revocation import resolve_site_by_domain

    site = resolve_site_by_domain(db, target_site)
    if not site:
        return None

    email = (getattr(site, "admin_email", None) or "").strip().lower()
    if not email:
        return None

    customer = (
        db.query(Customer)
        .filter(Customer.email.ilike(email))
        .first()
    )
    stripe_id = getattr(customer, "stripe_customer_id", None) if customer else None
    return (stripe_id or "").strip() or None


def resolve_billing_site_key(db, target_site: str) -> str:
    from api.site_ppid_revocation import resolve_site_by_domain

    site = resolve_site_by_domain(db, target_site)
    if site and getattr(site, "site_id", None):
        return site.site_id
    return (target_site or "").strip()


def record_credential_billing_event(
    db,
    *,
    target_site: str,
    ppid: str,
    credential_id: str,
    issue_mode: Optional[str] = None,
    is_cached_reissue: bool = False,
    month: Optional[str] = None,
) -> BillingEventResult:
    """
    Classify a site-credential issuance, track MAU for ops, and report to Stripe.
    """
    current_month = month or datetime.utcnow().strftime("%Y-%m")
    site_key = resolve_billing_site_key(db, target_site)
    ppid_hash = _hash_ppid_for_mau(ppid)

    exclude_id = None if is_cached_reissue else (credential_id or None)
    had_prior = had_prior_derived_credential(
        db,
        target_site=target_site,
        ppid=ppid,
        exclude_credential_id=exclude_id,
    )
    first_month = first_issuance_month_for_ppid(db, target_site=target_site, ppid=ppid)

    event_type = classify_billing_event(
        issue_mode=normalize_issue_mode(issue_mode),
        had_prior_derived=had_prior,
        first_issuance_month=first_month,
        current_month=current_month,
    )

    stripe_customer_id = resolve_stripe_customer_id_for_site(db, target_site)

    if event_type == EVENT_MAU_RENEWAL:
        if not track_site_proof_mau(site_key, ppid, month=current_month):
            event_type = None

    reported = False
    meter_name = METER_EVENTS.get(event_type) if event_type else None
    unit_cents = UNIT_AMOUNTS_CENTS.get(event_type, 0) if event_type else 0

    if event_type:
        logger.info(
            "Credential billing: event=%s site=%s month=%s credential=%s cached=%s mode=%s",
            event_type,
            site_key,
            current_month,
            (credential_id or "")[:24],
            is_cached_reissue,
            normalize_issue_mode(issue_mode),
        )
        reported = report_meter_event(
            event_type=event_type,
            stripe_customer_id=stripe_customer_id or "",
            site_id=site_key,
            ppid_hash=ppid_hash,
            month=current_month,
            credential_id=credential_id or "",
        )
    elif is_cached_reissue:
        track_site_proof_mau(site_key, ppid, month=current_month)

    return BillingEventResult(
        event_type=event_type,
        meter_event_name=meter_name,
        unit_amount_cents=unit_cents,
        stripe_customer_id=stripe_customer_id,
        reported_to_stripe=reported,
        month=current_month,
    )
