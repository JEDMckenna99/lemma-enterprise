import json
import os
import sys

from flask import Flask, g

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.authz_engine import AuthzPrincipal  # noqa: E402
from api.forensic_audit import capture_action_proof  # noqa: E402


OWNER_PPID = "did:lemma:ppid_" + ("a" * 64)


def test_capture_action_proof_logs_verified_ppid(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    logged = {}

    def _fake_log_event(event_type, **kwargs):
        logged.update(kwargs)
        logged["event_type"] = event_type

    monkeypatch.setattr("api.audit_logger.log_event", _fake_log_event)
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid=OWNER_PPID,
                credential_id="cred_forensic_1",
                permission_id="admin_access",
                scope=["admin"],
                site_binding="lemma.id",
            ),
            None,
        ),
    )

    credential = {
        "id": "cred_forensic_1",
        "subject": OWNER_PPID,
        "issuer": "did:web:lemma.id",
        "claims": {"permissionId": "admin_access", "siteId": "site_abc"},
        "proof": {"type": "Ed25519Signature2020", "proofValue": "abc"},
    }

    with app.test_request_context(
        "/api/developer/sites/site_abc/keys",
        method="POST",
        headers={"X-Lemma-Credential": json.dumps(credential)},
    ):
        g.ppid = OWNER_PPID
        g.credential_id = "cred_forensic_1"
        g.permission_id = "admin_access"
        g.auth_method = "lemma_header"
        capture_action_proof(action="site_key.create", site_id="site_abc")

    proof = logged["metadata"]["action_proof"]
    assert proof["ppid"] == OWNER_PPID
    assert proof["credential_id"] == "cred_forensic_1"
    assert proof["action"] == "site_key.create"


def test_tampered_body_ppid_not_used_in_proof(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    logged = {}

    def _fake_log_event(event_type, **kwargs):
        logged.update(kwargs)
        logged["event_type"] = event_type

    monkeypatch.setattr("api.audit_logger.log_event", _fake_log_event)
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid=OWNER_PPID,
                credential_id="cred_forensic_2",
                permission_id="admin_access",
                scope=["admin"],
                site_binding="lemma.id",
            ),
            None,
        ),
    )

    forged_ppid = "did:lemma:ppid_" + ("f" * 64)
    credential = {
        "id": "cred_forensic_2",
        "subject": OWNER_PPID,
        "claims": {"permissionId": "admin_access"},
    }

    with app.test_request_context(
        "/api/developer/sites/site_abc/users/did:lemma:ppid_fake/revoke",
        method="POST",
        headers={"X-Lemma-Credential": json.dumps(credential)},
        json={"ppid": forged_ppid},
    ):
        g.ppid = OWNER_PPID
        g.credential_id = "cred_forensic_2"
        g.auth_method = "lemma_header"
        capture_action_proof(action="site_user.revoke", site_id="site_abc", resource=forged_ppid)

    proof = logged["metadata"]["action_proof"]
    assert proof["ppid"] == OWNER_PPID
    assert proof["ppid"] != forged_ppid
