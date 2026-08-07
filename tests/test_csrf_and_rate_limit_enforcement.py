"""
Regression tests for two hardening fixes:

1. The global CSRF guard (``auth.decorators.init_csrf_protection``) must
   fail CLOSED for cookie-authenticated mutations, while leaving
   header/bearer-authenticated API clients and anonymous requests unaffected.

2. ``auth.decorators.rate_limit`` must actually enforce limits (it was a
   silent no-op stub) by delegating to the shared flask-limiter instance.
"""

import os
import sys

import pytest
from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# CSRF guard
# ---------------------------------------------------------------------------

def _make_csrf_app():
    from auth.decorators import init_csrf_protection

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    init_csrf_protection(app)

    @app.route("/api/customer/mutate", methods=["POST"])
    def mutate():
        return jsonify({"ok": True})

    return app


def test_cookie_auth_mutation_without_token_is_blocked():
    app = _make_csrf_app()
    client = app.test_client()
    client.set_cookie("session", "ambient-auth-value")
    resp = client.post("/api/customer/mutate")
    assert resp.status_code == 403
    assert resp.is_json
    assert resp.get_json()["error"] == "csrf_validation_failed"


def test_cookie_auth_mutation_with_valid_double_submit_passes():
    app = _make_csrf_app()
    client = app.test_client()
    client.set_cookie("session", "ambient-auth-value")
    client.set_cookie("lemma_csrf_token", "tok123")
    resp = client.post("/api/customer/mutate", headers={"X-Lemma-CSRF": "tok123"})
    assert resp.status_code == 200


def test_cookie_auth_mutation_with_mismatched_token_is_blocked():
    app = _make_csrf_app()
    client = app.test_client()
    client.set_cookie("session", "ambient-auth-value")
    client.set_cookie("lemma_csrf_token", "tok123")
    resp = client.post("/api/customer/mutate", headers={"X-Lemma-CSRF": "different"})
    assert resp.status_code == 403


def test_wallet_csrf_cookie_pair_is_accepted():
    app = _make_csrf_app()
    client = app.test_client()
    client.set_cookie("lemma_wallet_session", "ambient-auth-value")
    client.set_cookie("lemma_wallet_csrf", "wtok")
    resp = client.post("/api/customer/mutate", headers={"X-Lemma-CSRF": "wtok"})
    assert resp.status_code == 200


def test_header_authenticated_request_is_not_csrf_gated():
    app = _make_csrf_app()
    client = app.test_client()
    # Browser attached an ambient cookie, but the request authenticates via a
    # header credential the attacker page could never set cross-origin.
    client.set_cookie("session", "ambient-auth-value")
    resp = client.post(
        "/api/customer/mutate",
        headers={"X-Lemma-Credential": "eyJhbGciOi..."},
    )
    assert resp.status_code == 200


def test_anonymous_mutation_is_not_gated():
    app = _make_csrf_app()
    client = app.test_client()
    resp = client.post("/api/customer/mutate")
    assert resp.status_code == 200


def test_exempt_prefixes_are_not_gated():
    app = _make_csrf_app()

    @app.route("/api/sdk/thing", methods=["POST"])
    def sdk_thing():
        return jsonify({"ok": True})

    @app.route("/api/verify/flow-state", methods=["POST"])
    def flow_state():
        return jsonify({"ok": True})

    client = app.test_client()
    client.set_cookie("session", "ambient-auth-value")
    resp = client.post("/api/sdk/thing")
    assert resp.status_code == 200
    # Same-origin dogfood mints without CSRF headers while a session cookie
    # may be present; Origin+site_id binding is the real guard.
    flow = client.post("/api/verify/flow-state")
    assert flow.status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def test_decorators_rate_limit_is_not_a_noop():
    """The legacy (max_requests, window) decorator must enforce via the limiter."""
    flask_limiter = pytest.importorskip("flask_limiter")  # noqa: F841

    from auth.decorators import rate_limit
    from auth.rate_limiter import create_limiter

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    limiter = create_limiter(app)
    if limiter is None:
        pytest.skip("flask_limiter not available")
    app.limiter = limiter

    @app.route("/api/limited", methods=["POST"])
    @rate_limit(max_requests=2, window=60)
    def limited():
        return jsonify({"ok": True})

    client = app.test_client()
    statuses = [client.post("/api/limited").status_code for _ in range(4)]

    assert 429 in statuses, f"expected a 429 after exceeding the limit, got {statuses}"
    assert statuses[0] == 200
