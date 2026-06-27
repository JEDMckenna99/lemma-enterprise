import base64
import json

from flask import Flask, jsonify, g

from api.authz_engine import extract_user_lemma_principal
from api.authz.replay import validate_pop_replay
from auth.decorators import require_authenticated, require_wallet_ppid, require_customer_or_admin


def _encode_credential(credential: dict) -> str:
    raw = json.dumps(credential).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def test_extract_user_lemma_principal_valid_header(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    credential = {
        "id": "cred_1",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("a" * 64),
        "claims": {
            "permissionId": "admin_access",
            "scope": ["read", "write"],
            "siteId": "lemma.id",
        },
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    principal, error = extract_user_lemma_principal(headers)
    assert error is None
    assert principal is not None
    assert principal.ppid.startswith("did:lemma:ppid_")
    assert principal.credential_id == "cred_1"
    assert principal.permission_id == "admin_access"
    assert principal.scope == ["read", "write"]
    assert principal.auth_method == "lemma_header"


def test_extract_user_lemma_principal_parses_csv_scope(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    credential = {
        "id": "cred_csv_scope",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("f" * 64),
        "claims": {
            "permissionId": "developer_access",
            "scope": "developer,write,read",
            "siteId": "lemma.id",
        },
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    principal, error = extract_user_lemma_principal(headers)
    assert error is None
    assert principal is not None
    assert principal.scope == ["developer", "write", "read"]


def test_extract_user_lemma_principal_developer_permission_fallback_scope(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    credential = {
        "id": "cred_dev_fallback",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("1" * 64),
        "claims": {
            "permissionId": "developer_access",
            "siteId": "lemma.id",
        },
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    principal, error = extract_user_lemma_principal(headers)
    assert error is None
    assert principal is not None
    assert principal.scope == ["write", "read"]


def test_require_authenticated_accepts_verified_lemma_header(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    app = Flask(__name__)

    @app.route("/probe", methods=["POST"])
    @require_authenticated
    def probe():
        return jsonify(
            {
                "ok": True,
                "ppid": getattr(g, "ppid", None),
                "auth_method": getattr(g, "auth_method", None),
            }
        )

    credential = {
        "id": "cred_2",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("b" * 64),
        "claims": {"permissionId": "read", "scope": ["read"]},
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    client = app.test_client()
    resp = client.post("/probe", headers=headers, json={})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["ppid"].startswith("did:lemma:ppid_")
    assert payload["auth_method"] == "lemma_header"


def test_require_authenticated_rejects_ppid_only_header():
    app = Flask(__name__)

    @app.route("/probe", methods=["POST"])
    @require_authenticated
    def probe():
        return jsonify({"ok": True})

    client = app.test_client()
    resp = client.post(
        "/probe",
        headers={"X-Lemma-PPID": "did:lemma:ppid_" + ("c" * 64)},
        json={},
    )
    assert resp.status_code == 401
    payload = resp.get_json()
    assert payload.get("error") in {"Authentication required", "auth_required"}


def test_require_wallet_ppid_accepts_verified_lemma_header(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    app = Flask(__name__)

    @app.route("/wallet-probe", methods=["POST"])
    @require_wallet_ppid
    def wallet_probe():
        return jsonify({"ok": True, "ppid": getattr(g, "ppid", None)})

    credential = {
        "id": "cred_3",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("d" * 64),
        "claims": {"permissionId": "read", "scope": ["read"]},
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    client = app.test_client()
    resp = client.post("/wallet-probe", headers=headers, json={})
    assert resp.status_code == 200
    assert resp.get_json().get("ppid", "").startswith("did:lemma:ppid_")


def test_require_customer_or_admin_marks_admin_from_lemma_scope(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )

    app = Flask(__name__)

    @app.route("/coa-probe", methods=["POST"])
    @require_customer_or_admin
    def coa_probe():
        return jsonify(
            {
                "ok": True,
                "ppid": getattr(g, "ppid", None),
                "is_admin": bool(getattr(g, "is_admin", False)),
            }
        )

    credential = {
        "id": "cred_4",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("e" * 64),
        "claims": {"permissionId": "admin_access", "scope": ["admin", "read"]},
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    client = app.test_client()
    resp = client.post("/coa-probe", headers=headers, json={})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload.get("ppid", "").startswith("did:lemma:ppid_")
    assert payload.get("is_admin") is True


def test_pop_replay_contract_reuses_nonce_denied():
    seen = set()

    def nonce_writer(key: str, _ttl: int) -> bool:
        if key in seen:
            return False
        seen.add(key)
        return True

    pop_payload = {
        "nonce": "nonce-1",
        "proof_id": "proof-1",
        "method": "GET",
        "path": "/probe",
        "body_hash": "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
        "iat": 0,
        "exp": 9999999999,
    }
    header_value = base64.urlsafe_b64encode(json.dumps(pop_payload).encode("utf-8")).decode("utf-8").rstrip("=")
    headers = {"X-Lemma-PoP": header_value}
    first = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/probe",
        body_bytes=b"",
        required=True,
        nonce_writer=nonce_writer,
    )
    second = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/probe",
        body_bytes=b"",
        required=True,
        nonce_writer=nonce_writer,
    )
    assert first.valid is True
    assert second.valid is False
    assert second.code == "AUTH_REPLAY_DETECTED"

