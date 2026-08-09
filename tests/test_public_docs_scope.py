"""Public documentation exposes only the approved relying-site contract."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_legacy_agent_docs_redirect_to_ishuman_docs(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        for path in (
            "/docs/agents",
            "/docs/overview",
            "/docs/quickstart",
            "/docs/installation",
            "/docs/cli",
            "/docs/api/auth",
            "/docs/examples",
        ):
            response = client.get(path, follow_redirects=True)
            assert response.status_code == 200
            assert response.request.path == "/docs"
            assert b"private proof layer" in response.data.lower() or b"ishuman" in response.data.lower()


@pytest.mark.integration
def test_public_doc_allowlist_serves_approved_markdown(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        for path in (
            "/docs/integration/CONTINUITY_AND_ABUSE.md",
            "/docs/integration/ISHUMAN_AGENT_INTEGRATION.md",
            "/docs/integration/QUICK_START_SIMPLE_LOGIN.md",
            "/docs/integration/SIMPLE_INTEGRATION_GUIDE.md",
            "/docs/integration/SIGN_IN_TRUST_AND_RECOVERY.md",
            "/docs/integration/BROWSER_SUPPORT.md",
            "/docs/ERROR_CODES.md",
            "/docs/demo/README.md",
            "/docs/demo/PRESALE_DEMO_SCRIPT.md",
            "/docs/product/PASSKEY_STAMP_INPUT_BURN.md",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.mimetype.startswith("text/markdown")
            assert len(response.data) > 100


@pytest.mark.integration
def test_public_developer_docs_use_current_safe_integration_contract(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        error_reference = client.get("/docs/ERROR_CODES.md")
        docs_home = client.get("/docs")

    assert error_reference.status_code == 200
    assert b"ProofVerifier" in error_reference.data
    assert b"verifyForBackend" in error_reference.data
    assert b"LemmaAuth" not in error_reference.data
    assert b"sendLoginEmail" not in error_reference.data
    assert b"90-day" not in error_reference.data
    assert b"bare client PPID" in error_reference.data

    assert docs_home.status_code == 200
    assert b"signed <code>presentation</code>" in docs_home.data
    assert b"client sends you the <code>ppid</code>" not in docs_home.data


@pytest.mark.integration
def test_public_doc_allowlist_denies_internal_paths(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        denied = (
            "/docs/operations/ENVIRONMENT_CONFIG.md",
            "/docs/security/THREAT_MODEL.md",
            "/docs/product/COMPARTMENTALIZED_PERSONAS.md",
            "/docs/AGENT_OPS_READINESS.md",
            "/docs/integration/IAM_ONLY_INTEGRATION_GUIDE.md",
            "/docs/integration/INTEGRATION_GUIDE.md",
            "/docs/operations/INTERNAL_COGS_ESTIMATE.csv",
            "/docs/README.md",
        )
        for path in denied:
            response = client.get(path)
            assert response.status_code == 404, path


@pytest.mark.integration
def test_public_doc_allowlist_blocks_traversal_variants(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        traversal_paths = (
            "/docs/../operations/ENVIRONMENT_CONFIG.md",
            "/docs/integration/../../operations/ENVIRONMENT_CONFIG.md",
            "/docs/integration/%2e%2e/operations/ENVIRONMENT_CONFIG.md",
            "/docs/.hidden.md",
        )
        for path in traversal_paths:
            response = client.get(path)
            assert response.status_code == 404, path


@pytest.mark.integration
def test_llms_txt_is_served(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        response = client.get("/llms.txt")
        assert response.status_code == 200
        assert b"CONTINUITY_AND_ABUSE.md" in response.data
        assert b"ISHUMAN_AGENT_INTEGRATION.md" in response.data
        assert b"proof-verifier.js" in response.data
        assert b"ishuman-verifier.js" in response.data
        # Proof-layer-first contract: llms.txt steers agents to gate actions and
        # local verify, not login-only integration.
        assert b"QUICK_START_SIMPLE_LOGIN.md" in response.data
        assert b"verifyForBackend" in response.data
        assert b"local-first proof layer" in response.data.lower()


@pytest.mark.integration
def test_browser_verifier_current_and_legacy_urls_match(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        current = client.get("/sdk/proof-verifier.js")
        legacy = client.get("/sdk/ishuman-verifier.js")

    assert current.status_code == 200
    assert legacy.status_code == 200
    assert current.data == legacy.data
    assert current.headers["X-SDK-Version"] == legacy.headers["X-SDK-Version"]


def test_public_doc_path_normalization_unit():
    from api.public_docs import is_public_doc_allowed, normalize_public_doc_path

    assert normalize_public_doc_path("integration/ISHUMAN_AGENT_INTEGRATION.md") == (
        "integration/ISHUMAN_AGENT_INTEGRATION.md"
    )
    assert normalize_public_doc_path("integration\\ISHUMAN_AGENT_INTEGRATION.md") == (
        "integration/ISHUMAN_AGENT_INTEGRATION.md"
    )
    assert normalize_public_doc_path("../operations/ENVIRONMENT_CONFIG.md") is None
    assert normalize_public_doc_path("integration/../../operations/ENVIRONMENT_CONFIG.md") is None

    allowed, normalized = is_public_doc_allowed("integration/ISHUMAN_AGENT_INTEGRATION.md")
    assert allowed is True
    assert normalized == "integration/ISHUMAN_AGENT_INTEGRATION.md"

    allowed, _ = is_public_doc_allowed("operations/ENVIRONMENT_CONFIG.md")
    assert allowed is False
