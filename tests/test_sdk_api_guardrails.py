import types

from flask import Flask, jsonify, request

from api import sdk_api


def _build_guardrail_test_app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/_guardrail", methods=["GET"])
    @sdk_api.validate_api_key
    def _guardrail():
        return jsonify(
            {
                "ok": True,
                "api_key": getattr(request, "api_key", None),
                "api_key_info": getattr(request, "api_key_info", {}),
            }
        )

    app.register_blueprint(sdk_api.sdk_api_bp)
    return app


def test_validate_api_key_accepts_demo_only_when_explicit_non_prod(monkeypatch):
    app = _build_guardrail_test_app()
    monkeypatch.setattr(sdk_api, "_allow_sdk_demo_features", lambda: True)
    monkeypatch.setattr(sdk_api, "_is_non_prod_mode", lambda: True)

    with app.test_client() as client:
        response = client.get("/_guardrail", headers={"Authorization": "Bearer demo-abc"})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["api_key_info"]["type"] == "demo"


def test_validate_api_key_accepts_x_api_key_header_in_non_prod_demo(monkeypatch):
    app = _build_guardrail_test_app()
    monkeypatch.setattr(sdk_api, "_allow_sdk_demo_features", lambda: True)
    monkeypatch.setattr(sdk_api, "_is_non_prod_mode", lambda: True)

    with app.test_client() as client:
        response = client.get("/_guardrail", headers={"X-API-Key": "demo-abc"})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["api_key_info"]["type"] == "demo"


def test_validate_api_key_rejects_demo_in_production(monkeypatch):
    app = _build_guardrail_test_app()
    monkeypatch.setattr(sdk_api, "_allow_sdk_demo_features", lambda: True)
    monkeypatch.setattr(sdk_api, "_is_non_prod_mode", lambda: False)
    monkeypatch.setenv("LEMMA_PLATFORM_API_KEY", "")

    fake_customer_manager = types.SimpleNamespace(
        validate_api_key=lambda _key: {"valid": False, "error": "invalid"}
    )
    fake_module = types.SimpleNamespace(customer_manager=fake_customer_manager)
    monkeypatch.setitem(__import__("sys").modules, "api.customer_accounts", fake_module)

    with app.test_client() as client:
        response = client.get("/_guardrail", headers={"Authorization": "Bearer demo-abc"})
        assert response.status_code == 401
        payload = response.get_json()
        assert payload["error"] == "invalid_api_key"


def test_create_demo_identity_session_returns_success_shape():
    session = sdk_api.create_demo_identity_session(
        user_id="sdk_user_test",
        return_url="https://example.com/callback",
        inline_mode=True,
    )
    assert session["success"] is True
    assert session["demo_mode"] is True
    assert session["session_id"].startswith("didit_demo_")
    assert session["provider"] == "didit_demo"
    assert "client_secret" not in session
    assert "url" in session


def test_sdk_health_exposes_profile_guardrail_flags(monkeypatch):
    app = _build_guardrail_test_app()
    monkeypatch.setattr(sdk_api, "_is_non_prod_mode", lambda: False)
    monkeypatch.setattr(sdk_api, "_allow_sdk_demo_features", lambda: True)
    monkeypatch.setattr(sdk_api, "_get_network_registry_url", lambda: "")

    with app.test_client() as client:
        response = client.get("/api/sdk/health")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["environment_mode"] == "production"
        assert payload["demo_mode_enabled"] is False
        assert payload["network_registry_configured"] is False

