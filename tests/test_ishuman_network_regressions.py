import os
import sys

import pytest
from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app_with_ishuman():
    from api.ishuman import ishuman_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_bp)
    return app


def test_start_verification_fails_closed_when_persistence_fails(monkeypatch, attach_wallet_assertion):
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

    from api.wallet_authn import Result

    monkeypatch.setattr("api.database.SessionLocal", lambda: _FailingDbSession())
    monkeypatch.setattr(
        "api.wallet_authn.register_wallet_signing_key",
        lambda **kwargs: Result(True),
    )
    monkeypatch.setattr(
        "api.wallet_authn.verify_assertion_from_body",
        lambda body, **kwargs: (Result(True), {}),
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/ishuman/start-verification",
            json=attach_wallet_assertion(
                {"wallet_id": "wallet_test_abc", "return_url": "https://lemma.id/app"},
                ["return_url"],
                wallet_secret="ab" * 32,
            ),
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


def test_ppid_derivation_requires_wallet_secret(monkeypatch):
    from api.ishuman import _derive_ppid_for_site

    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_wallet_secret",
        lambda wallet_secret, rp_id: f"secret::{wallet_secret}::{rp_id}",
    )

    with pytest.raises(ValueError, match="wallet_secret required"):
        _derive_ppid_for_site(
            rp_id="lemma.id",
            wallet_secret=None,
            wallet_id="wallet_id_123",
        )


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


def test_ishuman_verifier_waits_for_bridge_ready_and_uses_payload_site_id():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "WALLET_BRIDGE_READY" in content
    assert "_bridgeReadyPromise" in content
    assert "await Promise.race" in content
    assert "payload: {" in content
    assert "siteId: this.siteId" in content
    assert "credentialType: 'isHuman'" in content
    assert "nonce: challengeNonce" in content
    assert "challengeTimestamp" in content


def test_ishuman_verifier_requires_signed_bloom_snapshot_checks():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "verifyBloomSnapshot" in content
    assert "revocation_data_untrusted" in content
    assert "snapshot_invalid_signature" in content
    assert "snapshot_stale" in content
    assert "DEFAULT_MAX_BLOOM_STALENESS_SECONDS" in content


def test_ishuman_verifier_uses_session_cache_on_repeat_verify():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "_verifyFromCachedSession" in content
    assert "session_valid" in content
    assert "_requestSessionFromBridge" in content
    assert "GET_SESSION_PRESENTATION" in content
    verify_idx = content.index("async verify()")
    cached_idx = content.index("_verifyFromCachedSession", verify_idx)
    bridge_idx = content.index("_requestSessionFromBridge", verify_idx)
    assert cached_idx < bridge_idx


def test_ishuman_verifier_requires_presentation_signature_checks():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "missing_presentation_signature" in content
    assert "invalid_presentation_signature" in content
    assert "MAX_PRESENTATION_STALENESS_SECONDS" in content


def test_site_signing_pubkey_validator_rejects_invalid_values():
    from api.ishuman import _normalize_site_signing_pubkey

    assert _normalize_site_signing_pubkey("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    with pytest.raises(ValueError):
        _normalize_site_signing_pubkey("")
    with pytest.raises(ValueError):
        _normalize_site_signing_pubkey("not-base64")


def test_ishuman_issue_signs_string_claims_but_returns_typed_claims(monkeypatch):
    import json

    captured = {}

    class _Issuer:
        def issue_credential(self, ppid, claims):
            captured["ppid"] = ppid
            captured["claims"] = claims
            assert all(isinstance(value, str) for value in claims.values())
            return json.dumps({
                "id": "from_issuer",
                "issuer": "did:lemma:" + ("a" * 64),
                "subject": ppid,
                "claims": claims,
                "credentialSubject": claims,
                "issuedAt": "1",
                "expiresAt": "2",
                "proof": {"signatureValue": "ab"},
            })

        def get_did(self):
            return "did:lemma:" + ("a" * 64)

        def get_public_key_hex(self):
            return "a" * 64

    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: _Issuer())

    from api.ishuman import _issue_ishuman_credential

    credential = _issue_ishuman_credential("did:lemma:ppid_test", "wallet_test")

    assert captured["claims"]["isHuman"] == "true"
    assert credential["claims"]["isHuman"] is True
    assert credential["credentialSubject"]["isHuman"] is True
    assert credential["claims"]["siteId"] == "lemma.id"
