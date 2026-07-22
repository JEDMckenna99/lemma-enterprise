"""Contract tests for isHuman verify SDK hostname normalization and defaults."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY_SDK_PATH = ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
MJS_PATH = ROOT / "static" / "js" / "proof-verifier.mjs"
VERIFIER_JS = ROOT / "static" / "js" / "ishuman-verifier.js"

from tests.test_ishuman_ppid_normalization import SITE_HOSTNAME_VECTORS


def _load_py_sdk():
    pytest.importorskip("cryptography")
    name = "lemma_proof_verifier_contract"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PY_SDK_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
@pytest.mark.parametrize(("raw_host", "expected"), SITE_HOSTNAME_VECTORS)
def test_py_sdk_canonicalize_site_hostname_vectors(raw_host, expected):
    mod = _load_py_sdk()
    assert mod.canonicalize_site_hostname(raw_host) == expected


@pytest.mark.unit
def test_py_sdk_rejects_internal_site_id():
    mod = _load_py_sdk()
    with pytest.raises(Exception, match="internal_site_id_not_allowed"):
        mod.canonicalize_site_hostname("site_abc123def456")


@pytest.mark.unit
def test_verification_context_canonicalizes_configured_site_id():
    mod = _load_py_sdk()
    ctx = mod.VerificationContext(site_id="https://WWW.Example.com/login")
    assert ctx.site_id == "example.com"


@pytest.mark.unit
def test_verification_context_bound_site_variants_match_configured_site():
    mod = _load_py_sdk()
    ctx = mod.VerificationContext(site_id="example.com")
    for variant in (
        "EXAMPLE.COM",
        "https://www.example.com/path",
        "example.com:8443",
    ):
        bound, err = mod.try_canonicalize_site_hostname(variant)
        assert err is None
        assert bound == ctx.site_id


@pytest.mark.unit
def test_mjs_exports_site_hostname_and_policy_store_helpers():
    src = MJS_PATH.read_text(encoding="utf-8")
    assert "export function canonicalizeSiteHostname(value)" in src
    assert "export function createLemmaCheckPolicyStore({" in src
    assert "createLemmaCheckPolicyStore," in src


@pytest.mark.unit
def test_mjs_create_verifier_canonicalizes_site_id():
    src = MJS_PATH.read_text(encoding="utf-8")
    assert "const canonicalSiteId = canonicalizeSiteHostname(siteId);" in src
    assert "boundSite !== canonicalSiteId" in src


@pytest.mark.unit
def test_verifier_sdk_contract_source_patterns():
    src = VERIFIER_JS.read_text(encoding="utf-8")
    popup_reasons = src.split("const popupReasons = new Set([", 1)[1].split("]);", 1)[0]
    assert "'revoked'," in popup_reasons
    assert "'invalid_signature'," not in popup_reasons
    assert "REVOCATION_SNAPSHOT_UPDATE" in src
    assert "NETWORK_REVOCATION" not in src
    assert "return { blocked: true, doubtRequired: false };" in src
    assert "this.siteId = this._canonicalizeSiteId(rawSiteId);" in src


@pytest.mark.unit
def test_browser_verifier_exports_current_and_legacy_names():
    src = VERIFIER_JS.read_text(encoding="utf-8")
    assert "class ProofVerifier {" in src
    assert "window.ProofVerifier = ProofVerifier;" in src
    assert "window.IsHumanVerifier = ProofVerifier;" in src
    assert "module.exports = ProofVerifier;" in src
