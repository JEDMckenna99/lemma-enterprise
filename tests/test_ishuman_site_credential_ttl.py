"""Site-bound isHuman credentials use a shorter monthly renewal TTL."""

from __future__ import annotations

import time

import pytest


@pytest.mark.unit
def test_site_credential_default_ttl_is_monthly(monkeypatch):
    monkeypatch.delenv("ISHUMAN_SITE_CREDENTIAL_TTL_DAYS", raising=False)
    monkeypatch.delenv("ISHUMAN_CREDENTIAL_TTL_DAYS", raising=False)

    from importlib import reload
    import api.ishuman as ishuman

    reload(ishuman)

    assert ishuman.ISHUMAN_SITE_CREDENTIAL_TTL_DAYS == 30
    assert ishuman._default_credential_lifetime_seconds("example.com") == 30 * 86400
    assert ishuman._default_credential_lifetime_seconds("lemma.id") == 365 * 86400
    assert ishuman._default_credential_lifetime_seconds(None) == 365 * 86400


@pytest.mark.unit
def test_issue_site_credential_uses_site_ttl(monkeypatch):
    monkeypatch.setenv("ISHUMAN_SITE_CREDENTIAL_TTL_DAYS", "30")
    monkeypatch.setenv("ISHUMAN_CREDENTIAL_TTL_DAYS", "365")

    captured: dict = {}

    class FakeIssuer:
        def issue_credential(self, subject, claims):
            captured["claims"] = claims
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

    from api.ishuman import _issue_ishuman_credential

    before = int(time.time())
    cred = _issue_ishuman_credential(
        "did:lemma:ppid_site_ttl",
        wallet_id="wallet_ttl",
        site_id="example.com",
        ppid_derivation="person_root_v1",
    )
    after = int(time.time())

    expires_at = int(cred["claims"]["expiresAt"])
    expected_min = before + 30 * 86400
    expected_max = after + 30 * 86400
    assert expected_min <= expires_at <= expected_max
    assert cred["claims"]["siteId"] == "example.com"
