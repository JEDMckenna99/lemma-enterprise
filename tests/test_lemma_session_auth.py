"""Platform sign-in session: presentation-verified, fail-closed.

Covers api/lemma_session_auth.py — the dogfooded "Sign in with lemma.id"
session that opens the lemma.id manager at /app. The session may ONLY be
minted from a server-verified signed presentation bound to this site.
"""

from __future__ import annotations

import time

import pytest
from flask import Flask

# Fixed 32-byte dev issuer seed (NOT a production key).
_DEV_ISSUER_SEED = b"session-auth-dev-issuer-seed-01!"


@pytest.fixture(name="dev_issuer")
def fixture_dev_issuer(monkeypatch):
    """Deterministic local issuer whose DID is trusted via env config."""
    lemma_crypto = pytest.importorskip("lemma_crypto")
    issuer = lemma_crypto.PyMinimalIssuer.from_seed(list(_DEV_ISSUER_SEED))

    from api import trusted_issuers

    monkeypatch.setenv("TRUSTED_ISSUER_DIDS", issuer.get_did())
    trusted_issuers.clear_cache()
    yield issuer
    trusted_issuers.clear_cache()


@pytest.fixture(name="live_revocation")
def fixture_live_revocation(monkeypatch):
    """Healthy Bloom revocation service with nothing revoked."""
    from api import revocation_verifier as rv

    class _Verifier:
        def is_revoked(self, _candidate):
            return False

    monkeypatch.setattr(rv, "_revocation_sync_ready", True, raising=False)
    monkeypatch.setattr(
        "api.permission_verification.get_global_verifier", lambda: _Verifier()
    )


@pytest.fixture(name="client")
def fixture_client(monkeypatch, live_revocation):
    # Production binding: the platform only accepts credentials bound to lemma.id.
    monkeypatch.setenv("ENVIRONMENT", "production")

    from api.lemma_session_auth import lemma_session_bp

    app = Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", TESTING=True)
    app.register_blueprint(lemma_session_bp)
    return app.test_client()


def _make_credential(issuer, ppid: str, site: str = "lemma.id", assurance: str = "passkey") -> dict:
    from api.ishuman import _sign_with_issuer_for_browser

    now = int(time.time())
    credential = {
        "id": f"ishuman_master_test_{ppid[-6:]}",
        "issuer": issuer.get_did(),
        "subject": ppid,
        "claims": {
            "assurance": assurance,
            "isHuman": assurance == "ishuman",
            "packageType": "identity",
            "siteId": site,
            "siteDomain": site,
            "issuedAt": str(now),
            "expiresAt": str(now + 3600),
        },
        "issuedAt": now,
        "expiresAt": now + 3600,
    }
    credential["proof"] = {"signatureValueWeb": _sign_with_issuer_for_browser(credential, issuer)}
    return credential


def _post_presentation(client, credential):
    return client.post("/api/auth/session", json={"presentation": {"credential": credential}})


def test_valid_presentation_mints_session(client, dev_issuer):
    ppid = "ppid_session_test_valid_001"
    resp = _post_presentation(client, _make_credential(dev_issuer, ppid))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["ppid"] == ppid
    assert body["assurance"] == "passkey"

    status = client.get("/api/auth/session").get_json()
    assert status["signed_in"] is True
    assert status["ppid"] == ppid


def test_bare_ppid_without_presentation_rejected(client, dev_issuer):
    resp = client.post("/api/auth/session", json={"ppid": "ppid_attacker_supplied"})
    assert resp.status_code == 400

    assert client.get("/api/auth/session").get_json()["signed_in"] is False


def test_wrong_site_binding_rejected(client, dev_issuer):
    credential = _make_credential(dev_issuer, "ppid_wrong_site_001", site="evil.example.com")
    resp = _post_presentation(client, credential)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "site_id_mismatch"

    assert client.get("/api/auth/session").get_json()["signed_in"] is False


def test_untrusted_issuer_rejected(client, monkeypatch):
    lemma_crypto = pytest.importorskip("lemma_crypto")
    from api import trusted_issuers

    # An issuer whose DID is NOT in the trust list.
    rogue = lemma_crypto.PyMinimalIssuer.from_seed(list(b"rogue-issuer-seed-000000000000!!"))
    monkeypatch.delenv("TRUSTED_ISSUER_DIDS", raising=False)
    trusted_issuers.clear_cache()

    resp = _post_presentation(client, _make_credential(rogue, "ppid_rogue_001"))
    assert resp.status_code == 401
    assert client.get("/api/auth/session").get_json()["signed_in"] is False
    trusted_issuers.clear_cache()


def test_tampered_claims_rejected(client, dev_issuer):
    credential = _make_credential(dev_issuer, "ppid_tampered_001")
    credential["claims"]["assurance"] = "ishuman"  # tamper after signing

    resp = _post_presentation(client, credential)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_signature"
    assert client.get("/api/auth/session").get_json()["signed_in"] is False


def test_expired_credential_rejected(client, dev_issuer):
    from api.ishuman import _sign_with_issuer_for_browser

    past = int(time.time()) - 7200
    credential = {
        "id": "ishuman_master_test_expired",
        "issuer": dev_issuer.get_did(),
        "subject": "ppid_expired_001",
        "claims": {
            "assurance": "passkey",
            "isHuman": False,
            "packageType": "identity",
            "siteId": "lemma.id",
            "siteDomain": "lemma.id",
            "issuedAt": str(past),
            "expiresAt": str(past + 3600),
        },
        "issuedAt": past,
        "expiresAt": past + 3600,
    }
    credential["proof"] = {
        "signatureValueWeb": _sign_with_issuer_for_browser(credential, dev_issuer)
    }

    resp = _post_presentation(client, credential)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "expired"


def test_revocation_outage_fails_closed(client, dev_issuer, monkeypatch):
    monkeypatch.setattr(
        "api.ishuman.verify_presentation_payload",
        lambda _body: ({"success": False, "error": "revocation_unavailable"}, 503),
    )
    resp = _post_presentation(client, _make_credential(dev_issuer, "ppid_outage_001"))
    assert resp.status_code == 401
    assert client.get("/api/auth/session").get_json()["signed_in"] is False


def test_logout_clears_session(client, dev_issuer):
    _post_presentation(client, _make_credential(dev_issuer, "ppid_logout_001"))
    assert client.get("/api/auth/session").get_json()["signed_in"] is True

    resp = client.post("/api/auth/session/logout")
    assert resp.status_code == 200
    assert client.get("/api/auth/session").get_json()["signed_in"] is False
