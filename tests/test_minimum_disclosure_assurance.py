"""Minimum-disclosure assurance: passkey policy must not leak latent IDV."""

from __future__ import annotations

import pytest

from tests.wallet_test_helpers import (
    DERIVE_ASSERTION_FIELDS,
    SITE_SIGNING_PUBKEY_B64,
)


PASSKEY_DERIVE_ASSERTION_FIELDS = DERIVE_ASSERTION_FIELDS + ["required_assurance"]


@pytest.mark.unit
def test_derive_site_proof_issues_passkey_when_master_exists_and_passkey_requested(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_existing_passkey",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setenv("LEMMA_ONE_PPID_ASSURANCE_MODEL", "1")
    monkeypatch.setenv("LEMMA_PASSKEY_ASSURANCE_ENABLED", "1")
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_passkey",
    )

    issued = []

    def _issue(ppid, wallet_id=None, site_id=None, **kwargs):
        issued.append(kwargs.get("assurance"))
        return {
            "id": "ishuman_site_passkey_tier",
            "subject": ppid,
            "claims": {
                "assurance": kwargs.get("assurance"),
                "isHuman": kwargs.get("assurance") == "ishuman",
                "siteId": site_id,
            },
        }

    monkeypatch.setattr("api.ishuman._issue_ishuman_credential", _issue)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_existing_passkey",
                "wallet_id": "wallet_test_001",
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
                "required_assurance": "passkey",
            },
            PASSKEY_DERIVE_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert issued == ["passkey"]
    assert payload["credential"]["claims"]["assurance"] == "passkey"


@pytest.mark.unit
def test_derive_site_proof_defaults_to_ishuman_with_verified_master(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_existing_default",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_ishuman",
    )

    issued = []

    def _issue(ppid, wallet_id=None, site_id=None, **kwargs):
        issued.append(kwargs.get("assurance"))
        return {
            "id": "ishuman_site_ishuman_tier",
            "subject": ppid,
            "claims": {
                "assurance": kwargs.get("assurance"),
                "isHuman": True,
                "siteId": site_id,
            },
        }

    monkeypatch.setattr("api.ishuman._issue_ishuman_credential", _issue)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_existing_default",
                "wallet_id": "wallet_test_001",
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert issued == ["ishuman"]


@pytest.mark.unit
def test_python_verifier_strict_assurance_match():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
    name = "lemma_proof_verifier_minimum_disclosure"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)

    ctx = mod.VerificationContext
    assert ctx._assurance_meets_policy("passkey", "passkey") is True
    assert ctx._assurance_meets_policy("ishuman", "ishuman") is True
    assert ctx._assurance_meets_policy("ishuman", "passkey") is True
    assert ctx._assurance_meets_policy("passkey", "ishuman") is False

