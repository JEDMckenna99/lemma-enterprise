"""Silent mobile wallet handoff during Didit IDV return."""

from __future__ import annotations

import hashlib

import pytest

HANDOFF_ID = "handoff_" + "b" * 24
SESSION_ID = "ishuman_sess_test_handoff_001"
WALLET_ID = "wallet_handoff_001"
WALLET_SECRET = "ab" * 32
MK = "cd" * 16
MK_FINGERPRINT = hashlib.sha256(MK.encode("utf-8")).hexdigest()
ENCRYPTED_BLOB = "AQID_encrypted_opaque_blob"


def _store_handoff_entry(
    *,
    handoff_id: str = HANDOFF_ID,
    session_id: str = SESSION_ID,
    wallet_id: str = WALLET_ID,
    encrypted_blob: str = ENCRYPTED_BLOB,
    mk_fingerprint: str = MK_FINGERPRINT,
):
    from auth.redis_store import store as redis_store

    entry = {
        "handoff_id": handoff_id,
        "wallet_id": wallet_id,
        "session_id": session_id,
        "encrypted_blob": encrypted_blob,
        "mk_fingerprint": mk_fingerprint,
    }
    redis_store(f"ishuman:idv-handoff:{handoff_id}", entry, ttl_seconds=300)
    redis_store(f"ishuman:idv-handoff-session:{session_id}", entry, ttl_seconds=300)


def _seed_verification_row(
    fake_ishuman_db_session_factory,
    *,
    session_id: str = SESSION_ID,
    wallet_id: str = WALLET_ID,
    status: str = "pending",
):
    from api.database import IsHumanVerification
    from datetime import datetime

    fake_ishuman_db_session_factory.store.data[IsHumanVerification.__name__].append(
        IsHumanVerification(
            session_id=session_id,
            stripe_session_id=f"vs_{session_id[-8:]}",
            wallet_id=wallet_id,
            status=status,
            created_at=datetime.utcnow(),
        )
    )


def _claim_body(**overrides):
    body = {
        "handoff_id": HANDOFF_ID,
        "session_id": SESSION_ID,
        "mk": MK,
    }
    body.update(overrides)
    return body


@pytest.mark.integration
def test_deposit_then_claim_round_trips_handoff(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _seed_verification_row(db)

    deposit_body = attach_wallet_assertion(
        {
            "wallet_id": WALLET_ID,
            "wallet_secret": WALLET_SECRET,
            "handoff_id": HANDOFF_ID,
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
            "handoff_mk_fingerprint": MK_FINGERPRINT,
        },
        ["handoff_id", "session_id", "handoff_mk_fingerprint"],
    )
    deposit = ishuman_client.post("/api/ishuman/idv-mobile-handoff/deposit", json=deposit_body)
    assert deposit.status_code == 200, deposit.get_json()
    assert deposit.get_json()["expires_in"] == 300

    claim = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(),
    )
    payload = claim.get_json()
    assert claim.status_code == 200, payload
    assert payload["wallet_id"] == WALLET_ID
    assert payload["session_id"] == SESSION_ID
    assert payload["encrypted_blob"] == ENCRYPTED_BLOB

    again = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(),
    )
    assert again.status_code == 404
    assert again.get_json()["error"] == "handoff_not_found"


@pytest.mark.integration
def test_claim_without_mk_returns_400(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"handoff_id": HANDOFF_ID, "session_id": SESSION_ID},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "handoff_id_session_id_mk_required"


@pytest.mark.integration
def test_claim_with_wrong_mk_does_not_burn_handoff(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    handoff_id = "handoff_" + "e" * 24
    session_id = "ishuman_sess_wrong_mk"
    _seed_verification_row(db, session_id=session_id)
    _store_handoff_entry(handoff_id=handoff_id, session_id=session_id)

    wrong = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(handoff_id=handoff_id, session_id=session_id, mk="00" * 16),
    )
    assert wrong.status_code == 403
    assert wrong.get_json()["error"] == "handoff_mk_mismatch"

    ok = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(handoff_id=handoff_id, session_id=session_id),
    )
    assert ok.status_code == 200, ok.get_json()


@pytest.mark.integration
def test_claim_with_stale_client_session_uses_stored_handoff_session(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    handoff_id = "handoff_" + "s" * 24
    stored_session_id = "ishuman_sess_stored_handoff"
    stale_session_id = "ishuman_sess_stale_phone"
    _seed_verification_row(db, session_id=stored_session_id)
    _store_handoff_entry(handoff_id=handoff_id, session_id=stored_session_id)

    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(handoff_id=handoff_id, session_id=stale_session_id),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["session_id"] == stored_session_id
    assert payload["wallet_id"] == WALLET_ID


@pytest.mark.integration
def test_claim_with_session_id_only_returns_400(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={"session_id": SESSION_ID, "mk": MK},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "handoff_id_session_id_mk_required"


@pytest.mark.integration
def test_claim_after_wrong_mk_lockout_returns_429(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    handoff_id = "handoff_" + "f" * 24
    session_id = "ishuman_sess_mk_lockout"
    _seed_verification_row(db, session_id=session_id)
    _store_handoff_entry(handoff_id=handoff_id, session_id=session_id)

    for _ in range(5):
        resp = ishuman_client.post(
            "/api/ishuman/idv-mobile-handoff/claim",
            json=_claim_body(handoff_id=handoff_id, session_id=session_id, mk="00" * 16),
        )
        assert resp.status_code == 403

    locked = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(handoff_id=handoff_id, session_id=session_id),
    )
    assert locked.status_code == 429
    assert locked.get_json()["error"] == "handoff_claim_rate_limited"


@pytest.mark.integration
def test_claim_when_verification_wallet_mismatch_returns_403(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    handoff_id = "handoff_" + "g" * 24
    session_id = "ishuman_sess_wallet_mismatch"
    _seed_verification_row(db, session_id=session_id, wallet_id="wallet_other")
    _store_handoff_entry(handoff_id=handoff_id, session_id=session_id)

    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json=_claim_body(handoff_id=handoff_id, session_id=session_id),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "handoff_session_invalid"


@pytest.mark.integration
def test_deposit_requires_wallet_assertion(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/deposit",
        json={
            "wallet_id": "wallet_handoff_002",
            "handoff_id": HANDOFF_ID,
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
            "handoff_mk_fingerprint": MK_FINGERPRINT,
        },
    )
    payload = resp.get_json()
    assert resp.status_code == 403, payload
    assert payload["error"].startswith("wallet_assertion")


@pytest.mark.integration
def test_deposit_missing_fields_returns_400(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/deposit",
        json={"wallet_id": "wallet_handoff_003"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_handoff_fields"


@pytest.mark.integration
def test_deposit_missing_mk_fingerprint_returns_400(
    ishuman_client,
    attach_wallet_assertion,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    deposit_body = attach_wallet_assertion(
        {
            "wallet_id": WALLET_ID,
            "wallet_secret": WALLET_SECRET,
            "handoff_id": HANDOFF_ID,
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
        },
        ["handoff_id", "session_id"],
    )
    resp = ishuman_client.post("/api/ishuman/idv-mobile-handoff/deposit", json=deposit_body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_handoff_mk_fingerprint"


@pytest.mark.integration
def test_claim_unknown_handoff_returns_404(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={
            "handoff_id": "handoff_" + "z" * 24,
            "session_id": SESSION_ID,
            "mk": MK,
        },
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "handoff_not_found"


@pytest.mark.integration
def test_start_verification_requires_handoff_mk_fingerprint(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.create_identity_verification_session",
        lambda self, user_id, return_url: {
            "success": True,
            "session_id": "didit_sess_handoff",
            "url": "https://verification.didit.me/session/handoff",
        },
    )

    return_url = "https://lemma.id/wallet/ishuman-idv?verification_return=true&handoff_id=" + HANDOFF_ID
    body = attach_wallet_assertion(
        {
            "wallet_id": "wallet_handoff_start_001",
            "wallet_secret": WALLET_SECRET,
            "return_url": return_url,
            "provider": "didit",
            "handoff_id": HANDOFF_ID,
        },
        ["return_url", "handoff_id"],
    )
    resp = ishuman_client.post("/api/ishuman/start-verification", json=body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_handoff_mk_fingerprint"


@pytest.mark.integration
def test_start_verification_stores_mobile_handoff_via_deposit(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification

    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.create_identity_verification_session",
        lambda self, user_id, return_url: {
            "success": True,
            "session_id": "didit_sess_handoff",
            "url": "https://verification.didit.me/session/handoff",
        },
    )
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_handoff_start",
    )

    handoff_id = "handoff_" + "h" * 24
    return_url = "https://lemma.id/wallet/ishuman-idv?verification_return=true&handoff_id=" + handoff_id
    body = attach_wallet_assertion(
        {
            "wallet_id": "wallet_handoff_start_001",
            "wallet_secret": WALLET_SECRET,
            "return_url": return_url,
            "provider": "didit",
            "handoff_id": handoff_id,
            "handoff_mk_fingerprint": MK_FINGERPRINT,
            "encrypted_blob": ENCRYPTED_BLOB,
        },
        ["return_url", "handoff_id", "handoff_mk_fingerprint"],
    )
    resp = ishuman_client.post("/api/ishuman/start-verification", json=body)
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["handoff_stored"] is True
    assert payload["handoff_expires_in"] == 300

    claim = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={
            "handoff_id": handoff_id,
            "session_id": payload["session_id"],
            "mk": MK,
        },
    )
    claim_payload = claim.get_json()
    assert claim.status_code == 200, claim_payload
    assert claim_payload["session_id"] == payload["session_id"]
    assert claim_payload["encrypted_blob"] == ENCRYPTED_BLOB

    rows = db.store.data[IsHumanVerification.__name__]
    assert any(row.session_id == payload["session_id"] for row in rows)


@pytest.mark.integration
def test_claim_rate_limit_exceeded(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _seed_verification_row(db, session_id="ishuman_sess_rate_limit")
    _store_handoff_entry(handoff_id="handoff_" + "c" * 24, session_id="ishuman_sess_rate_limit")

    monkeypatch.setattr(
        "api.rate_limiter.check_rate_limit",
        lambda key, max_requests, window_seconds: False,
    )

    resp = ishuman_client.post(
        "/api/ishuman/idv-mobile-handoff/claim",
        json={
            "handoff_id": "handoff_" + "c" * 24,
            "session_id": "ishuman_sess_rate_limit",
            "mk": MK,
        },
    )
    assert resp.status_code == 429
    assert resp.get_json()["error"] == "handoff_claim_rate_limited"


@pytest.mark.integration
def test_deposit_weak_handoff_id_rejected(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    deposit_body = attach_wallet_assertion(
        {
            "wallet_id": "wallet_handoff_004",
            "wallet_secret": WALLET_SECRET,
            "handoff_id": "short",
            "session_id": SESSION_ID,
            "encrypted_blob": ENCRYPTED_BLOB,
            "handoff_mk_fingerprint": MK_FINGERPRINT,
        },
        ["handoff_id", "session_id", "handoff_mk_fingerprint"],
    )
    resp = ishuman_client.post("/api/ishuman/idv-mobile-handoff/deposit", json=deposit_body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "weak_handoff_id"
