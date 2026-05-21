from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_env_parity import parse_env_lines, validate  # noqa: E402


@pytest.fixture(name="ishuman_demo_client")
def fixture_ishuman_demo_client(monkeypatch):
    from api.ishuman_demo import ishuman_demo_bp

    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_demo_bp)
    with app.test_client() as client:
        yield client


def _base_env(**overrides):
    env = {
        "SECRET_KEY": "secret-value-32-bytes-long",
        "FLASK_ENV": "production",
        "ENVIRONMENT": "staging",
        "LEMMA_BASE_URL": "https://staging.example",
        "DATABASE_URL": "postgresql://example",
        "REDIS_URL": "redis://example",
        "LEMMA_PPID_ROOT_KEY": "x" * 32,
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_IDENTITY_WEBHOOK_SECRET": "whsec_123",
        "ISHUMAN_RETURN_URL": "https://staging.example/demo/ishuman?verification_return=true",
        "AWS_REGION": "us-east-1",
        "LEMMA_KMS_KEY_ID": "kms-staging",
        "LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY": "true",
        "LEMMA_ISHUMAN_DEMO_TEST_TOKEN": "demo-token",
    }
    env.update(overrides)
    return env


def test_parse_env_lines_ignores_comments_and_preserves_values():
    env = parse_env_lines([
        "# comment",
        "STRIPE_SECRET_KEY=sk_test_123",
        "EMPTY=",
        "QUOTED=\"value=with=equals\"",
    ])

    assert env["STRIPE_SECRET_KEY"] == "sk_test_123"
    assert env["EMPTY"] == ""
    assert env["QUOTED"] == "value=with=equals"


def test_staging_allows_test_keys_with_guarded_demo_helper():
    errors, warnings = validate(_base_env(), "staging")

    assert errors == []
    assert warnings == []


def test_staging_rejects_live_stripe_key():
    errors, _warnings = validate(_base_env(STRIPE_SECRET_KEY="sk_live_123"), "staging")

    assert any("must start with sk_test_" in err for err in errors)
    assert any("Test verification helper can only" in err for err in errors)


def test_production_rejects_demo_test_helper():
    env = _base_env(
        ENVIRONMENT="production",
        STRIPE_SECRET_KEY="sk_live_123",
        LEMMA_BASE_URL="https://lemma.id",
        ISHUMAN_RETURN_URL="https://lemma.id/demo/ishuman?verification_return=true",
        LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY="true",
    )
    errors, _warnings = validate(env, "production")

    assert any("must not enable" in err for err in errors)


def test_verify_once_runtime_requires_demo_token_header(ishuman_demo_client, monkeypatch):
    """Runtime guard: verify-once must require X-Demo-Test-Token when test mode is enabled."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY", "true")
    monkeypatch.setenv("LEMMA_ISHUMAN_DEMO_TEST_TOKEN", "parity-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")

    resp = ishuman_demo_client.post(
        "/api/demo/ishuman/verify-once-test-mode",
        json={"wallet_id": "wallet_demo_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403
    assert payload["error"] == "demo_test_token_required"


def test_production_accepts_live_key_and_disabled_test_helper():
    env = _base_env(
        ENVIRONMENT="production",
        STRIPE_SECRET_KEY="sk_live_123",
        LEMMA_BASE_URL="https://lemma.id",
        ISHUMAN_RETURN_URL="https://lemma.id/demo/ishuman?verification_return=true",
        LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY="false",
        LEMMA_ISHUMAN_DEMO_TEST_TOKEN="",
        LEMMA_ISHUMAN_DEMO_ADMIN_TOKEN="",
        LEMMA_KMS_KEY_ID="kms-prod",
    )
    errors, warnings = validate(env, "production")

    assert errors == []
    assert warnings == []
