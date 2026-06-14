"""Agent credential list auth accepts wallet session + lemma header PPID."""

from __future__ import annotations

import json
import base64

from flask import Flask


def _encode_header(credential: dict) -> str:
    raw = json.dumps(credential).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _make_client():
    from api.agent_credentials import agent_credentials_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(agent_credentials_bp)
    return app.test_client()


def test_list_agent_credentials_accepts_wallet_session_with_header_ppid(monkeypatch):
    from api import agent_credentials as mod

    ppid = "did:lemma:ppid_" + ("a" * 64)
    credential = {
        "id": "cred_admin_test",
        "subject": ppid,
        "claims": {
            "permissionId": "admin_access",
            "siteId": "lemma.id",
        },
    }

    monkeypatch.setattr(mod, "_has_valid_wallet_unlock_session", lambda: True)
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (None, "invalid_lemma:invalid_signature"),
    )
    monkeypatch.setattr(mod, "_extract_ppid_from_lemma_header", lambda: None)
    monkeypatch.setattr(
        mod,
        "_decode_lemma_header_credential",
        lambda: credential,
    )
    monkeypatch.setattr(
        mod,
        "_parse_ppid_from_credential_dict",
        lambda cred: ppid if cred is credential else None,
    )

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchall(self):
            return []

        def close(self):
            return None

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr("api.database.get_db_connection", lambda: FakeConn())

    client = _make_client()
    resp = client.get(
        "/api/agent/credentials",
        headers={"X-Lemma-Credential": _encode_header(credential)},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_list_agent_credentials_still_requires_auth_without_session(monkeypatch):
    from api import agent_credentials as mod

    monkeypatch.setattr(mod, "_has_valid_wallet_unlock_session", lambda: False)
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (None, "missing_lemma_header"),
    )
    monkeypatch.setattr(mod, "_extract_ppid_from_lemma_header", lambda: None)

    client = _make_client()
    resp = client.get("/api/agent/credentials")
    assert resp.status_code == 401


def test_issue_accepts_wallet_delegation_when_header_invalid(monkeypatch):
    from api import agent_credentials as mod
    from flask import jsonify

    ppid = "did:lemma:ppid_" + ("b" * 64)
    monkeypatch.setattr(mod, "_has_valid_wallet_unlock_session", lambda: True)
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (None, "invalid_lemma:invalid_signature"),
    )
    monkeypatch.setattr(
        mod,
        "_require_delegation_admin_session",
        lambda: (False, (jsonify({"success": False, "error": "passed_decorator_gate"}), 403)),
    )

    client = _make_client()
    resp = client.post(
        "/api/agent/credentials/issue",
        json={
            "agent_name": "Cursor Admin Inspector",
            "scope": ["read", "admin"],
            "operator_plane": True,
            "allowed_sites": ["lemma.id"],
            "admin_credential": {
                "subject": ppid,
                "claims": {
                    "permissionId": "admin_access",
                    "siteId": "lemma.id",
                },
            },
        },
        headers={"X-Lemma-Credential": "invalid"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "passed_decorator_gate"


def test_try_wallet_delegation_principal_reads_body_admin_credential(monkeypatch):
    from api import agent_credentials as mod

    ppid = "did:lemma:ppid_" + ("c" * 64)
    monkeypatch.setattr(mod, "_has_valid_wallet_unlock_session", lambda: True)

    app = Flask(__name__)
    app.config["TESTING"] = True
    with app.test_request_context(
        "/api/agent/credentials/issue",
        method="POST",
        json={
            "admin_credential": {
                "subject": ppid,
                "claims": {"permissionId": "admin_access", "siteId": "lemma.id"},
            }
        },
    ):
        assert mod._try_wallet_delegation_principal() == ppid
