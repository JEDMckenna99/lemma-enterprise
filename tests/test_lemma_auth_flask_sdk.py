import os
import sys

from flask import Flask, jsonify


sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sdk",
        "python",
        "lemma_auth_flask",
        "src",
    ),
)

from lemma_auth_flask import LemmaAuth, evaluate_proof_contract  # noqa: E402


def _make_header(payload: str) -> dict:
    return {"X-Lemma-Credential": payload}


def test_require_lemma_accepts_verified_credential():
    def _verify(_credential):
        return {"valid": True}

    app = Flask(__name__)
    middleware = LemmaAuth(verifier=_verify, required_site="example.com")

    @app.get("/secure")
    @middleware.require_lemma(scope="read", site_bound=True)
    def secure():
        return jsonify({"ok": True})

    valid_payload = (
        '{"id":"cred_1","subject":"did:lemma:ppid_abc","claims":{"scope":["read"],"siteId":"example.com"}}'
    )
    with app.test_client() as client:
        resp = client.get("/secure", headers=_make_header(valid_payload))
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


def test_require_lemma_rejects_missing_scope():
    def _verify(_credential):
        return {"valid": True}

    app = Flask(__name__)
    middleware = LemmaAuth(verifier=_verify, required_site="example.com")

    @app.get("/secure")
    @middleware.require_lemma(scope="admin", site_bound=True)
    def secure():
        return jsonify({"ok": True})

    valid_payload = (
        '{"id":"cred_1","subject":"did:lemma:ppid_abc","claims":{"scope":["read"],"siteId":"example.com"}}'
    )
    with app.test_client() as client:
        resp = client.get("/secure", headers=_make_header(valid_payload))
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "missing_scope"
        assert resp.get_json()["message"] == "Insufficient scope"


def test_require_lemma_handles_verifier_exception_as_auth_error():
    def _verify(_credential):
        raise RuntimeError("verifier backend unavailable")

    app = Flask(__name__)
    middleware = LemmaAuth(verifier=_verify, required_site="example.com")

    @app.get("/secure")
    @middleware.require_lemma(scope="read", site_bound=True)
    def secure():
        return jsonify({"ok": True})

    valid_payload = (
        '{"id":"cred_1","subject":"did:lemma:ppid_abc","claims":{"scope":["read"],"siteId":"example.com"}}'
    )
    with app.test_client() as client:
        resp = client.get("/secure", headers=_make_header(valid_payload))
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid_lemma:verification_error"
        assert resp.get_json()["message"] == "Credential verification failed"


def test_require_lemma_site_bound_uses_canonical_domain_matching():
    def _verify(_credential):
        return {"valid": True}

    app = Flask(__name__)
    middleware = LemmaAuth(verifier=_verify, required_site="https://www.example.com")

    @app.get("/secure")
    @middleware.require_lemma(scope="read", site_bound=True)
    def secure():
        return jsonify({"ok": True})

    # siteId variant would fail previously without canonicalization
    valid_payload = (
        '{"id":"cred_1","subject":"did:lemma:ppid_abc","claims":{"scope":["read"],"siteId":"example.com"}}'
    )
    with app.test_client() as client:
        resp = client.get("/secure", headers=_make_header(valid_payload))
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


def test_flask_sdk_proof_contract_profile_parity():
    decision = evaluate_proof_contract(
        {
            "profile": "authz_profile_v2",
            "proof_id": "prf_1",
            "root_grant_id": "root_1",
            "policy_version": "v2-test",
            "scope": ["read"],
            "expires_at": 9999999999,
        },
        required_scope="read",
    )
    assert decision["decision"] == "allow"
    assert decision["reason_code"] == "OK"
    assert decision["profile"] == "authz_profile_v2"

