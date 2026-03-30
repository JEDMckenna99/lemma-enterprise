import time

from flask import Flask

from api import permission_verification, trusted_issuers


def test_trusted_issuer_verification_uses_canonical_revocation(monkeypatch):
    credential = {
        "id": "cred_revoked_1",
        "issuer": "did:lemma:test_issuer",
        "claims": {"expiresAt": str(int(time.time()) + 3600)},
    }

    monkeypatch.setattr(trusted_issuers, "is_trusted_issuer", lambda _issuer: True)
    monkeypatch.setattr("api.revocation_verifier.is_credential_revoked", lambda _cid: True)

    result = trusted_issuers.verify_credential_with_trust(credential)
    assert result["valid"] is False
    assert result["not_revoked"] is False
    assert result["reason"] == "revoked"


def test_permission_verification_denies_when_canonically_revoked(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(permission_verification.permission_verification_bp)

    class _Verifier:
        def verify_credential_json(self, _payload):
            return True

        def is_revoked(self, _credential_id):
            return False

    monkeypatch.setenv("LEMMA_API_KEY", "test_key")
    monkeypatch.setattr(permission_verification, "is_nonce_fresh", lambda _nonce: True)
    monkeypatch.setattr(permission_verification, "get_global_verifier", lambda: _Verifier())
    monkeypatch.setattr(permission_verification, "is_credential_revoked", lambda _cid: True)

    payload = {
        "credential": {
            "id": "cred_revoked_2",
            "claims": {"siteDomain": "lemma.id", "permissionId": "read"},
        },
        "nonce": "nonce_test_123",
        "site_domain": "lemma.id",
        "timestamp": int(time.time() * 1000),
    }

    with app.test_client() as client:
        resp = client.post(
            "/api/sdk/verify-permission-lemma",
            json=payload,
            headers={"Origin": "https://lemma.id", "Authorization": "Bearer test_key"},
        )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "Credential has been revoked"
