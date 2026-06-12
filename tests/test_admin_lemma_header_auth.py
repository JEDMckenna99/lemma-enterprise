import base64
import json

from flask import Flask, jsonify

from auth import decorators


def _encode_lemma_header(lemma: dict) -> str:
    raw = json.dumps(lemma, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _stub_lemma(permission_id: str) -> dict:
    scope_csv = "admin,write,read" if "admin" in permission_id else "read"
    return {
        "id": "cred_admin_header_test",
        "issuer": "did:lemma:test_issuer",
        "subject": "did:lemma:ppid_" + ("a" * 64),
        "claims": {
            "siteId": "lemma.id",
            "permissionId": permission_id,
            "scope": scope_csv,
        },
    }


def _app_with_site_admin_route():
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/_test/admin", methods=["GET"])
    @decorators.require_site_admin
    def _route():
        return jsonify({"ok": True}), 200

    return app


def test_require_site_admin_accepts_admin_lemma_header(monkeypatch):
    app = _app_with_site_admin_route()

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": True, "reason": "ok"},
    )

    lemma_header = _encode_lemma_header(_stub_lemma("admin_access"))
    with app.test_client() as client:
        resp = client.get("/_test/admin", headers={"X-Lemma-Credential": lemma_header})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


def test_require_site_admin_rejects_non_admin_lemma_header(monkeypatch):
    app = _app_with_site_admin_route()

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": True, "reason": "ok"},
    )

    lemma_header = _encode_lemma_header(_stub_lemma("customer_access"))
    with app.test_client() as client:
        resp = client.get("/_test/admin", headers={"X-Lemma-Credential": lemma_header})
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "missing_scope"


def test_require_site_admin_rejects_invalid_credential(monkeypatch):
    """When verify_credential_with_trust returns invalid, auth is denied."""
    app = _app_with_site_admin_route()

    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": False, "reason": "untrusted_issuer"},
    )

    lemma_header = _encode_lemma_header(_stub_lemma("admin_access"))
    with app.test_client() as client:
        resp = client.get("/_test/admin", headers={"X-Lemma-Credential": lemma_header})
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "auth_required"


def test_admin_trust_routes_require_admin(monkeypatch, fake_ishuman_db_session_factory):
    """Cover new admin trust + overview routes with require_site_admin."""
    from api.admin_billing import admin_billing_bp
    from api.admin_trust import admin_trust_bp
    from api.dashboard_api import dashboard_bp

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda credential: {"valid": True, "reason": "ok"},
    )
    monkeypatch.setattr(
        "api.dashboard_api._load_admin_sites",
        lambda: [{"site_id": "site_test", "site_domain": "test.example.com", "plan": "starter", "status": "active"}],
    )
    monkeypatch.setattr("api.dashboard_api._get_slo_snapshot", lambda: {})
    monkeypatch.setattr("api.dashboard_api._site_block_counts", lambda site_id: {"active_blocks_count": 0, "pending_review_count": 0})
    monkeypatch.setattr("api.dashboard_api._site_activity_count", lambda site_id, domain: 0)
    monkeypatch.setattr("api.dashboard_api.get_monthly_active_users", lambda site_id: 0)
    monkeypatch.setattr("api.dashboard_api._lookup_stripe_customer_for_site", lambda site: "")

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_trust_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_billing_bp)

    with app.test_client() as client:
        for path in (
            "/api/admin/trust/queue",
            "/api/admin/trust/blocks",
            "/api/admin/trust/revocations",
            "/api/admin/ishuman-overview",
            "/api/admin/sites/site_test",
            "/api/admin/billing/summary",
        ):
            denied = client.get(path)
            assert denied.status_code == 401

            ok = client.get(path, headers={"X-Lemma-Credential": _encode_lemma_header(_stub_lemma("admin_access"))})
            assert ok.status_code == 200, path


def test_require_site_admin_rejects_missing_credential():
    """No credential header at all -> 401."""
    app = _app_with_site_admin_route()

    with app.test_client() as client:
        resp = client.get("/_test/admin")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "auth_required"
