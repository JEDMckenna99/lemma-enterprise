"""Smoke tests for the backend verifier packages (JS + Python)."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
JS_PACKAGE = ROOT / "packages" / "proof-verifier-js"
PY_PACKAGE = ROOT / "packages" / "proof-verifier-py"
JS_CANONICAL_SOURCE = ROOT / "static" / "js" / "proof-verifier.mjs"
PY_CANONICAL_SOURCE = ROOT / "examples" / "proof-verifier.py"


def test_js_package_layout_present():
    assert (JS_PACKAGE / "package.json").exists()
    assert (JS_PACKAGE / "index.mjs").exists()
    assert (JS_PACKAGE / "README.md").exists()


def test_js_package_index_mirrors_canonical_source():
    canonical = JS_CANONICAL_SOURCE.read_text(encoding="utf-8")
    packaged = (JS_PACKAGE / "index.mjs").read_text(encoding="utf-8")
    assert canonical == packaged


def test_js_package_manifest_metadata():
    manifest = json.loads((JS_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "@lemma/proof-verifier"
    assert manifest["type"] == "module"
    assert manifest["main"] == "./index.mjs"


def test_py_package_layout_present():
    assert (PY_PACKAGE / "pyproject.toml").exists()
    assert (PY_PACKAGE / "lemma_proof_verifier.py").exists()


def test_py_package_module_mirrors_canonical_source():
    canonical = PY_CANONICAL_SOURCE.read_text(encoding="utf-8")
    packaged = (PY_PACKAGE / "lemma_proof_verifier.py").read_text(encoding="utf-8")
    assert canonical == packaged


def test_py_package_module_is_valid_python():
    source = (PY_PACKAGE / "lemma_proof_verifier.py").read_text(encoding="utf-8")
    ast.parse(source)


def test_py_package_exports_verification_context():
    spec = ast.parse((PY_PACKAGE / "lemma_proof_verifier.py").read_text(encoding="utf-8"))
    class_names = {node.name for node in ast.walk(spec) if isinstance(node, ast.ClassDef)}
    assert "VerificationContext" in class_names


def test_js_module_exports_create_verifier():
    source = JS_CANONICAL_SOURCE.read_text(encoding="utf-8")
    assert "export function createVerifier" in source


def test_js_module_loads_under_node_if_available():
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node not available in PATH")
    module_url = JS_CANONICAL_SOURCE.resolve().as_uri()
    script = (
        f"import({module_url!r}).then(m => {{"
        "  if (!Object.keys(m).includes('createVerifier')) process.exit(2);"
        "  console.log('ok');"
        "}).catch(err => { console.error(err); process.exit(1); });"
    )
    result = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_app_serves_backend_verifier_routes():
    pytest.importorskip("flask")
    from app import app  # noqa: E402

    client = app.test_client()
    js_resp = client.get("/sdk/proof-verifier.mjs")
    assert js_resp.status_code == 200
    py_resp = client.get("/sdk/proof-verifier.py")
    assert py_resp.status_code == 200
    assert client.get("/sdk/lemma-ishuman-verify.mjs").status_code == 200
    assert client.get("/sdk/lemma_ishuman_verify.py").status_code == 200
