"""Section 10 SDK productization tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(name="sdk_app")
def fixture_sdk_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    from api.sdk_serving import register_sdk_routes

    register_sdk_routes(app)
    return app


@pytest.fixture(name="sdk_client")
def fixture_sdk_client(sdk_app):
    with sdk_app.test_client() as client:
        yield client


def test_manifest_exists_and_matches_sdk_versions():
    from api.sdk_versions import (
        backend_verifier_version,
        browser_verifier_version,
        load_sdk_manifest,
        npm_package_version,
        pypi_package_version,
    )

    manifest = load_sdk_manifest()
    assert manifest["browser_verifier"] == browser_verifier_version()
    assert manifest["backend_verifier"] == backend_verifier_version()
    assert manifest["npm_package"] == npm_package_version()
    assert manifest["pypi_package"] == pypi_package_version()


def test_browser_sdk_version_in_source():
    from api.sdk_versions import browser_verifier_version

    source = (REPO_ROOT / "static/js/ishuman-verifier.js").read_text(encoding="utf-8")
    assert f"@version {browser_verifier_version()}" in source


def test_backend_sdk_version_in_source():
    from api.sdk_versions import backend_verifier_version

    source = (REPO_ROOT / "static/js/proof-verifier.mjs").read_text(encoding="utf-8")
    assert f"@version {backend_verifier_version()}" in source


def test_package_versions_match_manifest():
    from api.sdk_versions import npm_package_version, pypi_package_version

    pkg = json.loads((REPO_ROOT / "packages/proof-verifier-js/package.json").read_text(encoding="utf-8"))
    pyproject = (REPO_ROOT / "packages/proof-verifier-py/pyproject.toml").read_text(encoding="utf-8")
    assert pkg["version"] == npm_package_version()
    assert f'version = "{pypi_package_version()}"' in pyproject
    assert pkg["name"] == "@lemma.id/proof-verifier"
    assert 'name = "lemma-proof-verifier"' in pyproject


def test_sync_proof_verifier_packages_no_drift():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sync_proof_verifier_packages",
        REPO_ROOT / "scripts/sync_proof_verifier_packages.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.sync(check_only=True) is True


def test_versioned_browser_sdk_route(sdk_client):
    from api.sdk_versions import browser_verifier_version

    resp = sdk_client.get(f"/sdk/v{browser_verifier_version()}/proof-verifier.js")
    assert resp.status_code == 200
    assert "ProofVerifier" in resp.get_data(as_text=True)
    assert resp.headers.get("X-SDK-Version") == browser_verifier_version()
    assert "immutable" in resp.headers.get("Cache-Control", "")


def test_versioned_backend_sdk_route(sdk_client):
    from api.sdk_versions import backend_verifier_version

    resp = sdk_client.get(f"/sdk/v{backend_verifier_version()}/proof-verifier.mjs")
    assert resp.status_code == 200
    assert "createVerifier" in resp.get_data(as_text=True)
    assert resp.headers.get("X-SDK-Version") == backend_verifier_version()


def test_sdk_versions_api(sdk_client):
    resp = sdk_client.get("/api/sdk/versions")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["manifest"]["browser_verifier"]


def test_sri_includes_proof_verifier_assets():
    from api.sri_hashes import SDK_FILES

    assert "proof-verifier.js" in SDK_FILES
    assert "proof-verifier.mjs" in SDK_FILES


def test_flask_signup_example_fail_closed():
    import importlib.util
    import sys

    path = REPO_ROOT / "examples/flask_ishuman_signup/app.py"
    spec = importlib.util.spec_from_file_location("flask_signup_example", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["flask_signup_example"] = mod
    spec.loader.exec_module(mod)
    mod.app.config["TESTING"] = True
    client = mod.app.test_client()
    resp = client.post("/api/login", json={})
    assert resp.status_code == 400


def test_openapi_and_docs_present():
    assert (REPO_ROOT / "docs/api/ISHUMAN_RELYING_SITE.openapi.json").is_file()
    assert (REPO_ROOT / "docs/sdk/ISHUMAN_SDK_COMPATIBILITY_MATRIX.md").is_file()
    assert (REPO_ROOT / "docs/sdk/ISHUMAN_SDK_DEPRECATION_POLICY.md").is_file()
