"""Security invariants for the privacy-minimized isHuman cutover."""

from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

import pytest


@pytest.mark.unit
def test_site_billing_subject_storage_has_no_identity_graph_columns():
    from api.database import Base, IsHumanSiteBillingSubject, IsHumanSiteMonthlyUsage

    forbidden = {
        "wallet_id", "person_id", "lemma_person_id", "master_credential_id",
        "ppid", "derived_ppid", "credential_id", "derived_credential_id",
    }
    for model in (IsHumanSiteBillingSubject, IsHumanSiteMonthlyUsage):
        assert forbidden.isdisjoint(model.__table__.columns.keys())
    assert "derived_credentials" not in Base.metadata.tables
    assert "ppid_migration_issued" not in Base.metadata.tables
    assert "person_merges" not in Base.metadata.tables


@pytest.mark.unit
def test_ppid_migration_api_is_absent(ishuman_client):
    response = ishuman_client.post(
        "/api/ishuman/confirm-ppid-migration",
        json={"legacy_ppid": "old", "current_ppid": "new"},
    )
    assert response.status_code == 404


@pytest.mark.unit
def test_person_root_kms_context_is_opaque_and_round_trips(monkeypatch):
    import api.person_root_crypto as crypto

    monkeypatch.setenv("LEMMA_COLUMN_ENCRYPTION_KEY", "context-key-" + "x" * 32)
    monkeypatch.setenv("ENVIRONMENT", "production")
    calls = []

    class FakeKms:
        def is_enabled(self):
            return True

        def encrypt_identity_secret(self, secret, **context):
            calls.append(("encrypt", context))
            return secret.hex(), "test-key"

        def decrypt_identity_secret(self, ciphertext, **context):
            calls.append(("decrypt", context))
            return bytes.fromhex(ciphertext)

    monkeypatch.setattr("api.kms_manager.get_kms_manager", lambda: FakeKms())
    person_id = "person_private_123"
    root = "ab" * 32
    encrypted = crypto.encrypt_person_root(person_id, root)

    assert encrypted.startswith("kms1:")
    assert crypto.decrypt_person_root(person_id, encrypted) == root
    for _, context in calls:
        assert context["key_type"] == "ishuman_person_root"
        assert context["purpose"] == "ppid_derivation"
        assert context["version"] == "1"
        assert person_id not in context.values()
        assert len(context["context_id"]) == 64


@pytest.mark.unit
def test_production_rejects_legacy_person_root(monkeypatch):
    from api.person_root_crypto import decrypt_person_root

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="not KMS encrypted"):
        decrypt_person_root("person_legacy", "ab" * 32)


@pytest.mark.unit
def test_stripe_meter_payload_contains_only_aggregate_safe_fields(monkeypatch):
    import billing.stripe_meter_reporter as reporter

    captured = []

    class MeterEvent:
        @staticmethod
        def create(**kwargs):
            captured.append(kwargs)

    fake_stripe = SimpleNamespace(
        api_key=None,
        billing=SimpleNamespace(MeterEvent=MeterEvent),
    )
    monkeypatch.setattr(reporter, "_stripe", fake_stripe)
    monkeypatch.setattr(reporter, "_stripe_available", True)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_private")
    monkeypatch.setenv("LEMMA_STRIPE_METER_REPORTING", "1")

    assert reporter.report_meter_event(
        event_type="mau_renewal",
        stripe_customer_id="cus_test",
        site_id="site_test",
        month="2026-06",
        event_id="bevt_random",
        unit_count=1,
    ).reported is True
    payload = captured[0]["payload"]
    assert set(payload) == {
        "stripe_customer_id", "value", "site_id", "month", "event_type",
    }
    serialized = repr(captured[0]).lower()
    for forbidden in ("ppid", "wallet_id", "person_id", "master_id", "credential_id"):
        assert forbidden not in serialized


@pytest.mark.unit
def test_check_cannot_query_another_site(
    ishuman_client, monkeypatch,
):
    site = SimpleNamespace(site_id="site_owned", admin_email="admin@example.com")
    monkeypatch.setattr("api.ishuman._require_site_api_key", lambda: site)
    response = ishuman_client.get(
        "/api/ishuman/check?ppid=did:lemma:ppid_x&site_id=site_other",
        headers={"X-API-Key": "test"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "site_id_mismatch"


@pytest.mark.unit
def test_site_doubt_lifecycle_is_separate_from_block(
    ishuman_client, fake_ishuman_db_session_factory, monkeypatch,
):
    from api.database import SiteBlock, SiteDoubt

    factory = fake_ishuman_db_session_factory
    site = SimpleNamespace(site_id="site_owned", admin_email="admin@example.com")
    monkeypatch.setattr("api.ishuman._require_site_api_key", lambda: site)
    monkeypatch.setattr("api.database.SessionLocal", factory.session_local)
    monkeypatch.setattr("api.rate_limiter.check_rate_limit", lambda *args, **kwargs: True)
    ppid = "did:lemma:ppid_doubt"

    created = ishuman_client.post(
        "/api/ishuman/site-doubt",
        json={"ppid": ppid, "reason": "suspicious automation"},
    )
    assert created.status_code == 200
    assert created.get_json()["doubt_required"] is True
    assert len(factory.store.data[SiteDoubt.__name__]) == 1
    assert factory.store.data[SiteBlock.__name__] == []

    checked = ishuman_client.get(
        f"/api/ishuman/check?ppid={ppid}", headers={"X-API-Key": "test"},
    )
    assert checked.status_code == 200
    assert checked.get_json()["blocked"] is False
    assert checked.get_json()["doubt_required"] is True

    listed = ishuman_client.get("/api/ishuman/site-doubts")
    assert listed.status_code == 200
    assert listed.get_json()["count"] == 1

    cleared = ishuman_client.post(
        "/api/ishuman/site-doubt-clear", json={"ppid": ppid},
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["doubt_required"] is False
    assert factory.store.data[SiteDoubt.__name__][0].is_active is False


@pytest.mark.unit
def test_fresh_idv_site_marker_is_single_use(
    ishuman_client, fake_ishuman_db_session_factory, make_ishuman_verification,
    attach_wallet_assertion, monkeypatch,
):
    from tests.wallet_test_helpers import SITE_SIGNING_PUBKEY_B64

    factory = fake_ishuman_db_session_factory
    master = make_ishuman_verification(
        credential_id="ishuman_master_fresh",
        wallet_id="wallet_test_001",
        status="verified",
        verified_at=datetime.utcnow(),
        metadata_json={
            "fresh_idv_site": "example.com",
            "fresh_idv_consumed": False,
        },
    )
    factory.store.data["IsHumanVerification"].append(master)
    monkeypatch.setattr("api.database.SessionLocal", factory.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **kwargs: "did:lemma:ppid_fresh",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, **kwargs: {
            "id": "ishuman_site_rotated", "subject": ppid,
            "claims": {"isHuman": True, "siteId": "example.com"},
        },
    )
    monkeypatch.setattr("api.ishuman._bill_site_credential_event", lambda *args, **kwargs: None)

    body = {
        "master_credential_id": "ishuman_master_fresh",
        "wallet_id": "wallet_test_001",
        "target_site": "example.com",
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
        "issue_mode": "fresh_idv",
    }
    first = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            body, ["master_credential_id", "target_site", "site_signing_pubkey", "issue_mode"],
        ),
    )
    assert first.status_code == 200
    assert master.metadata_json["fresh_idv_consumed"] is True

    replay = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            body, ["master_credential_id", "target_site", "site_signing_pubkey", "issue_mode"],
        ),
    )
    assert replay.status_code == 403
    assert replay.get_json()["error"] == "fresh_idv_required"
