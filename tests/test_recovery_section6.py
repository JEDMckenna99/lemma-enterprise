"""Section 6: human recovery hardening tests."""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

pytestmark = pytest.mark.unit


@pytest.fixture
def recovery_module(monkeypatch):
    import api.account_recovery as mod

    monkeypatch.setattr(mod, "redis_client", None)
    with mod._recovery_memory_lock:
        mod.recovery_tokens_memory.clear()
    return mod


@pytest.fixture
def recovery_client(recovery_module):
    from api.account_recovery import account_recovery_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "section6-test-secret"
    app.register_blueprint(account_recovery_bp)
    with app.test_client() as client:
        yield client, recovery_module


def _store_token(mod, *, token: str = "recovery-token-1", site_id: str = "example.com", email: str = "admin@example.com"):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    mod.store_recovery_token(
        token_hash,
        {
            "site_id": site_id,
            "admin_email": email,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            "used": False,
        },
    )
    return token


def test_complete_requires_replacement_passkey(recovery_client):
    client, mod = recovery_client
    token = _store_token(mod)

    resp = client.post(
        "/api/recovery/complete",
        json={"token": token, "ppid": "did:lemma:ppid_abc"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "replacement_passkey_required"


def test_complete_requires_ppid(recovery_client):
    client, mod = recovery_client
    token = _store_token(mod)

    resp = client.post(
        "/api/recovery/complete",
        json={"token": token, "passkey_credential_id": "pk-123"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "replacement_ppid_required"


def test_recovery_token_consumed_atomically_before_issuance(recovery_client, monkeypatch):
    client, mod = recovery_client
    token = _store_token(mod)
    issued = {"count": 0}
    lock = threading.Lock()

    def _issue(**_kwargs):
        with lock:
            issued["count"] += 1
        return {"id": "admin_cred_1"}

    class _Site:
        site_domain = "example.com"

    class _Query:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return _Site()

    class _DB:
        def query(self, _model):
            return _Query()

        def close(self):
            return None

    monkeypatch.setattr(mod, "_issue_site_admin_proof", _issue)
    monkeypatch.setattr(mod, "_update_site_admin_ppid", lambda *_a, **_k: True)
    monkeypatch.setattr(mod, "_update_all_admin_sites", lambda *_a, **_k: [])
    monkeypatch.setattr(mod, "_verify_recovery_webauthn_assertion", lambda *_a, **_k: (True, "ok"))
    monkeypatch.setattr("api.database.SessionLocal", lambda: _DB())

    body = {
        "token": token,
        "ppid": "did:lemma:ppid_recovery",
        "passkey_credential_id": "pk-recovery-1",
        "webauthn_credential": {"id": "pk-recovery-1"},
    }
    first = client.post("/api/recovery/complete", json=body)
    second = client.post("/api/recovery/complete", json=body)

    assert first.status_code == 200
    assert first.get_json()["success"] is True
    assert second.status_code == 400
    assert "already used" in second.get_json()["error"].lower()
    assert issued["count"] == 1


def test_complete_wallet_path_disabled(recovery_client):
    client, _mod = recovery_client
    resp = client.post("/api/recovery/complete-wallet", json={"token": "x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "recovery_wallet_path_disabled"


def test_update_site_admin_ppid_refuses_owner_fallback(recovery_module, monkeypatch):
    mod = recovery_module

    class _Admin:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Site:
        admin_email = "owner@example.com"

    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self._rows[0] if self._rows else None

    owner_row = _Admin(site_id="example.com", admin_email="", admin_role="owner", admin_did="did:lemma:ppid_old", is_active=True)

    class _DB:
        def query(self, model):
            if model.__name__ == "SiteAdmin":
                return _Query([owner_row])
            if model.__name__ == "Site":
                return _Query([_Site()])
            return _Query([])

        def add(self, _obj):
            return None

        def commit(self):
            return None

        def close(self):
            return None

    class _SessionLocal:
        def __call__(self):
            return _DB()

    monkeypatch.setattr("api.database.SessionLocal", _SessionLocal())
    monkeypatch.setattr("api.database.SiteAdmin", type("SiteAdmin", (), {"__name__": "SiteAdmin"}))
    monkeypatch.setattr("api.database.Site", type("Site", (), {"__name__": "Site"}))

    ok = mod._update_site_admin_ppid("example.com", "admin@example.com", "did:lemma:ppid_new")
    assert ok is False
    assert owner_row.admin_did == "did:lemma:ppid_old"


def test_lost_device_authorization_requires_idv_purpose(
    wallet_seed,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import IsHumanVerification, LemmaWalletBinding
    from api.wallet_authn import issue_lost_device_recovery_authorization

    wallet_id = wallet_seed["wallet_id"]
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        LemmaWalletBinding(
            wallet_id=wallet_id,
            lemma_person_id="person_recovery",
            binding_status="active",
        )
    )
    db.add(
        IsHumanVerification(
            session_id="idv_wrong_purpose",
            wallet_id=wallet_id,
            status="verified",
            metadata_json={"purpose": "ishuman_signup"},
        )
    )
    db.commit()
    db.close()

    result, _token = issue_lost_device_recovery_authorization(
        wallet_id=wallet_id,
        idv_session_id="idv_wrong_purpose",
    )
    assert not result.ok
    assert result.code == "recovery_idv_purpose_mismatch"


def test_lost_device_authorization_accepts_lost_device_purpose(
    wallet_seed,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import IsHumanVerification, LemmaWalletBinding
    from api.wallet_authn import issue_lost_device_recovery_authorization

    wallet_id = wallet_seed["wallet_id"]
    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        LemmaWalletBinding(
            wallet_id=wallet_id,
            lemma_person_id="person_recovery",
            binding_status="active",
        )
    )
    db.add(
        IsHumanVerification(
            session_id="idv_lost_ok",
            wallet_id=wallet_id,
            status="verified",
            metadata_json={"purpose": "lost_device_recovery"},
        )
    )
    db.commit()
    db.close()

    result, token = issue_lost_device_recovery_authorization(
        wallet_id=wallet_id,
        idv_session_id="idv_lost_ok",
    )
    assert result.ok
    assert token.startswith("wra_")
