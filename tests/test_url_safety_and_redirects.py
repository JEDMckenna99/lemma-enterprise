"""Tests for SSRF-safe outbound URL validation and open-redirect hardening."""

from __future__ import annotations

import os
import socket
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api import url_safety  # noqa: E402


def _fake_getaddrinfo(*ips):
    """Build a getaddrinfo replacement returning the given IP strings."""
    def _inner(host, port, *args, **kwargs):
        results = []
        for ip in ips:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, port) if family == socket.AF_INET else (ip, port, 0, 0)
            results.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr))
        return results
    return _inner


# ---------------------------------------------------------------------------
# is_safe_outbound_url (SSRF guard)
# ---------------------------------------------------------------------------

def test_outbound_allows_public_host(monkeypatch):
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    ok, reason = url_safety.is_safe_outbound_url("https://example.com/webhook")
    assert ok is True
    assert reason == "ok"


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",        # loopback
        "10.0.0.5",         # private RFC1918
        "192.168.1.10",     # private RFC1918
        "172.16.5.4",       # private RFC1918
        "169.254.169.254",  # link-local / cloud metadata
        "::1",              # IPv6 loopback
        "fd00::1",          # IPv6 unique-local
        "::ffff:169.254.169.254",  # IPv4-mapped metadata
        "100.64.0.1",       # CGNAT (not is_global)
        "0.0.0.0",          # unspecified
    ],
)
def test_outbound_blocks_internal_ips(monkeypatch, ip):
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _fake_getaddrinfo(ip))
    ok, reason = url_safety.is_safe_outbound_url("https://internal.example/webhook")
    assert ok is False
    assert reason in {"private_or_reserved_ip", "invalid_ip"}


def test_outbound_blocks_when_any_record_is_private(monkeypatch):
    # DNS returns one public and one private answer -> must fail closed.
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34", "127.0.0.1"))
    ok, _ = url_safety.is_safe_outbound_url("https://rebind.example/webhook")
    assert ok is False


@pytest.mark.parametrize(
    "url,reason",
    [
        ("file:///etc/passwd", "scheme_not_allowed"),
        ("gopher://evil/", "scheme_not_allowed"),
        ("ftp://host/", "scheme_not_allowed"),
        ("https://", "missing_host"),
        ("", "empty_url"),
        (None, "empty_url"),
    ],
)
def test_outbound_rejects_bad_schemes_and_hosts(url, reason):
    ok, got = url_safety.is_safe_outbound_url(url)
    assert ok is False
    assert got == reason


def test_outbound_dns_failure_fails_closed(monkeypatch):
    def _boom(*a, **k):
        raise socket.gaierror("no such host")
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _boom)
    ok, reason = url_safety.is_safe_outbound_url("https://does-not-resolve.example/")
    assert ok is False
    assert reason == "dns_resolution_failed"


# ---------------------------------------------------------------------------
# is_safe_relative_redirect
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", ["/dashboard", "/a/b/c?x=1", "/"])
def test_relative_redirect_allows_same_origin_paths(target):
    assert url_safety.is_safe_relative_redirect(target) is True


@pytest.mark.parametrize(
    "target",
    [
        "//evil.com",
        "/\\evil.com",
        "https://evil.com",
        "http://evil.com",
        "dashboard",
        "",
        None,
        "/path\nSet-Cookie: x",
        "/%2fevil.com",
        "/%5cevil.com",
    ],
)
def test_relative_redirect_rejects_open_redirects(target):
    assert url_safety.is_safe_relative_redirect(target) is False


# ---------------------------------------------------------------------------
# is_host_allowed_redirect
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "target",
    [
        "https://lemma.id/cb",
        "https://app.lemma.id/cb?ok=1",
        "https://deep.sub.lemma.id/x",
    ],
)
def test_host_allowed_redirect_accepts_site_hosts(target):
    assert url_safety.is_host_allowed_redirect(target, ["lemma.id"]) is True


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.com/cb",
        "http://lemma.id/cb",           # non-https downgrade
        "https://notlemma.id/cb",       # suffix trick
        "https://lemma.id.evil.com/cb",  # prefix trick
        "//lemma.id/cb",                # protocol-relative
        "",
        None,
    ],
)
def test_host_allowed_redirect_rejects_others(target):
    assert url_safety.is_host_allowed_redirect(target, ["lemma.id"]) is False


# ---------------------------------------------------------------------------
# sdk_auth open-redirect integration
# ---------------------------------------------------------------------------

@pytest.fixture(name="sdk_client")
def fixture_sdk_client(monkeypatch):
    from api.sdk_auth import sdk_auth_bp
    import api.sdk_auth as sdk_auth

    monkeypatch.setattr(sdk_auth, "_store_pending_sdk_request", lambda state, payload: True)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(sdk_auth_bp)
    with app.test_client() as client:
        yield client


def test_sdk_request_accepts_same_domain_return(sdk_client):
    resp = sdk_client.get("/auth/sdk-request?site=app.example.com&return=https://app.example.com/cb")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_sdk_request_rejects_cross_domain_return(sdk_client):
    resp = sdk_client.get("/auth/sdk-request?site=app.example.com&return=https://evil.com/cb")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid return URL"


def test_sdk_request_rejects_protocol_relative_return(sdk_client):
    resp = sdk_client.get("/auth/sdk-request?site=app.example.com&return=//evil.com")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# agent session open-redirect integration
# ---------------------------------------------------------------------------

def _unwrap(func):
    handler = func
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    return handler


@pytest.fixture(name="agent_session_ctx")
def fixture_agent_session_ctx(monkeypatch):
    import api.agent_credentials as mod

    monkeypatch.setattr(
        mod,
        "validate_agent_token",
        lambda token: {
            "token_id": "tok_1",
            "authorized_by_ppid": "did:lemma:ppid_" + ("a" * 64),
            "scope": ["read"],
            "allowed_sites": None,
        },
    )
    monkeypatch.setattr(mod, "check_site_allowed", lambda info: (True, None, set(), []))
    monkeypatch.setattr(mod, "apply_agent_token_to_flask_session", lambda info: None)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test"
    return app, _unwrap(mod.create_agent_session)


def test_agent_session_rejects_protocol_relative_redirect(agent_session_ctx):
    app, handler = agent_session_ctx
    with app.test_request_context(
        "/api/agent/session?redirect=//evil.com",
        headers={"X-Agent-Token": "lm_agent_x"},
    ):
        resp = handler()
    # Not a redirect: falls through to the JSON session response.
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    assert status == 200
    location = (resp[0] if isinstance(resp, tuple) else resp).headers.get("Location")
    assert location is None


def test_agent_session_allows_relative_redirect(agent_session_ctx):
    app, handler = agent_session_ctx
    with app.test_request_context(
        "/api/agent/session?redirect=/dashboard",
        headers={"X-Agent-Token": "lm_agent_x"},
    ):
        resp = handler()
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")


def test_agent_session_allows_platform_host_redirect(agent_session_ctx):
    app, handler = agent_session_ctx
    with app.test_request_context(
        "/api/agent/session?redirect=https://lemma.id/admin",
        headers={"X-Agent-Token": "lm_agent_x"},
    ):
        resp = handler()
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://lemma.id/admin"
