"""Versioned and mutable SDK asset serving (Section 10)."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from api.sdk_versions import (
    backend_verifier_version,
    browser_verifier_version,
    load_sdk_manifest,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _attach_sdk_headers(response, *, version: str, immutable: bool = False):
    if immutable:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    response.headers["X-SDK-Version"] = version
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def register_sdk_routes(app: Flask) -> None:
    browser_v = browser_verifier_version()
    backend_v = backend_verifier_version()

    @app.route("/sdk/proof-verifier.js")
    @app.route("/sdk/ishuman-verifier.js")
    def proof_verifier_sdk():
        response = send_from_directory(
            str(_REPO_ROOT / "static/js"),
            "ishuman-verifier.js",
            mimetype="application/javascript",
        )
        return _attach_sdk_headers(response, version=browser_v, immutable=False)

    @app.route("/sdk/proof-verifier.mjs")
    @app.route("/sdk/lemma-ishuman-verify.mjs")
    def proof_verifier_backend_sdk():
        response = send_from_directory(
            str(_REPO_ROOT / "static/js"),
            "proof-verifier.mjs",
            mimetype="application/javascript",
        )
        response.headers["Cache-Control"] = "public, max-age=300"
        return _attach_sdk_headers(response, version=backend_v, immutable=False)

    @app.route("/sdk/proof-verifier.py")
    @app.route("/sdk/lemma_ishuman_verify.py")
    def proof_verifier_python_sdk():
        response = send_from_directory(
            str(_REPO_ROOT / "examples"),
            "proof-verifier.py",
            mimetype="text/x-python",
        )
        response.headers["Cache-Control"] = "public, max-age=300"
        return _attach_sdk_headers(response, version=backend_v, immutable=False)

    @app.route(f"/sdk/v{browser_v}/proof-verifier.js")
    @app.route(f"/sdk/v{browser_v}/ishuman-verifier.js")
    def proof_verifier_sdk_versioned():
        response = send_from_directory(
            str(_REPO_ROOT / "static/js"),
            "ishuman-verifier.js",
            mimetype="application/javascript",
        )
        return _attach_sdk_headers(response, version=browser_v, immutable=True)

    @app.route(f"/sdk/v{backend_v}/proof-verifier.mjs")
    @app.route(f"/sdk/v{backend_v}/lemma-ishuman-verify.mjs")
    def proof_verifier_backend_sdk_versioned():
        response = send_from_directory(
            str(_REPO_ROOT / "static/js"),
            "proof-verifier.mjs",
            mimetype="application/javascript",
        )
        return _attach_sdk_headers(response, version=backend_v, immutable=True)

    @app.route(f"/sdk/v{backend_v}/proof-verifier.py")
    @app.route(f"/sdk/v{backend_v}/lemma_ishuman_verify.py")
    def proof_verifier_python_sdk_versioned():
        response = send_from_directory(
            str(_REPO_ROOT / "examples"),
            "proof-verifier.py",
            mimetype="text/x-python",
        )
        return _attach_sdk_headers(response, version=backend_v, immutable=True)

    @app.route("/api/sdk/versions")
    def sdk_versions_manifest():
        manifest = load_sdk_manifest()
        return jsonify({"success": True, "manifest": manifest}), 200
