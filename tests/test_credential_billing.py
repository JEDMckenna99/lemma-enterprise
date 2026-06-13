"""Unit tests for site-credential billing classification and Stripe meter reporting."""

from __future__ import annotations

from datetime import datetime

import pytest

from billing.credential_billing import (
    EVENT_DOUBT_REENTRY,
    EVENT_INITIAL_ISSUANCE,
    EVENT_MAU_RENEWAL,
    classify_billing_event,
    record_credential_billing_event,
)
from tests.wallet_test_helpers import SITE_SIGNING_PUBKEY_B64


@pytest.mark.unit
@pytest.mark.parametrize(
    "issue_mode,had_prior,first_month,current,expected",
    [
        ("site_proof", False, None, "2026-01", EVENT_INITIAL_ISSUANCE),
        ("site_proof", True, "2026-01", "2026-01", None),
        ("site_proof", True, "2026-01", "2026-02", EVENT_MAU_RENEWAL),
        ("fresh_idv", True, "2026-01", "2026-02", EVENT_DOUBT_REENTRY),
        ("fresh_idv", False, None, "2026-01", EVENT_INITIAL_ISSUANCE),
    ],
)
def test_classify_billing_event(issue_mode, had_prior, first_month, current, expected):
    assert classify_billing_event(
        issue_mode=issue_mode,
        had_prior_derived=had_prior,
        first_issuance_month=first_month,
        current_month=current,
    ) == expected


@pytest.mark.unit
def test_record_initial_issuance_reports_meter(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import DerivedCredential

    reported: list[dict] = []

    def _capture(**kwargs):
        reported.append(kwargs)
        return True

    monkeypatch.setattr("billing.credential_billing.report_meter_event", _capture)
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
        ppid="did:lemma:ppid_new_user",
        credential_id="ishuman_site_new_001",
        issue_mode="site_proof",
        is_cached_reissue=False,
        month="2026-03",
    )

    assert result.event_type == EVENT_INITIAL_ISSUANCE
    assert result.unit_amount_cents == 35
    assert result.reported_to_stripe is True
    assert len(reported) == 1
    assert reported[0]["event_type"] == EVENT_INITIAL_ISSUANCE
    assert reported[0]["stripe_customer_id"] == "cus_test_123"


@pytest.mark.unit
def test_record_mau_requires_redis_dedup(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import DerivedCredential

    store = fake_ishuman_db_session_factory.store
    store.data[DerivedCredential.__name__].append(
        DerivedCredential(
            master_credential_id="ishuman_master_001",
            derived_credential_id="ishuman_site_existing_001",
            wallet_id="wallet_test_001",
            target_site="example.com",
            derived_ppid="did:lemma:ppid_returning",
            created_at=datetime(2026, 1, 15),
            is_active=True,
        )
    )

    reported: list[dict] = []

    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: reported.append(kwargs) or True,
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_stripe_customer_id_for_site",
        lambda _db, _site: "cus_test_123",
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_billing_site_key",
        lambda _db, _site: "site_example",
    )
    monkeypatch.setattr("billing.credential_billing.track_site_proof_mau", lambda *_a, **_k: True)

    db = fake_ishuman_db_session_factory.session_local()
    result = record_credential_billing_event(
        db,
        target_site="example.com",
        ppid="did:lemma:ppid_returning",
        credential_id="ishuman_site_existing_001",
        issue_mode="site_proof",
        is_cached_reissue=True,
        month="2026-02",
    )

    assert result.event_type == EVENT_MAU_RENEWAL
    assert result.unit_amount_cents == 1
    assert len(reported) == 1


@pytest.mark.unit
def test_record_mau_skipped_when_already_counted(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import DerivedCredential

    store = fake_ishuman_db_session_factory.store
    store.data[DerivedCredential.__name__].append(
        DerivedCredential(
            master_credential_id="ishuman_master_001",
            derived_credential_id="ishuman_site_existing_001",
            wallet_id="wallet_test_001",
            target_site="example.com",
            derived_ppid="did:lemma:ppid_returning",
            created_at=datetime(2026, 1, 15),
            is_active=True,
        )
    )

    reported: list[dict] = []
    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: reported.append(kwargs) or True,
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_stripe_customer_id_for_site",
        lambda _db, _site: "cus_test_123",
    )
    monkeypatch.setattr(
        "billing.credential_billing.resolve_billing_site_key",
        lambda _db, _site: "site_example",
    )
    monkeypatch.setattr("billing.credential_billing.track_site_proof_mau", lambda *_a, **_k: False)

    db = fake_ishuman_db_session_factory.session_local()
    result = record_credential_billing_event(
        db,
        target_site="example.com",
        ppid="did:lemma:ppid_returning",
        credential_id="ishuman_site_existing_001",
        issue_mode="site_proof",
        is_cached_reissue=True,
        month="2026-02",
    )

    assert result.event_type is None
    assert reported == []


@pytest.mark.unit
def test_record_doubt_reentry_after_block(monkeypatch, fake_ishuman_db_session_factory):
    from api.database import DerivedCredential

    store = fake_ishuman_db_session_factory.store
    store.data[DerivedCredential.__name__].append(
        DerivedCredential(
            master_credential_id="ishuman_master_001",
            derived_credential_id="ishuman_site_old_001",
            wallet_id="wallet_test_001",
            target_site="example.com",
            derived_ppid="did:lemma:ppid_blocked",
            created_at=datetime(2026, 1, 10),
            is_active=False,
        )
    )

    reported: list[dict] = []
    monkeypatch.setattr(
        "billing.credential_billing.report_meter_event",
        lambda **kwargs: reported.append(kwargs) or True,
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
        ppid="did:lemma:ppid_blocked",
        credential_id="ishuman_site_fresh_002",
        issue_mode="fresh_idv",
        is_cached_reissue=False,
        month="2026-02",
    )

    assert result.event_type == EVENT_DOUBT_REENTRY
    assert result.unit_amount_cents == 35
    assert reported[0]["event_type"] == EVENT_DOUBT_REENTRY


@pytest.mark.unit
def test_stripe_meter_reporter_dry_run_without_key(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LEMMA_STRIPE_METER_REPORTING", "1")

    from billing.stripe_meter_reporter import report_meter_event

    ok = report_meter_event(
        event_type="initial_issuance",
        stripe_customer_id="cus_test",
        site_id="site_abc",
        ppid_hash="abc123",
        month="2026-02",
        credential_id="ishuman_cred_001",
    )
    assert ok is True


@pytest.mark.unit
def test_derive_site_proof_records_initial_issuance(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    billed: list[dict] = []

    def _capture(db, **kwargs):
        billed.append(kwargs)

    factory = fake_ishuman_db_session_factory
    factory.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_verified_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", factory.session_local)
    monkeypatch.setattr("api.ishuman._bill_site_credential_event", _capture)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_phase12",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_site_phase12_001",
            "subject": ppid,
            "wallet_id": wallet_id,
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "issuer": "did:lemma:test",
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
                "issue_mode": "site_proof",
            },
            ["target_site", "site_signing_pubkey"],
        ),
    )

    assert resp.status_code == 200, resp.get_json()
    assert len(billed) == 1
    assert billed[0]["issue_mode"] == "site_proof"
    assert billed[0]["is_cached_reissue"] is False
    assert billed[0]["credential_id"] == "ishuman_site_phase12_001"
