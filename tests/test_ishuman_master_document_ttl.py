"""Master isHuman credential TTL binds to IDV document expiration when present."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from api.identity_roots import (
    document_expiration_end_of_day_utc,
    normalize_document_expiration_date,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2031-06-02", "2031-06-02"),
        ({"year": 2031, "month": 6, "day": 2}, "2031-06-02"),
        ("", None),
        ("bad", None),
        (None, None),
    ],
)
def test_normalize_document_expiration_date(raw, expected):
    assert normalize_document_expiration_date(raw) == expected


@pytest.mark.unit
def test_document_expiration_end_of_day_utc():
    end = document_expiration_end_of_day_utc("2031-06-02")
    assert end == datetime(2031, 6, 2, 23, 59, 59)


@pytest.mark.unit
def test_master_ttl_uses_document_expiration(monkeypatch):
    monkeypatch.delenv("ISHUMAN_CREDENTIAL_TTL_DAYS", raising=False)

    from importlib import reload
    import api.ishuman as ishuman

    reload(ishuman)

    issued = datetime(2026, 1, 15, 12, 0, 0)
    ttl = ishuman._master_credential_ttl_seconds("2031-06-02", issued_at=issued)
    expected = int(
        (ishuman._master_expires_at_datetime(issued, "2031-06-02") - issued).total_seconds()
    )
    assert ttl == expected
    assert ttl > ishuman.ISHUMAN_CREDENTIAL_TTL_DAYS * 86400


@pytest.mark.unit
def test_master_ttl_falls_back_to_policy_when_expiration_missing(monkeypatch):
    monkeypatch.setenv("ISHUMAN_CREDENTIAL_TTL_DAYS", "365")

    from importlib import reload
    import api.ishuman as ishuman

    reload(ishuman)

    assert ishuman._master_credential_ttl_seconds(None) == 365 * 86400


@pytest.mark.unit
def test_master_ttl_falls_back_to_policy_when_expiration_before_issue(monkeypatch):
    monkeypatch.setenv("ISHUMAN_CREDENTIAL_TTL_DAYS", "365")

    from importlib import reload
    import api.ishuman as ishuman

    reload(ishuman)

    issued = datetime(2026, 6, 15, 12, 0, 0)
    ttl = ishuman._master_credential_ttl_seconds("2020-01-01", issued_at=issued)
    assert ttl == 365 * 86400


@pytest.mark.unit
def test_issue_master_credential_honors_document_expiration(monkeypatch):
    monkeypatch.setenv("ISHUMAN_CREDENTIAL_TTL_DAYS", "365")

    class FakeIssuer:
        def issue_credential(self, subject, claims):
            return '{"issuer":"did:lemma:test","subject":"%s","claims":{}}' % subject

        def get_did(self):
            return "did:lemma:test"

        def get_public_key_hex(self):
            return "aa" * 32

        signing_key_bytes = lambda self: b"\x01" * 32

    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: FakeIssuer())
    monkeypatch.setattr(
        "api.ishuman._sign_with_issuer_for_browser",
        lambda credential, issuer: "bb" * 64,
    )

    from api.ishuman import _issue_ishuman_credential, _master_credential_ttl_seconds

    issued = datetime.utcnow()
    doc_exp = (issued + timedelta(days=120)).strftime("%Y-%m-%d")
    ttl = _master_credential_ttl_seconds(doc_exp, issued_at=issued)

    before = int(time.time())
    cred = _issue_ishuman_credential(
        "did:lemma:ppid_doc_ttl",
        wallet_id="wallet_doc_ttl",
        ttl_seconds=ttl,
    )
    after = int(time.time())

    expires_at = int(cred["claims"]["expiresAt"])
    assert before + ttl <= expires_at <= after + ttl + 1


@pytest.mark.unit
def test_apply_master_expiry_to_record_sets_expires_at_only():
    from api.ishuman import _apply_master_expiry_to_record

    class Record:
        metadata_json = {"pending": True}
        expires_at = None

    record = Record()
    _apply_master_expiry_to_record(record, "2030-12-31")

    assert "document_expiration_date" not in record.metadata_json
    assert record.metadata_json["pending"] is True
    assert record.expires_at == datetime(2030, 12, 31, 23, 59, 59)
