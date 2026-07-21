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
from billing.stripe_meter_reporter import OUTCOME_REPORTED, MeterReportResult, report_meter_event

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
        result = _attempt_outbox_report(db, outbox, stripe_customer_id=stripe_customer_id)
        reported = result.reported

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


def _resolve_outbox_stripe_customer(db, row) -> str:
    existing = (getattr(row, "stripe_customer_id", None) or "").strip()
    if existing:
        return existing
    resolved = resolve_stripe_customer_id_for_site(db, row.site_scope) or ""
    if resolved:
        row.stripe_customer_id = resolved
    return resolved


def _apply_outbox_report_result(row, result: MeterReportResult, *, now: datetime | None = None) -> None:
    from billing.billing_outbox_policy import (
        billing_outbox_max_attempts,
        compute_next_attempt_at,
    )

    current = now or datetime.utcnow()
    row.attempts = int(row.attempts or 0) + 1
    if result.outcome == OUTCOME_REPORTED:
        row.status = "reported"
        row.reported_at = current
        row.last_error = None
        row.next_attempt_at = None
        return

    row.status = "pending"
    row.last_error = result.detail or (
        "skipped" if result.outcome == "skipped" else "stripe_report_failed"
    )
    if row.attempts >= billing_outbox_max_attempts() and not (row.stripe_customer_id or "").strip():
        row.status = "dead_letter"
        row.last_error = "unresolvable_stripe_customer"
        row.next_attempt_at = None
        return
    if row.attempts >= billing_outbox_max_attempts():
        row.status = "dead_letter"
        row.last_error = result.detail or "max_attempts_exceeded"
        row.next_attempt_at = None
        return
    row.next_attempt_at = compute_next_attempt_at(attempts=row.attempts, now=current)


def _attempt_outbox_report(db, row, *, stripe_customer_id: Optional[str] = None) -> MeterReportResult:
    customer_id = (stripe_customer_id or _resolve_outbox_stripe_customer(db, row) or "").strip()
    result = report_meter_event(
        event_type=row.event_type,
        stripe_customer_id=customer_id,
        site_id=row.site_scope,
        month=row.month,
        event_id=row.event_id,
        unit_count=row.unit_count,
    )
    _apply_outbox_report_result(row, result)
    db.commit()
    return result


def retry_pending_billing_outbox(db, *, limit: int = 100) -> dict[str, int]:
    """Retry aggregate-safe Stripe events without reconstructing user state."""
    from api.database import IsHumanBillingOutbox
    from billing.billing_outbox_policy import outbox_ready_for_retry

    now = datetime.utcnow()
    rows = (
        db.query(IsHumanBillingOutbox)
        .filter(IsHumanBillingOutbox.status == "pending")
        .order_by(IsHumanBillingOutbox.created_at.asc())
        .limit(max(1, min(int(limit), 1000)))
        .all()
    )
    reported = 0
    failed = 0
    dead_letter = 0
    skipped_not_due = 0
    for row in rows:
        if not outbox_ready_for_retry(row, now=now):
            skipped_not_due += 1
            continue
        result = _attempt_outbox_report(db, row)
        if result.reported:
            reported += 1
        elif row.status == "dead_letter":
            dead_letter += 1
        else:
            failed += 1
    return {
        "selected": len(rows),
        "reported": reported,
        "failed": failed,
        "dead_letter": dead_letter,
        "skipped_not_due": skipped_not_due,
    }


def get_outbox_queue_stats(db) -> dict[str, int | float | None]:
    """Return pending/dead-letter counts and oldest pending queue age."""
    from api.database import IsHumanBillingOutbox

    pending_count = db.query(IsHumanBillingOutbox).filter_by(status="pending").count()
    dead_letter_count = db.query(IsHumanBillingOutbox).filter_by(status="dead_letter").count()
    oldest = (
        db.query(IsHumanBillingOutbox.created_at)
        .filter_by(status="pending")
        .order_by(IsHumanBillingOutbox.created_at.asc())
        .first()
    )
    queue_age_seconds = None
    if oldest and oldest[0]:
        queue_age_seconds = max(0.0, (datetime.utcnow() - oldest[0]).total_seconds())
    return {
        "pending_count": int(pending_count or 0),
        "dead_letter_count": int(dead_letter_count or 0),
        "queue_age_seconds": queue_age_seconds,
    }
