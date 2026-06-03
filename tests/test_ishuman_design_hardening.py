"""Tests for the lemma.id design-hardening fixes.

Covers:
  * PPID convergence guard (_derive_ppid_for_site fail-closed)
  * config flags (ppid_require_person_root, is_ishuman_pull_fallback_enabled)
  * DiditManager.retrieve_session_decision (pull fallback transport)
  * _maybe_pull_issue_didit orchestration (webhook-independent issuance)
  * /api/ishuman/erase input validation
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# PPID convergence guard
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_derive_ppid_fails_closed_by_default():
    """With the default (person-root required), an authoritative derivation that
    has no person root must refuse the legacy wallet-secret path."""
    from api.ishuman import _derive_ppid_for_site

    with pytest.raises(ValueError, match="person-root PPID required"):
        _derive_ppid_for_site(rp_id="example.com", wallet_secret="ab" * 32)


@pytest.mark.unit
def test_derive_ppid_provisional_allows_legacy_pre_idv():
    """Provisional (pre-IDV) callers may still use the wallet-secret path since
    no person root exists yet."""
    from api.ishuman import _derive_ppid_for_site

    ppid = _derive_ppid_for_site(
        rp_id="example.com", wallet_secret="ab" * 32, provisional=True
    )
    assert ppid.startswith("did:lemma:ppid_")


@pytest.mark.unit
def test_derive_ppid_legacy_allowed_when_flag_disabled(monkeypatch):
    monkeypatch.setenv("LEMMA_PPID_REQUIRE_PERSON_ROOT", "0")
    from api.ishuman import _derive_ppid_for_site

    ppid = _derive_ppid_for_site(rp_id="example.com", wallet_secret="ab" * 32)
    assert ppid.startswith("did:lemma:ppid_")


@pytest.mark.unit
def test_derive_ppid_resolves_person_root_from_wallet_binding(monkeypatch):
    """A verified wallet derives via person-root even when the caller passes only
    wallet_id (no explicit lemma_person_id) -- resolved through the binding."""
    from types import SimpleNamespace

    import api.ishuman as ish

    monkeypatch.setattr(
        ish, "_resolve_person_id_for_wallet", lambda db, wallet_id: "person_xyz"
    )
    monkeypatch.setattr(
        "api.identity_person.load_person_root_bytes",
        lambda db, pid: bytes.fromhex("cd" * 32),
    )

    db = SimpleNamespace()
    ppid = ish._derive_ppid_for_site(rp_id="example.com", wallet_id="wallet_1", db=db)
    assert ppid.startswith("did:lemma:ppid_")
    # Must match the canonical person-root derivation, not a wallet-secret one.
    from api.ppid import derive_ppid_from_person_root

    assert ppid == derive_ppid_from_person_root(bytes.fromhex("cd" * 32), "example.com")


@pytest.mark.unit
def test_derive_ppid_missing_inputs_raises():
    from api.ishuman import _derive_ppid_for_site

    with pytest.raises(ValueError):
        _derive_ppid_for_site(rp_id="example.com")


# ---------------------------------------------------------------------------
# Config flags
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_ppid_require_person_root_flag(monkeypatch):
    import api.config as config

    monkeypatch.delenv("LEMMA_PPID_REQUIRE_PERSON_ROOT", raising=False)
    assert config.ppid_require_person_root() is True
    monkeypatch.setenv("LEMMA_PPID_REQUIRE_PERSON_ROOT", "0")
    assert config.ppid_require_person_root() is False


@pytest.mark.unit
def test_pull_fallback_disabled_when_didit_disabled(monkeypatch):
    import api.config as config

    # Didit is not configured in the test env, so the rail is disabled and the
    # pull fallback must be inert regardless of its own flag.
    monkeypatch.setenv("LEMMA_ISHUMAN_PULL_FALLBACK", "1")
    assert config.is_ishuman_pull_fallback_enabled() is False


# ---------------------------------------------------------------------------
# DiditManager.retrieve_session_decision
# ---------------------------------------------------------------------------

def _make_didit_manager():
    from billing.didit_manager import DiditManager

    mgr = DiditManager.__new__(DiditManager)  # bypass config-reading __init__
    mgr.api_base = "https://verification.didit.me"
    mgr.api_key = "test-key"
    mgr.enabled = True
    return mgr


@pytest.mark.unit
def test_retrieve_session_decision_approved(monkeypatch):
    import billing.didit_manager as dm

    class _Resp:
        status_code = 200
        content = b"{}"

        @staticmethod
        def json():
            return {"status": "Approved", "id_verifications": [{"status": "Approved"}]}

    monkeypatch.setattr(dm.requests, "get", lambda *a, **k: _Resp())
    result = _make_didit_manager().retrieve_session_decision("sess_1")
    assert result["success"] is True
    assert result["status"] == "approved"
    assert result["decision"]["id_verifications"]


@pytest.mark.unit
def test_retrieve_session_decision_non_200(monkeypatch):
    import billing.didit_manager as dm

    class _Resp:
        status_code = 404
        content = b""
        text = "not found"

    monkeypatch.setattr(dm.requests, "get", lambda *a, **k: _Resp())
    result = _make_didit_manager().retrieve_session_decision("sess_1")
    assert result["success"] is False


@pytest.mark.unit
def test_retrieve_session_decision_requires_enabled():
    from billing.didit_manager import DiditManager

    mgr = DiditManager.__new__(DiditManager)
    mgr.enabled = False
    result = mgr.retrieve_session_decision("sess_1")
    assert result["success"] is False


# ---------------------------------------------------------------------------
# _maybe_pull_issue_didit orchestration
# ---------------------------------------------------------------------------

class _FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.unit
def test_pull_issue_short_circuits_when_already_verified():
    import api.ishuman as ish

    record = SimpleNamespace(status="verified", credential_id="cred_1")
    assert ish._maybe_pull_issue_didit(_FakeDb(), record) is True


@pytest.mark.unit
def test_pull_issue_issues_on_approved_decision(monkeypatch):
    import api.ishuman as ish
    import api.config as config

    monkeypatch.setattr(config, "is_ishuman_pull_fallback_enabled", lambda: True)

    class _Mgr:
        def retrieve_session_decision(self, _sid):
            return {"success": True, "status": "approved", "decision": {"ok": 1}}

    import billing.didit_manager as dm
    monkeypatch.setattr(dm, "DiditManager", _Mgr)

    monkeypatch.setattr(
        ish, "_complete_verified_ishuman_from_didit",
        lambda db, record, *, wallet_id, decision: {
            "id": "ishuman_master_pulled",
            "issuerInfo": {"did": "did:lemma:issuer"},
        },
    )

    record = SimpleNamespace(
        status="pending",
        credential_id=None,
        issuer_id="didit",
        provider_session_id="sess_1",
        wallet_id="wallet_1",
        metadata_json={},
    )
    db = _FakeDb()
    assert ish._maybe_pull_issue_didit(db, record) is True
    assert record.status == "verified"
    assert record.credential_id == "ishuman_master_pulled"
    assert record.metadata_json["issued_via"] == "pull_fallback"
    assert db.commits == 1


@pytest.mark.unit
def test_pull_issue_noop_when_decision_not_approved(monkeypatch):
    import api.ishuman as ish
    import api.config as config

    monkeypatch.setattr(config, "is_ishuman_pull_fallback_enabled", lambda: True)

    class _Mgr:
        def retrieve_session_decision(self, _sid):
            return {"success": True, "status": "in_progress", "decision": {}}

    import billing.didit_manager as dm
    monkeypatch.setattr(dm, "DiditManager", _Mgr)

    record = SimpleNamespace(
        status="pending",
        credential_id=None,
        issuer_id="didit",
        provider_session_id="sess_1",
        wallet_id="wallet_1",
        metadata_json={},
    )
    assert ish._maybe_pull_issue_didit(_FakeDb(), record) is False
    assert record.status == "pending"


# ---------------------------------------------------------------------------
# Erasure endpoint input validation
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_erase_requires_wallet_id(ishuman_client):
    resp = ishuman_client.post("/api/ishuman/erase", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "wallet_id required"


# ---------------------------------------------------------------------------
# Cross-device amnesty (gap #1): site blocks lift for the re-verifying PERSON,
# not just the single wallet that completes the re-IDV.
# ---------------------------------------------------------------------------

@pytest.fixture
def amnesty_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from api.database import (
        LemmaPerson,
        LemmaWalletBinding,
        DerivedCredential,
        SiteBlock,
        RevocationList,
        IsHumanVerification,
    )

    engine = create_engine("sqlite:///:memory:")
    for model in (
        LemmaPerson,
        LemmaWalletBinding,
        DerivedCredential,
        SiteBlock,
        RevocationList,
        IsHumanVerification,
    ):
        model.__table__.create(bind=engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _seed_blocked_person(db, *, with_binding_for_new=True):
    """A person verified on wallet_old, with a site block on their site PPID.

    wallet_new is a freshly recovered device: it has NO derived credentials of
    its own, only a binding to the same person.
    """
    from api.database import (
        LemmaPerson,
        LemmaWalletBinding,
        DerivedCredential,
        SiteBlock,
        RevocationList,
    )

    blocked_ppid = "did:lemma:ppid_crossdevice"
    db.add(
        LemmaPerson(
            person_id="person_A",
            person_root_hash="ab" * 32,
            root_version="v1",
            status="active",
        )
    )
    db.add(LemmaWalletBinding(wallet_id="wallet_old", lemma_person_id="person_A"))
    if with_binding_for_new:
        db.add(LemmaWalletBinding(wallet_id="wallet_new", lemma_person_id="person_A"))
    db.add(
        DerivedCredential(
            master_credential_id="m_old",
            derived_credential_id="d_old",
            wallet_id="wallet_old",
            target_site="site1.example",
            derived_ppid=blocked_ppid,
            is_active=False,
            revoked_at=datetime.utcnow(),
        )
    )
    db.add(SiteBlock(site_id="site_1", ppid=blocked_ppid, is_active=True))
    db.add(
        RevocationList(
            lemma_id=blocked_ppid,
            credential_id=blocked_ppid,
            ppid=blocked_ppid,
            site_id="site_1",
            lemma_type="ishuman",
            revocation_type="user",
            revoked_by="site",
            reason="abuse",
        )
    )
    db.commit()
    return blocked_ppid


@pytest.mark.integration
def test_amnesty_lifts_site_block_cross_device(amnesty_db):
    """Re-IDV on a brand-new wallet (no derived creds of its own) must lift the
    site block placed against the person's deterministic PPID on a prior device."""
    from api.site_ppid_revocation import clear_amnesty_eligible_wallet_revocations
    from api.database import SiteBlock, RevocationList

    blocked_ppid = _seed_blocked_person(amnesty_db, with_binding_for_new=True)

    summary = clear_amnesty_eligible_wallet_revocations(
        amnesty_db, wallet_id="wallet_new"
    )

    assert summary["person_id"] == "person_A"
    assert summary["person_wallets"] == 2
    assert summary["cleared_site_blocks"] == 1
    block = amnesty_db.query(SiteBlock).filter_by(ppid=blocked_ppid).first()
    assert block is not None and block.is_active is False
    assert (
        amnesty_db.query(RevocationList)
        .filter_by(ppid=blocked_ppid, revocation_type="user")
        .first()
        is None
    )


@pytest.mark.integration
def test_amnesty_without_binding_stays_wallet_scoped(amnesty_db):
    """Control: with no person binding for the new wallet, the prior device's
    block is NOT visible -- demonstrating why the person-scoped resolution is the
    fix rather than incidental behavior."""
    from api.site_ppid_revocation import clear_amnesty_eligible_wallet_revocations
    from api.database import SiteBlock

    blocked_ppid = _seed_blocked_person(amnesty_db, with_binding_for_new=False)

    summary = clear_amnesty_eligible_wallet_revocations(
        amnesty_db, wallet_id="wallet_new"
    )

    assert summary["person_id"] is None
    assert summary["person_wallets"] == 1
    assert summary["cleared_site_blocks"] == 0
    block = amnesty_db.query(SiteBlock).filter_by(ppid=blocked_ppid).first()
    assert block is not None and block.is_active is True
