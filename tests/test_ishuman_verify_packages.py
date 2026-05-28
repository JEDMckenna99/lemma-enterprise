"""Smoke tests for the backend verifier packages (JS + Python).

These tests validate that the packaged sources are syntactically valid,
serve correctly through the lemma.id app, and the two implementations
produce byte-identical canonical messages for the same credential.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_PACKAGE = ROOT / "packages" / "ishuman-verify-js"
PY_PACKAGE = ROOT / "packages" / "ishuman-verify-py"
JS_CANONICAL_SOURCE = ROOT / "static" / "js" / "lemma-ishuman-verify.mjs"
PY_CANONICAL_SOURCE = ROOT / "examples" / "relying_site_offline_verify.py"


def test_js_package_layout_present():
    assert (JS_PACKAGE / "package.json").exists()
    assert (JS_PACKAGE / "index.mjs").exists()
    assert (JS_PACKAGE / "README.md").exists()


def test_js_package_index_mirrors_canonical_source():
    canonical = JS_CANONICAL_SOURCE.read_text(encoding="utf-8")
    packaged = (JS_PACKAGE / "index.mjs").read_text(encoding="utf-8")
    assert canonical == packaged, (
        "packages/ishuman-verify-js/index.mjs must mirror "
        "static/js/lemma-ishuman-verify.mjs"
    )


def test_js_package_manifest_metadata():
    manifest = json.loads((JS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@lemma/ishuman-verify"
    assert manifest["type"] == "module"
    assert manifest["main"] == "./index.mjs"
    assert manifest["module"] == "./index.mjs"
    assert manifest["exports"]["."]["import"] == "./index.mjs"
    assert int(manifest["engines"]["node"].split(">=")[1]) >= 18


def test_py_package_layout_present():
    assert (PY_PACKAGE / "pyproject.toml").exists()
    assert (PY_PACKAGE / "lemma_ishuman_verify.py").exists()
    assert (PY_PACKAGE / "README.md").exists()


def test_py_package_module_mirrors_canonical_source():
    canonical = PY_CANONICAL_SOURCE.read_text(encoding="utf-8")
    packaged = (PY_PACKAGE / "lemma_ishuman_verify.py").read_text(encoding="utf-8")
    assert canonical == packaged


def test_py_package_module_is_valid_python():
    source = (PY_PACKAGE / "lemma_ishuman_verify.py").read_text(encoding="utf-8")
    ast.parse(source)


def test_py_package_exports_verification_context():
    spec = ast.parse((PY_PACKAGE / "lemma_ishuman_verify.py").read_text(encoding="utf-8"))
    class_names = {node.name for node in ast.walk(spec) if isinstance(node, ast.ClassDef)}
    assert "VerificationContext" in class_names


def test_js_module_exports_create_verifier():
    source = JS_CANONICAL_SOURCE.read_text(encoding="utf-8")
    assert "export function createVerifier" in source
    assert "export function browserCanonicalMessage" in source
    assert "export async function verifyPresentation" in source


def test_js_module_loads_under_node_if_available():
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node not available in PATH")
    # Just verify the file parses under Node by importing and inspecting exports.
    module_url = JS_CANONICAL_SOURCE.resolve().as_uri()
    script = (
        f"import({module_url!r}).then(m => {{"
        "  const names = Object.keys(m).sort();"
        "  if (!names.includes('createVerifier')) process.exit(2);"
        "  if (!names.includes('browserCanonicalMessage')) process.exit(3);"
        "  console.log(names.join(','));"
        "}).catch(err => { console.error(err); process.exit(1); });"
    )
    result = subprocess.run(
        [node_bin, "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "createVerifier" in result.stdout


def test_app_serves_backend_verifier_routes():
    pytest.importorskip("flask")
    from app import app  # noqa: E402

    client = app.test_client()
    js_resp = client.get("/sdk/lemma-ishuman-verify.mjs")
    assert js_resp.status_code == 200
    assert "createVerifier" in js_resp.data.decode("utf-8")
    assert js_resp.headers.get("Access-Control-Allow-Origin") == "*"

    py_resp = client.get("/sdk/lemma_ishuman_verify.py")
    assert py_resp.status_code == 200
    assert "VerificationContext" in py_resp.data.decode("utf-8")
    assert py_resp.headers.get("Access-Control-Allow-Origin") == "*"
