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

    # Default IDV rail is didit (it replaced Stripe Identity); enable it and
    # mock a successful session so the flow reaches the persistence step.
    monkeypatch.setattr("api.config.is_ishuman_didit_enabled", lambda: True)
    monkeypatch.setattr(
        "billing.didit_manager.DiditManager.create_identity_verification_session",
        lambda self, user_id, return_url, callback_url=None: {
            "success": True,
            "session_id": "didit_test_123",
            "url": "https://verify.didit.test/session",
        },
    )

    class _EmptyQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class _FailingDbSession:
        def query(self, *_args, **_kwargs):
            return _EmptyQuery()

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

    # Provisional (pre-IDV) derivation: no person root exists yet, so the
    # wallet-secret path is the expected source.
    ppid = _derive_ppid_for_site(
        rp_id="example.com",
        wallet_secret="deadbeef" * 8,
        wallet_id="wallet_fallback_should_not_be_used",
        provisional=True,
    )
    assert ppid.startswith("secret::")
    assert "example.com" in ppid


def test_ppid_derivation_requires_wallet_secret(monkeypatch):
    from api.ishuman import _derive_ppid_for_site

    monkeypatch.setattr(
        "api.ppid.derive_ppid_from_wallet_secret",
        lambda wallet_secret, rp_id: f"secret::{wallet_secret}::{rp_id}",
    )

    with pytest.raises(ValueError, match="wallet_secret or lemma_person_id required"):
        _derive_ppid_for_site(
            rp_id="lemma.id",
            wallet_secret=None,
            wallet_id="wallet_id_123",
            provisional=True,
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


def test_ishuman_verifier_popup_carries_site_id():
    # Phase 2.1: no bridge iframe — the popup carries the site id so the IDV
    # flow can derive and issue a per-site proof.
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "_issueSiteProofViaPopup" in content
    assert "popupUrl.searchParams.set('site_id', this.siteId)" in content
    assert "ISHUMAN_SITE_PROOF_ISSUED" in content


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


def test_ishuman_verifier_requires_signed_trust_list_checks():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "TRUST_LIST_PREFIX" in content
    assert "verifySignedTrustList" in content
    assert "trust_list_invalid_signature" in content
    assert "snapshot_issuer_untrusted" in content
    assert "this._trustListTrusted" in content


def test_ishuman_verifier_uses_session_cache_before_popup():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "_verifyFromSiteVcCache" in content
    assert "site_proof_required" in content
    # The local cache must be consulted before signalling the popup path.
    verify_idx = content.index("async _verifyOnce(")
    cached_idx = content.index("_verifyFromSiteVcCache", verify_idx)
    proof_idx = content.index("'site_proof_required'", verify_idx)
    assert cached_idx < proof_idx


def test_ishuman_verifier_retries_trust_refresh_on_untrusted_issuer():
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "'untrusted_issuer'" in content
    assert "retriedTrust" in content
    assert "await this._syncBloom({ force: true })" in content


def test_ishuman_verifier_is_popup_only_no_bridge():
    """Phase 2.1: the bridge iframe was removed entirely; verify() is popup-only."""
    sdk_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "ishuman-verifier.js",
    )
    with open(sdk_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "_setupBridge" not in content
    assert "_requestSessionFromBridge" not in content
    assert "BRIDGE_PATH" not in content
    assert "GET_SESSION_PRESENTATION" not in content
    # popup-only mode signals site_proof_required on a cache miss.
    assert "site_proof_required" in content
    assert "_issueSiteProofViaPopup" in content


def test_ishuman_wallet_gates_daily_unlock_bundle():
    """Phase 2.2: the daily-unlock bundle has its own dedicated opt-out."""
    wallet_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "js",
        "lemma-wallet.js",
    )
    with open(wallet_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "_isHumanLockDisabled" in content
    assert "LEMMA_DISABLE_DAILY_UNLOCK" in content
    # isIsHumanLockValid must bail out when the lock is disabled.
    valid_idx = content.index("isIsHumanLockValid() {")
    guard_idx = content.index("if (this._isHumanLockDisabled()) return false;", valid_idx)
    assert valid_idx < guard_idx


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

    owner_ppid = f"did:lemma:ppid_{'1' * 64}"
    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", owner_ppid)
    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: _Issuer())

    from api.ishuman import _issue_ishuman_credential

    credential = _issue_ishuman_credential(owner_ppid, "wallet_test")

    assert captured["claims"]["isHuman"] == "true"
    assert captured["claims"]["permissionId"] == "admin_access"
    assert credential["claims"]["isHuman"] is True
    assert credential["credentialSubject"]["isHuman"] is True
    assert credential["claims"]["siteId"] == "lemma.id"
    assert credential["claims"]["siteDomain"] == "lemma.id"
    assert credential["claims"]["permissionId"] == "admin_access"
    assert credential["claims"]["permission_level"] == "admin"
    assert credential["claims"]["accountType"] == "admin"
    assert credential["claims"]["scope"] == ["admin", "write", "read", "developer"]


def test_ishuman_master_for_non_owner_does_not_get_platform_admin_claims(monkeypatch):
    import json

    class _Issuer:
        def issue_credential(self, ppid, claims):
            return json.dumps({
                "issuer": "did:lemma:" + ("a" * 64),
                "subject": ppid,
                "claims": claims,
                "credentialSubject": claims,
                "proof": {"signatureValue": "ab"},
            })

        def get_did(self):
            return "did:lemma:" + ("a" * 64)

        def get_public_key_hex(self):
            return "a" * 64

    monkeypatch.setenv("LEMMA_PLATFORM_OWNER_PPID", f"did:lemma:ppid_{'1' * 64}")
    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: _Issuer())

    from api.ishuman import _issue_ishuman_credential

    credential = _issue_ishuman_credential(
        f"did:lemma:ppid_{'2' * 64}",
        "wallet_test",
    )

    claims = credential["claims"]
    assert claims["isHuman"] is True
    assert claims["siteId"] == "lemma.id"
    assert claims["siteDomain"] == "lemma.id"
    assert "permissionId" not in claims
    assert "permission_level" not in claims
    assert "accountType" not in claims
    assert "scope" not in claims


def test_ishuman_site_proof_does_not_inherit_platform_admin_claims(monkeypatch):
    import json

    class _Issuer:
        def issue_credential(self, ppid, claims):
            return json.dumps({
                "issuer": "did:lemma:" + ("a" * 64),
                "subject": ppid,
                "claims": claims,
                "credentialSubject": claims,
                "proof": {"signatureValue": "ab"},
            })

        def get_did(self):
            return "did:lemma:" + ("a" * 64)

        def get_public_key_hex(self):
            return "a" * 64

    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: _Issuer())

    from api.ishuman import _issue_ishuman_credential

    credential = _issue_ishuman_credential(
        "did:lemma:ppid_site",
        "wallet_test",
        site_id="tickets-demo.lemma.id",
    )

    claims = credential["claims"]
    assert claims["isHuman"] is True
    assert claims["siteId"] == "tickets-demo.lemma.id"
    assert "permissionId" not in claims
    assert "permission_level" not in claims
    assert "accountType" not in claims
