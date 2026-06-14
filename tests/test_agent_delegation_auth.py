"""Tests for unified agent delegation auth fixes."""

from __future__ import annotations

from flask import Flask, g

from api.authz.mode_policy import MODE_PROOF_REQUIRED, evaluate_mode_policy
from auth.agent_principal import extract_agent_admin_principal
from auth.request_principal import get_context_ppid, resolve_admin_principal


def test_extract_agent_admin_principal_defaults_empty_allowed_sites(monkeypatch):
    monkeypatch.setattr(
        "api.agent_credentials.validate_agent_token_with_reason",
        lambda token: (
            {
                "authorized_by_ppid": "did:lemma:ppid_" + ("a" * 64),
                "token_id": "tok_empty_sites",
                "scope": ["read", "admin"],
                "allowed_sites": [],
                "allowed_paths": ["/api/admin/**"],
            },
            None,
        ),
    )
    monkeypatch.setattr("api.agent_credentials.check_path_allowed", lambda path, patterns: True)

    principal, error, _info = extract_agent_admin_principal(
        {"X-Agent-Token": "lm_agent_testtoken"},
        request_path="/api/admin/trust/queue",
    )
    assert error is None
    assert principal is not None


def test_proof_required_allows_agent_delegation_without_proof_header():
    decision = evaluate_mode_policy(
        expected_mode=MODE_PROOF_REQUIRED,
        headers={"X-Agent-Token": "lm_agent_probe_token"},
    )
    assert decision.allowed is True


def test_proof_required_still_blocks_bearer_without_agent_or_proof():
    decision = evaluate_mode_policy(
        expected_mode=MODE_PROOF_REQUIRED,
        headers={"Authorization": "Bearer lm_at_example"},
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_PROOF_REQUIRED"


def test_resolve_admin_principal_from_g_context():
    app = Flask(__name__)
    with app.test_request_context("/api/customer/api-keys"):
        g.authenticated = True
        g.is_admin = True
        g.ppid = "did:lemma:ppid_" + ("b" * 64)
        g.permission_id = "admin_access"
        g.scope = ["admin", "read"]
        g.auth_method = "agent_token"

        principal, error = resolve_admin_principal()
        assert error is None
        assert principal.ppid == g.ppid


def test_get_context_ppid_reads_g():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.ppid = "did:lemma:ppid_" + ("c" * 64)
        assert get_context_ppid() == g.ppid


def test_resolve_agent_site_binding_for_request(monkeypatch):
    from api.agent_credentials import _resolve_agent_site_binding_for_request

    app = Flask(__name__)
    with app.test_request_context("/api/developer/sites/lemma.id/keys"):
        binding = _resolve_agent_site_binding_for_request(
            {"allowed_sites": ["lemma.id"], "scope": ["admin", "read"]}
        )
        assert binding == "lemma.id"
