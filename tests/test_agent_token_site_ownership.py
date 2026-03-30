import os

os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-unit-tests")

from flask import Flask

from api import agent_credentials


def test_validate_allowed_sites_against_ownership_rejects_non_owned(monkeypatch):
    monkeypatch.setattr(
        agent_credentials,
        "_get_owned_sites_for_delegator",
        lambda _ppid, _email: {"site-a.com"},
    )
    ok, invalid, owned = agent_credentials._validate_allowed_sites_against_ownership(
        allowed_sites=["site-a.com", "site-b.com"],
        authorized_by_ppid="did:lemma:ppid_123",
        authorized_by_email="owner@example.com",
    )
    assert ok is False
    assert invalid == ["site-b.com"]
    assert owned == {"site-a.com"}


def test_check_site_allowed_enforces_owned_sites_even_when_allowed_sites_present():
    app = Flask(__name__)
    info = {
        "allowed_sites": ["site-a.com", "site-b.com"],
        "owned_sites": ["site-a.com"],
    }
    with app.test_request_context("/api/agent/credentials?site_id=site-b.com"):
        allowed, blocked, allowed_norm, _requested = agent_credentials.check_site_allowed(info)
        assert allowed is False
        assert blocked == "site-b.com"
        assert "site-b.com" in allowed_norm
