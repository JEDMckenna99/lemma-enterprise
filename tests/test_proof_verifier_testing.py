"""Tests for offline proof-verifier test helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_TESTING = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier_testing.py"
JS_TESTING = REPO_ROOT / "packages" / "proof-verifier-js" / "testing.mjs"


@pytest.fixture
def testing_module():
    py_verifier = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
    spec_main = importlib.util.spec_from_file_location("lemma_proof_verifier_testmod", py_verifier)
    main_mod = importlib.util.module_from_spec(spec_main)
    sys.modules[spec_main.name] = main_mod
    spec_main.loader.exec_module(main_mod)
    sys.modules["lemma_proof_verifier"] = main_mod

    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_testing", PY_TESTING)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_mint_and_verify_offline_passkey_presentation(testing_module):
    issuer = testing_module.mint_test_issuer()
    presentation = testing_module.mint_test_presentation(
        site_id="localhost",
        ppid="did:lemma:ppid_ci_user",
        assurance="passkey",
        issuer=issuer,
    )
    ctx = testing_module.create_offline_test_context(
        site_id="localhost",
        issuer_did=issuer["did"],
        issuer_pubkey_hex=issuer["pubkey_hex"],
        required_assurance="passkey",
    )
    result = ctx.verify(presentation)
    assert result.ok is True
    assert result.ppid == "did:lemma:ppid_ci_user"
    assert result.assurance == "passkey"


def test_lemma_signin_web_component_source():
    source = (REPO_ROOT / "static" / "js" / "lemma-signin.js").read_text(encoding="utf-8")
    assert "customElements.define('lemma-signin'" in source
    assert "lemma-signin-success" in source
    assert "verifyForBackend" in source
    assert "required-assurance" in source


def test_sdk_public_reason_normalization():
    source = (REPO_ROOT / "static" / "js" / "ishuman-verifier.js").read_text(encoding="utf-8")
    assert "_normalizePublicSdkReason" in source
    assert "passkey_unsupported" in source
    assert "popup_blocked" in source


def test_login_popup_copy_updated():
    source = (REPO_ROOT / "static" / "js" / "demo" / "ishuman-idv-preview-scenes.js").read_text(
        encoding="utf-8"
    )
    assert "Sign in to" in source
    assert "continuity proof" not in source


def test_js_testing_helper_roundtrip():
    import shutil
    import subprocess

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node not available")
    script = (
        "import('./packages/proof-verifier-js/testing.mjs').then(async (m) => {"
        "const issuer = await m.mintTestIssuer();"
        "const p = await m.mintTestPresentation({ siteId: 'localhost', ppid: 'did:lemma:ppid_test', assurance: 'passkey', issuer });"
        "const r = await m.verifyTestPresentationOffline({ presentation: p, siteId: 'localhost', requiredAssurance: 'passkey', trustedIssuerPubkeyHex: issuer.pubkeyHex });"
        "if (!r.ok) process.exit(2);"
        "console.log('ok');"
        "});"
    )
    result = subprocess.run([node_bin, "-e", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr or result.stdout
