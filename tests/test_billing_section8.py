"""Section 8 billing integrity tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from billing.billing_reconcile import reconcile_billing_state
from billing.credential_billing import record_credential_billing_event, retry_pending_billing_outbox
from billing.stripe_meter_reporter import OUTCOME_FAILED, OUTCOME_REPORTED, OUTCOME_SKIPPED, MeterReportResult
from billing.stripe_webhook_idempotency import process_stripe_billing_webhook


@pytest.mark.unit
def test_dry_run_does_not_mark_outbox_reported(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import IsHumanBillingOutbox

    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: MeterReportResult(OUTCOME_SKIPPED, "reporting_disabled"),
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_stripe_customer_id_for_site",
        lambda _db, _site: "cus_test_123",
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_billing_site_key",
        lambda _db, _site: "site_example",
    )

    db = fake_ishuman_db_session_factory.session_local()
    result = record_credential_billing_event(
        db,
        target_site="example.com",
        ppid="did:lemma:ppid_dry_run",
        month="2026-04",
    )
    assert result.reported_to_stripe is False
    outbox = db.query(IsHumanBillingOutbox).one()
    assert outbox.status == "pending"
    assert outbox.last_error == "reporting_disabled"


@pytest.mark.unit
def test_stripe_outage_keeps_outbox_pending(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import IsHumanBillingOutbox

    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: MeterReportResult(OUTCOME_FAILED, "stripe_timeout"),
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_stripe_customer_id_for_site",
        lambda _db, _site: "cus_test_123",
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_billing_site_key",
        lambda _db, _site: "site_example",
    )

    db = fake_ishuman_db_session_factory.session_local()
    record_credential_billing_event(
        db,
        target_site="example.com",
        ppid="did:lemma:ppid_outage",
        month="2026-04",
    )
    outbox = db.query(IsHumanBillingOutbox).one()
    assert outbox.status == "pending"
    assert "stripe_timeout" in (outbox.last_error or "")


@pytest.mark.unit
def test_duplicate_stripe_webhook_is_idempotent(fake_ishuman_db_session_factory):
    from api.database import Customer, StripeWebhookEvent

    store = fake_ishuman_db_session_factory.store
    store.data[Customer.__name__].append(
        Customer(
            customer_id="cus_webhook",
            email="billing@example.com",
            stripe_customer_id="cus_stripe_webhook",
            subscription_status="none",
            api_keys=[],
            sites=[],
            created_at=datetime.utcnow(),
        )
    )
    db = fake_ishuman_db_session_factory.session_local()
    event = {
        "id": "evt_duplicate_001",
        "type": "invoice.paid",
        "data": {"object": {"customer": "cus_stripe_webhook", "subscription": "sub_123"}},
    }

    ok1, detail1 = process_stripe_billing_webhook(db, event)
    ok2, detail2 = process_stripe_billing_webhook(db, event)

    assert ok1 is True and detail1 == "processed"
    assert ok2 is True and detail2 == "duplicate"
    assert db.query(StripeWebhookEvent).count() == 1
    customer = store.data[Customer.__name__][0]
    assert customer.subscription_status == "active"


@pytest.mark.unit
def test_worker_retry_resolves_customer_and_reports(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import IsHumanBillingOutbox

    store = fake_ishuman_db_session_factory.store
    store.data[IsHumanBillingOutbox.__name__].append(
        IsHumanBillingOutbox(
            event_id="bevt_retry_001",
            stripe_customer_id=None,
            site_scope="site_example",
            month="2026-05",
            event_type="initial_issuance",
            unit_count=1,
            status="pending",
            attempts=0,
            created_at=datetime.utcnow() - timedelta(minutes=5),
        )
    )

    monkeypatch.setattr(
        "billing.credential_billing.resolve_stripe_customer_id_for_site",
        lambda _db, _site: "cus_resolved",
    )
    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: MeterReportResult(OUTCOME_REPORTED),
    )

    db = fake_ishuman_db_session_factory.session_local()
    result = retry_pending_billing_outbox(db, limit=10)
    row = store.data[IsHumanBillingOutbox.__name__][0]
    assert result["reported"] == 1
    assert row.status == "reported"
    assert row.stripe_customer_id == "cus_resolved"


@pytest.mark.unit
def test_unresolvable_customer_dead_letters_after_max_attempts(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import IsHumanBillingOutbox

    store = fake_ishuman_db_session_factory.store
    row = IsHumanBillingOutbox(
        event_id="bevt_dead_001",
        stripe_customer_id=None,
        site_scope="site_example",
        month="2026-05",
        event_type="initial_issuance",
        unit_count=1,
        status="pending",
        attempts=7,
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    store.data[IsHumanBillingOutbox.__name__].append(row)

    monkeypatch.setenv("LEMMA_BILLING_OUTBOX_MAX_ATTEMPTS", "8")
    monkeypatch.setattr(
        "billing.credential_billing.resolve_stripe_customer_id_for_site",
        lambda _db, _site: None,
    )
    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: MeterReportResult(OUTCOME_SKIPPED, "missing_stripe_customer"),
    )

    db = fake_ishuman_db_session_factory.session_local()
    retry_pending_billing_outbox(db, limit=10)
    assert row.status == "dead_letter"
    assert row.last_error == "unresolvable_stripe_customer"


@pytest.mark.unit
def test_reconcile_detects_missing_outbox_rows(fake_ishuman_db_session_factory):
    from api.database import IsHumanSiteUsageAggregate

    store = fake_ishuman_db_session_factory.store
    store.data[IsHumanSiteUsageAggregate.__name__].append(
        IsHumanSiteUsageAggregate(
            site_scope="site_example",
            month="2026-06",
            initial_issuances=2,
            mau_renewals=0,
            doubt_reentries=0,
            active_subjects=2,
        )
    )
    db = fake_ishuman_db_session_factory.session_local()
    report = reconcile_billing_state(db)
    assert report.ok is False
    assert any(issue.code == "missing_outbox_rows" for issue in report.issues)
