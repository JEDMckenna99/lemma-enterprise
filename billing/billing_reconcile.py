"""Reconcile internal billing aggregates with outbox reporting state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class BillingReconcileIssue:
    code: str
    site_scope: str
    month: str
    detail: str


@dataclass
class BillingReconcileReport:
    scanned_site_months: int = 0
    issues: List[BillingReconcileIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "scanned_site_months": self.scanned_site_months,
            "issue_count": len(self.issues),
            "issues": [
                {
                    "code": issue.code,
                    "site_scope": issue.site_scope,
                    "month": issue.month,
                    "detail": issue.detail,
                }
                for issue in self.issues
            ],
        }


def _expected_outbox_counts(row) -> Dict[str, int]:
    return {
        "initial_issuance": int(getattr(row, "initial_issuances", 0) or 0),
        "mau_renewal": int(getattr(row, "mau_renewals", 0) or 0),
        "doubt_reentry": int(getattr(row, "doubt_reentries", 0) or 0),
    }


def reconcile_billing_state(db) -> BillingReconcileReport:
    from api.database import IsHumanBillingOutbox, IsHumanSiteUsageAggregate

    report = BillingReconcileReport()
    aggregates = db.query(IsHumanSiteUsageAggregate).all()
    report.scanned_site_months = len(aggregates)

    for aggregate in aggregates:
        site_scope = aggregate.site_scope
        month = aggregate.month
        expected = _expected_outbox_counts(aggregate)
        for event_type, expected_count in expected.items():
            if expected_count <= 0:
                continue
            reported_count = (
                db.query(IsHumanBillingOutbox)
                .filter_by(
                    site_scope=site_scope,
                    month=month,
                    event_type=event_type,
                    status="reported",
                )
                .count()
            )
            pending_count = (
                db.query(IsHumanBillingOutbox)
                .filter_by(
                    site_scope=site_scope,
                    month=month,
                    event_type=event_type,
                    status="pending",
                )
                .count()
            )
            if reported_count + pending_count < expected_count:
                report.issues.append(
                    BillingReconcileIssue(
                        code="missing_outbox_rows",
                        site_scope=site_scope,
                        month=month,
                        detail=(
                            f"{event_type}: aggregate={expected_count} "
                            f"outbox_reported={reported_count} outbox_pending={pending_count}"
                        ),
                    )
                )
            if reported_count > expected_count:
                report.issues.append(
                    BillingReconcileIssue(
                        code="duplicate_reported_usage",
                        site_scope=site_scope,
                        month=month,
                        detail=(
                            f"{event_type}: aggregate={expected_count} "
                            f"outbox_reported={reported_count}"
                        ),
                    )
                )

    duplicate_counts: dict[str, int] = {}
    for row in db.query(IsHumanBillingOutbox).all():
        duplicate_counts[row.event_id] = duplicate_counts.get(row.event_id, 0) + 1
    for event_id, count in duplicate_counts.items():
        if count > 1:
            report.issues.append(
                BillingReconcileIssue(
                    code="duplicate_event_id",
                    site_scope="*",
                    month="*",
                    detail=f"event_id={event_id}",
                )
            )

    stale_pending = (
        db.query(IsHumanBillingOutbox)
        .filter_by(status="pending")
        .order_by(IsHumanBillingOutbox.created_at.asc())
        .first()
    )
    if stale_pending and stale_pending.created_at:
        age_hours = (datetime.utcnow() - stale_pending.created_at).total_seconds() / 3600.0
        if age_hours >= 24:
            report.issues.append(
                BillingReconcileIssue(
                    code="stale_pending_outbox",
                    site_scope=stale_pending.site_scope,
                    month=stale_pending.month,
                    detail=f"event_id={stale_pending.event_id} age_hours={age_hours:.1f}",
                )
            )

    return report


def get_customer_usage_summary(db, *, site_scope: str, month: str | None = None) -> Dict[str, Any]:
    from api.database import IsHumanBillingOutbox, IsHumanSiteUsageAggregate

    current_month = month or datetime.utcnow().strftime("%Y-%m")
    aggregate = (
        db.query(IsHumanSiteUsageAggregate)
        .filter_by(site_scope=site_scope, month=current_month)
        .first()
    )
    pending_count = (
        db.query(IsHumanBillingOutbox)
        .filter_by(site_scope=site_scope, month=current_month, status="pending")
        .count()
    )
    dead_letter_count = (
        db.query(IsHumanBillingOutbox)
        .filter_by(site_scope=site_scope, month=current_month, status="dead_letter")
        .count()
    )
    return {
        "month": current_month,
        "active_subjects": int(getattr(aggregate, "active_subjects", 0) or 0),
        "initial_issuances": int(getattr(aggregate, "initial_issuances", 0) or 0),
        "mau_renewals": int(getattr(aggregate, "mau_renewals", 0) or 0),
        "doubt_reentries": int(getattr(aggregate, "doubt_reentries", 0) or 0),
        "outbox_pending": int(pending_count or 0),
        "outbox_dead_letter": int(dead_letter_count or 0),
    }
