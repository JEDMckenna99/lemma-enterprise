"""Privacy-minimized site credential billing.

Only a keyed token of the already site-private PPID is retained.  No wallet,
person, master credential, or site credential identifier is stored here.
"""

from __future__ import annotations

import logging
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from api.usage_tracking import _hash_ppid_for_mau
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
    return ISSUE_MODE_FRESH_IDV if (value or "").strip().lower() == ISSUE_MODE_FRESH_IDV else ISSUE_MODE_SITE_PROOF


def classify_billing_event(
    *,
    issue_mode: str,
    had_prior_derived: bool,
    first_issuance_month: Optional[str],
    current_month: str,
    active_doubt: bool = False,
    monthly_first_seen: bool = True,
) -> Optional[str]:
    """Pure billing policy retained as a stable public test seam."""
    if not had_prior_derived:
        return EVENT_INITIAL_ISSUANCE
    if normalize_issue_mode(issue_mode) == ISSUE_MODE_FRESH_IDV and active_doubt:
        return EVENT_DOUBT_REENTRY
    if first_issuance_month and current_month > first_issuance_month and monthly_first_seen:
        return EVENT_MAU_RENEWAL
    return None


def resolve_stripe_customer_id_for_site(db, target_site: str) -> Optional[str]:
    from billing.billing_customer import get_registered_site_billing_context

    ctx = get_registered_site_billing_context(db, target_site)
    return (ctx.get("stripe_customer_id") or "").strip() or None


def resolve_billing_site_key(db, target_site: str) -> str:
    from api.site_ppid_revocation import resolve_site_by_domain

    site = resolve_site_by_domain(db, target_site)
    return (getattr(site, "site_id", None) if site else None) or (target_site or "").strip().lower()


def _active_doubt(db, *, site_scope: str, ppid: str):
    from api.database import SiteDoubt

    return db.query(SiteDoubt).filter_by(site_id=site_scope, ppid=ppid, is_active=True).first()


def _lock_site_billing_subject_transaction(db, *, site_scope: str, subject_token: str) -> None:
    """Serialize classification for one site subject on PostgreSQL.

    The uniqueness constraints remain the final invariant; this lock ensures
    concurrent first issuance/renewal requests do not race into an error or
    produce duplicate aggregate/outbox events.
    """
    try:
        bind = db.get_bind()
    except (AttributeError, TypeError):
        return
    if getattr(getattr(bind, "dialect", None), "name", "") != "postgresql":
        return
    from sqlalchemy import text

    digest = hashlib.sha256(f"{site_scope}\0{subject_token}".encode("utf-8")).digest()
    lock_key = int.from_bytes(digest[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def _increment_aggregate(db, *, site_scope: str, month: str, event_type: str) -> None:
    from api.database import IsHumanSiteUsageAggregate

    row = db.query(IsHumanSiteUsageAggregate).filter_by(site_scope=site_scope, month=month).first()
    if not row:
        row = IsHumanSiteUsageAggregate(site_scope=site_scope, month=month)
        db.add(row)
        db.flush()
    field = {
        EVENT_INITIAL_ISSUANCE: "initial_issuances",
        EVENT_MAU_RENEWAL: "mau_renewals",
        EVENT_DOUBT_REENTRY: "doubt_reentries",
    }[event_type]
    setattr(row, field, int(getattr(row, field, 0) or 0) + 1)
    row.updated_at = datetime.utcnow()


def _increment_active_subjects(db, *, site_scope: str, month: str) -> None:
    from api.database import IsHumanSiteUsageAggregate

    row = db.query(IsHumanSiteUsageAggregate).filter_by(site_scope=site_scope, month=month).first()
    if not row:
        row = IsHumanSiteUsageAggregate(site_scope=site_scope, month=month)
        db.add(row)
        db.flush()
    row.active_subjects = int(getattr(row, "active_subjects", 0) or 0) + 1
    row.updated_at = datetime.utcnow()


def record_credential_billing_event(
    db,
    *,
    target_site: str,
    ppid: str,
    credential_id: str = "",  # accepted but deliberately never retained
    issue_mode: Optional[str] = None,
    is_cached_reissue: bool = False,  # legacy compatibility; no storage effect
    month: Optional[str] = None,
) -> BillingEventResult:
    """Record one issuance using site-local tokens and a privacy-safe outbox."""
    from api.database import (
        IsHumanBillingOutbox,
        IsHumanSiteMonthlyUsage,
        IsHumanSiteBillingSubject,
    )

    now = datetime.utcnow()
    current_month = month or now.strftime("%Y-%m")
    site_scope = resolve_billing_site_key(db, target_site)
    subject_token = _hash_ppid_for_mau(ppid)
    _lock_site_billing_subject_transaction(db, site_scope=site_scope, subject_token=subject_token)
    subject = db.query(IsHumanSiteBillingSubject).filter_by(
        site_scope=site_scope, subject_token=subject_token,
    ).first()
    had_prior = subject is not None
    if not subject:
        subject = IsHumanSiteBillingSubject(
            site_scope=site_scope,
            subject_token=subject_token,
            first_issuance_month=current_month,
            first_issued_at=now,
            last_issued_at=now,
        )
        db.add(subject)
    else:
        subject.last_issued_at = now

    monthly = db.query(IsHumanSiteMonthlyUsage).filter_by(
        site_scope=site_scope, month=current_month, subject_token=subject_token,
    ).first()
    monthly_first_seen = monthly is None
    if monthly_first_seen:
        db.add(IsHumanSiteMonthlyUsage(
            site_scope=site_scope,
            month=current_month,
            subject_token=subject_token,
            first_seen_at=now,
        ))
        _increment_active_subjects(db, site_scope=site_scope, month=current_month)

    doubt = _active_doubt(db, site_scope=site_scope, ppid=ppid)
    event_type = classify_billing_event(
        issue_mode=normalize_issue_mode(issue_mode),
        had_prior_derived=had_prior,
        first_issuance_month=getattr(subject, "first_issuance_month", current_month),
        current_month=current_month,
        active_doubt=doubt is not None,
        monthly_first_seen=monthly_first_seen,
    )

    if doubt is not None and normalize_issue_mode(issue_mode) == ISSUE_MODE_FRESH_IDV:
        doubt.is_active = False
        doubt.cleared_at = now
        doubt.cleared_by = "fresh_idv_same_ppid"

    stripe_customer_id = resolve_stripe_customer_id_for_site(db, target_site)
    outbox = None
    if event_type:
        _increment_aggregate(db, site_scope=site_scope, month=current_month, event_type=event_type)
        outbox = IsHumanBillingOutbox(
            event_id=f"bevt_{secrets.token_urlsafe(24)}",
            stripe_customer_id=stripe_customer_id,
            site_scope=site_scope,
            month=current_month,
            event_type=event_type,
            unit_count=1,
            status="pending",
            created_at=now,
        )
        db.add(outbox)

    db.commit()

    reported = False
    if outbox is not None:
        reported = report_meter_event(
            event_type=event_type,
            stripe_customer_id=stripe_customer_id or "",
            site_id=site_scope,
            month=current_month,
            event_id=outbox.event_id,
            unit_count=1,
        )
        outbox.attempts = int(outbox.attempts or 0) + 1
        if reported:
            outbox.status = "reported"
            outbox.reported_at = datetime.utcnow()
            outbox.last_error = None
        else:
            outbox.last_error = "stripe_report_failed"
        db.commit()

    return BillingEventResult(
        event_type=event_type,
        meter_event_name=METER_EVENTS.get(event_type) if event_type else None,
        unit_amount_cents=UNIT_AMOUNTS_CENTS.get(event_type, 0) if event_type else 0,
        stripe_customer_id=stripe_customer_id,
        reported_to_stripe=reported,
        month=current_month,
    )


def purge_monthly_subject_usage(db, *, now: Optional[datetime] = None) -> int:
    """Delete subject-level monthly rows older than the 90-day boundary."""
    from api.database import IsHumanSiteMonthlyUsage

    cutoff = (now or datetime.utcnow()) - timedelta(days=90)
    deleted = db.query(IsHumanSiteMonthlyUsage).filter(
        IsHumanSiteMonthlyUsage.first_seen_at < cutoff
    ).delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def retry_pending_billing_outbox(db, *, limit: int = 100) -> dict[str, int]:
    """Retry aggregate-safe Stripe events without reconstructing user state."""
    from api.database import IsHumanBillingOutbox

    rows = (
        db.query(IsHumanBillingOutbox)
        .filter_by(status="pending")
        .order_by(IsHumanBillingOutbox.created_at.asc())
        .limit(max(1, min(int(limit), 1000)))
        .all()
    )
    reported = 0
    failed = 0
    for row in rows:
        ok = report_meter_event(
            event_type=row.event_type,
            stripe_customer_id=row.stripe_customer_id or "",
            site_id=row.site_scope,
            month=row.month,
            event_id=row.event_id,
            unit_count=row.unit_count,
        )
        row.attempts = int(row.attempts or 0) + 1
        if ok:
            row.status = "reported"
            row.reported_at = datetime.utcnow()
            row.last_error = None
            reported += 1
        else:
            row.last_error = "stripe_report_failed"
            failed += 1
    db.commit()
    return {"selected": len(rows), "reported": reported, "failed": failed}
