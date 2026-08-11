"""Cross-language protocol fixture harness for oss/ public surface."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

OSS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = OSS_ROOT / "fixtures" / "protocol"
PY_MODULE = OSS_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
JS_MODULE = OSS_ROOT / "packages" / "proof-verifier-js" / "index.mjs"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def py_mod():
    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_oss", PY_MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _node_eval(script: str) -> subprocess.CompletedProcess[str]:
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node not available in PATH")
    module_url = JS_MODULE.resolve().as_uri()
    wrapped = (
        "import(" + repr(module_url) + ").then(async (m) => {\n"
        "  try {\n"
        f"    {script}\n"
        "  } catch (err) {\n"
        "    console.error(err?.message || err);\n"
        "    process.exit(1);\n"
        "  }\n"
        "});\n"
    )
    return subprocess.run(
        [node_bin, "-e", wrapped],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(OSS_ROOT),
    )


def test_assurance_policy_parity(py_mod):
    data = _load_json("assurance_policy_parity.json")
    for case in data["cases"]:
        actual = case["actual"]
        required = case["required"]
        expected = case["expected"]
        py_result = py_mod.assurance_meets_policy(actual or None, required)
        assert py_result is expected, case

        actual_js = json.dumps(actual)
        required_js = json.dumps(required)
        expected_js = json.dumps(expected)
        result = _node_eval(
            f"const actual = {actual_js};"
            f"const required = {required_js};"
            f"const got = m.assuranceMeetsPolicy(actual, required);"
            f"if (got !== {expected_js}) process.exit(2);"
            "console.log('ok');"
        )
        assert result.returncode == 0, result.stderr


def test_browser_canonical_parity(py_mod):
    data = _load_json("browser_canonical_parity.json")
    credential = data["credential"]
    py_hex = py_mod.browser_canonical_message(credential).hex()
    cred_json = json.dumps(credential)
    result = _node_eval(
        f"const cred = {cred_json};"
        "const bytes = m.browserCanonicalMessage(cred);"
        "const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');"
        f"if (hex !== '{py_hex}') {{ console.error('py', '{py_hex}', 'js', hex); process.exit(2); }}"
        "console.log('match');"
    )
    assert result.returncode == 0, result.stderr
    assert "match" in result.stdout


def test_credential_required_fields_parity(py_mod):
    data = _load_json("credential_required_fields.json")
    for case in data["cases"]:
        label = case["label"]
        credential = case["credential"]
        expected = case["expected_reason"]
        py_reason = py_mod.validate_credential_required_fields(credential)
        assert py_reason == expected, label

        cred_json = json.dumps(credential)
        expected_js = json.dumps(expected)
        result = _node_eval(
            f"const cred = {cred_json};"
            f"const expected = {expected_js};"
            "const got = m.validateCredentialRequiredFields(cred);"
            "if (got !== expected) { console.error('got', got, 'expected', expected); process.exit(2); }"
            "console.log('ok');"
        )
        assert result.returncode == 0, f"{label}: {result.stderr}"


def test_trust_list_unpinned_signer_parity(py_mod):
    data = _load_json("trust_list_unpinned_signer.json")
    trust_list = data["trust_list"]
    pinned = data["pinned_roots_hex"]
    expected = data["expected_reason"]

    with pytest.raises(RuntimeError) as exc:
        py_mod._verify_signed_trust_list_payload(  # noqa: SLF001
            trust_list,
            network_root_pubkeys=pinned,
            now_unix=1700000100,
        )
    assert str(exc.value) == expected

    trust_json = json.dumps(trust_list)
    pinned_json = json.dumps(pinned)
    result = _node_eval(
        f"const trustList = {trust_json};"
        f"const pinned = {pinned_json};"
        "const nowSec = 1700000100;"
        "const TIME_SKEW_SECONDS = 300;"
        "function signerPubkeyIsPinned(signerPubkey, networkRootPubkeys) {"
        "  const normalized = String(signerPubkey || '').trim().toLowerCase();"
        "  if (!normalized || normalized.length !== 64) return false;"
        "  const pins = (networkRootPubkeys || []).map((p) => String(p).trim().toLowerCase());"
        "  return pins.includes(normalized);"
        "}"
        "if (!trustList || typeof trustList !== 'object') throw new Error('trust_list_missing');"
        "if (!signerPubkeyIsPinned(trustList.signer_pubkey, pinned)) {"
        f"  if ({json.dumps(expected)} !== 'trust_list_signer_not_pinned') process.exit(2);"
        "  console.log('ok');"
        "} else { process.exit(3); }"
    )
    assert result.returncode == 0, result.stderr
