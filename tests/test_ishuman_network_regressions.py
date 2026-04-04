import os
import sys

from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app_with_ishuman():
    from api.ishuman import ishuman_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_bp)
    return app


def test_start_verification_fails_closed_when_persistence_fails(monkeypatch):
    # Needed because monkeypatching api.database imports the module.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    app = _app_with_ishuman()

    monkeypatch.setattr(
        "billing.stripe_manager.StripeManager.create_identity_verification_session",
        lambda self, user_id, return_url: {
            "success": True,
            "session_id": "vs_test_123",
            "client_secret": "cs_test_123",
            "url": "https://verify.stripe.test/session",
        },
    )

    class _FailingDbSession:
        def add(self, _obj):
            return None

        def commit(self):
            raise RuntimeError("db down")

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("api.database.SessionLocal", lambda: _FailingDbSession())

    with app.test_client() as client:
        resp = client.post(
            "/api/ishuman/start-verification",
            json={"wallet_id": "wallet_test_abc"},
        )
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["success"] is False
    assert payload["error"] == "verification_session_persist_failed"


def test_ppid_derivation_prefers_wallet_secret(monkeypatch):
    from api.ishuman import _derive_ppid_for_site

    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_wallet_secret",
        lambda wallet_secret, rp_id: f"secret::{wallet_secret}::{rp_id}",
    )
    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_passkey",
        lambda passkey_credential_id, rp_id: f"passkey::{passkey_credential_id}::{rp_id}",
    )

    ppid = _derive_ppid_for_site(
        rp_id="example.com",
        wallet_secret="deadbeef" * 8,
        wallet_id="wallet_fallback_should_not_be_used",
    )
    assert ppid.startswith("secret::")
    assert "example.com" in ppid


def test_ppid_derivation_falls_back_to_wallet_id(monkeypatch):
    from api.ishuman import _derive_ppid_for_site

    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_wallet_secret",
        lambda wallet_secret, rp_id: f"secret::{wallet_secret}::{rp_id}",
    )
    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_passkey",
        lambda passkey_credential_id, rp_id: f"passkey::{passkey_credential_id}::{rp_id}",
    )

    ppid = _derive_ppid_for_site(
        rp_id="lemma.id",
        wallet_secret=None,
        wallet_id="wallet_id_123",
    )
    assert ppid == "passkey::wallet_id_123::lemma.id"


def test_ishuman_verifier_uses_sha256_revocation_membership():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "sha256HexText(candidate)" in content
    assert "this._bloomFilter.has(candidateHash)" in content
