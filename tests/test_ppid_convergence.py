"""Tests for signed site-scoped PPID convergence artifacts."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from api.ppid_convergence import (
    CONVERGENCE_SCHEMA,
    build_convergence_canonical_message,
    issue_ppid_convergence_for_site,
    record_person_convergence_event,
    sign_ppid_convergence_artifact,
    verify_ppid_convergence_artifact,
)


@pytest.fixture
def fake_issuer(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    seed = b"\x33" * 32
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk_hex = sk.public_key().public_bytes_raw().hex()
    issuer_did = f"did:lemma:{pk_hex}"

    class _Issuer:
        def signing_key_bytes(self):
            return seed

        def get_did(self):
            return issuer_did

    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: _Issuer())
    return _Issuer(), pk_hex


@pytest.mark.unit
def test_build_convergence_canonical_message_vector():
    artifact = {
        "issuer": "did:lemma:issuer:federated",
        "site_id": "example.com",
        "legacy_ppid": "did:lemma:ppid_legacy0123456789abcdef0123456789abcdef0123456789abcdef01234567",
        "canonical_ppid": "did:lemma:ppid_canon0123456789abcdef0123456789abcdef0123456789abcdef012345678",
        "convergence_id": "conv_test_vector_001",
        "nonce": "nonce_test_001",
        "issued_at_unix": 1700000000,
        "expires_at_unix": 1700003600,
    }
    # Wave 4 binds issuer into the signed bytes (CANONICAL_MESSAGES.md §9).
    message = build_convergence_canonical_message(artifact)
    assert message.decode("utf-8") == "\n".join(
        [
            "lemma:ppid-convergence:v1",
            artifact["issuer"],
            artifact["site_id"],
            artifact["legacy_ppid"],
            artifact["canonical_ppid"],
            artifact["convergence_id"],
            artifact["nonce"],
            "1700000000",
            "1700003600",
        ]
    )


@pytest.mark.unit
def test_sign_and_verify_convergence_artifact(fake_issuer):
    _issuer, pk_hex = fake_issuer
    now = int(time.time())
    unsigned = {
        "schema": CONVERGENCE_SCHEMA,
        "convergence_id": "conv_unit_001",
        "site_id": "example.com",
        "legacy_ppid": "did:lemma:ppid_" + ("a" * 64),
        "canonical_ppid": "did:lemma:ppid_" + ("b" * 64),
        "issued_at_unix": now,
        "expires_at_unix": now + 3600,
        "nonce": "nonce_unit_001",
    }
    signed = sign_ppid_convergence_artifact(unsigned)
    ok, reason = verify_ppid_convergence_artifact(
        signed,
        site_id="example.com",
        canonical_ppid=unsigned["canonical_ppid"],
        trusted_issuer_pubkeys=[pk_hex],
        now_unix=now,
    )
    assert ok is True
    assert reason == "valid"


@pytest.mark.unit
def test_convergence_wrong_site_fails(fake_issuer):
    _issuer, pk_hex = fake_issuer
    now = int(time.time())
    signed = sign_ppid_convergence_artifact(
        {
            "schema": CONVERGENCE_SCHEMA,
            "convergence_id": "conv_wrong_site",
            "site_id": "example.com",
            "legacy_ppid": "did:lemma:ppid_" + ("a" * 64),
            "canonical_ppid": "did:lemma:ppid_" + ("b" * 64),
            "issued_at_unix": now,
            "expires_at_unix": now + 3600,
            "nonce": "nonce_wrong_site",
        }
    )
    ok, reason = verify_ppid_convergence_artifact(
        signed,
        site_id="other.example.com",
        canonical_ppid=signed["canonical_ppid"],
        trusted_issuer_pubkeys=[pk_hex],
        now_unix=now,
    )
    assert ok is False
    assert reason == "convergence_site_mismatch"


@pytest.mark.unit
def test_convergence_expired_fails(fake_issuer):
    _issuer, pk_hex = fake_issuer
    now = int(time.time())
    signed = sign_ppid_convergence_artifact(
        {
            "schema": CONVERGENCE_SCHEMA,
            "convergence_id": "conv_expired",
            "site_id": "example.com",
            "legacy_ppid": "did:lemma:ppid_" + ("a" * 64),
            "canonical_ppid": "did:lemma:ppid_" + ("b" * 64),
            "issued_at_unix": now - 7200,
            "expires_at_unix": now - 3600,
            "nonce": "nonce_expired",
        }
    )
    ok, reason = verify_ppid_convergence_artifact(
        signed,
        site_id="example.com",
        canonical_ppid=signed["canonical_ppid"],
        trusted_issuer_pubkeys=[pk_hex],
        now_unix=now,
    )
    assert ok is False
    assert reason == "convergence_expired"


@pytest.mark.unit
def test_record_person_convergence_event_idempotent(fake_ishuman_db_session_factory):
    db = fake_ishuman_db_session_factory.session_local()
    first = record_person_convergence_event(
        db,
        wallet_id="wallet_conv_001",
        superseded_person_id="person_prov_001",
        canonical_person_id="person_canon_001",
        idv_session_id="sess_001",
    )
    second = record_person_convergence_event(
        db,
        wallet_id="wallet_conv_001",
        superseded_person_id="person_prov_001",
        canonical_person_id="person_canon_001",
        idv_session_id="sess_002",
    )
    assert first
    assert second == first


@pytest.mark.unit
def test_issue_ppid_convergence_for_site(
    fake_ishuman_db_session_factory,
    fake_issuer,
    monkeypatch,
):
    from api.database import PersonConvergenceEvent, PpidConvergenceIssued

    monkeypatch.setenv("LEMMA_ONE_PPID_ASSURANCE_MODEL", "1")
    monkeypatch.setenv("LEMMA_PPID_CONVERGENCE_ENABLED", "1")

    db = fake_ishuman_db_session_factory.session_local()
    convergence_id = record_person_convergence_event(
        db,
        wallet_id="wallet_issue_001",
        superseded_person_id="person_prov_issue",
        canonical_person_id="person_canon_issue",
    )
    assert convergence_id

    legacy_ppid = "did:lemma:ppid_" + ("c" * 64)
    canonical_ppid = "did:lemma:ppid_" + ("d" * 64)
    monkeypatch.setattr(
        "api.identity_person.load_person_root_bytes",
        lambda _db, _person_id: b"superseded-root-bytes",
    )
    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_person_root",
        lambda _root, _site: legacy_ppid,
    )

    artifact = issue_ppid_convergence_for_site(
        db,
        wallet_id="wallet_issue_001",
        target_site="example.com",
        canonical_ppid=canonical_ppid,
        canonical_person_id="person_canon_issue",
    )
    assert artifact is not None
    assert artifact["schema"] == CONVERGENCE_SCHEMA
    assert artifact["legacy_ppid"] == legacy_ppid
    assert artifact["canonical_ppid"] == canonical_ppid
    assert artifact["convergence_id"] == convergence_id

    event = db.query(PersonConvergenceEvent).filter_by(convergence_id=convergence_id).first()
    assert event.status == "pending"
    issued = db.query(PpidConvergenceIssued).filter_by(
        convergence_id=convergence_id,
        target_site="example.com",
    ).first()
    assert issued is not None
    assert issued.consumed_at is None


@pytest.mark.unit
def test_provisional_rebound_sets_convergence_flags(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import LemmaPerson, LemmaWalletBinding
    from api.identity_person import (
        PERSON_STATUS_PROVISIONAL,
        ensure_provisional_person_for_wallet,
        material_from_test_fixture,
        resolve_or_create_person_from_material,
    )
    from api.ppid import derive_ppid_from_person_root_hash

    monkeypatch.setattr("api.config.use_assigned_person_root", lambda: True)

    db = fake_ishuman_db_session_factory.session_local()
    material = material_from_test_fixture(document_number="CONVERGENCE-FLAG-001")
    anchored = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_anchored_conv",
        provider="didit",
    )
    provisional_id = ensure_provisional_person_for_wallet(
        db,
        wallet_id="wallet_provisional_conv",
    )
    provisional = db.query(LemmaPerson).filter_by(person_id=provisional_id).first()
    assert provisional.status == PERSON_STATUS_PROVISIONAL

    recovered = resolve_or_create_person_from_material(
        db,
        material=material,
        wallet_id="wallet_provisional_conv",
        provider="didit",
    )

    assert recovered.provisional_rebound is True
    assert recovered.superseded_person_id == provisional_id
    assert recovered.person_id == anchored.person_id

    from api.identity_person import load_person_root_bytes
    from api.ppid import derive_ppid_from_person_root

    legacy_ppid = derive_ppid_from_person_root(
        load_person_root_bytes(db, provisional_id),
        "example.com",
    )
    canonical_ppid = derive_ppid_from_person_root_hash(
        recovered.person_root_hash,
        "example.com",
    )
    assert legacy_ppid != canonical_ppid

    binding = db.query(LemmaWalletBinding).filter_by(wallet_id="wallet_provisional_conv").first()
    assert binding.lemma_person_id == anchored.person_id
