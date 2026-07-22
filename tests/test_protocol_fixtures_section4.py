"""Section 4 cross-verifier protocol fixtures and negative vectors."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_MODULE = REPO_ROOT / "static" / "js" / "proof-verifier.mjs"
PY_MODULE = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"


@pytest.fixture(autouse=True)
def _allow_unpinned_trust_root(monkeypatch):
    monkeypatch.setenv("LEMMA_ALLOW_UNPINNED_TRUST_ROOT", "1")


@pytest.fixture
def py_verify_module():
    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_section4", PY_MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pinned_trust_list(monkeypatch):
    from api.wallet_keys import derive_wallet_signing_keypair

    private_key, public_key = derive_wallet_signing_keypair("ef" * 32)
    pubkey_hex = public_key.public_bytes_raw().hex()

    def _material():
        return private_key, public_key, "did:lemma:" + ("b" * 64)

    monkeypatch.setattr("api.bloom_snapshot._issuer_signing_material", _material)
    monkeypatch.setenv("LEMMA_NETWORK_ROOT_PUBKEYS", pubkey_hex)

    from api.issuer_trust_list import build_signed_trust_list

    return build_signed_trust_list()


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
        "    console.error(err);\n"
        "    process.exit(1);\n"
        "  }\n"
        "});\n"
    )
    return subprocess.run(
        [node_bin, "-e", wrapped],
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_browser_canonical_v2_includes_credential_id(py_verify_module):
    from api.ishuman import _browser_canonical_message

    credential = {
        "id": "ishuman_site_fixture_001",
        "issuer": "did:lemma:issuer:test",
        "subject": "did:lemma:ppid_abc",
        "claims": {
            "assurance": "ishuman",
            "isHuman": True,
            "siteId": "example.com",
            "issuedAt": "1700000000",
            "expiresAt": "4102444800",
        },
    }
    expected = (
        b'{"issuer":"did:lemma:issuer:test","subject":"did:lemma:ppid_abc",'
        b'"claims":{"assurance":"ishuman","expiresAt":"4102444800","isHuman":"true",'
        b'"issuedAt":"1700000000","siteId":"example.com"},'
        b'"id":"ishuman_site_fixture_001"}'
    )
    assert _browser_canonical_message(credential) == expected
    assert py_verify_module.browser_canonical_message(credential) == expected


def test_assurance_monotonic_across_python_and_node(py_verify_module):
    assert py_verify_module.assurance_meets_policy("ishuman", "passkey") is True
    assert py_verify_module.assurance_meets_policy("passkey", "ishuman") is False

    result = _node_eval(
        "const ok = m.assuranceMeetsPolicy('ishuman', 'passkey');"
        "const bad = m.assuranceMeetsPolicy('passkey', 'ishuman');"
        "if (!ok || bad) process.exit(2);"
        "console.log('ok');"
    )
    assert result.returncode == 0, result.stderr


def test_trust_list_pin_rejects_self_signed_python_and_server(pinned_trust_list):
    from api.wallet_keys import derive_wallet_signing_keypair
    from api.issuer_trust_list import verify_signed_trust_list

    _, attacker_pub = derive_wallet_signing_keypair("aa" * 32)
    forged = dict(pinned_trust_list)
    forged["signer_pubkey"] = attacker_pub.public_bytes_raw().hex()
    forged["signature"] = pinned_trust_list["signature"]

    ok, reason = verify_signed_trust_list(forged)
    assert not ok
    assert reason == "trust_list_signer_not_pinned"


def test_required_credential_fields_fail_closed(py_verify_module):
    base = {
        "id": "ishuman_site_x",
        "issuer": "did:lemma:issuer",
        "subject": "did:lemma:ppid_x",
        "claims": {
            "assurance": "ishuman",
            "siteId": "example.com",
            "issuedAt": "1",
            "expiresAt": "9",
        },
        "proof": {"signatureValueWeb": "aa" * 64},
    }
    assert py_verify_module.validate_credential_required_fields(base) is None

    missing_id = dict(base)
    missing_id.pop("id")
    assert py_verify_module.validate_credential_required_fields(missing_id) == "credential_id_missing"

    tampered_site = json.loads(json.dumps(base))
    tampered_site["claims"]["siteId"] = "evil.example"
    assert py_verify_module.validate_credential_required_fields(tampered_site) is None


def test_signed_trust_list_round_trip_python_server(pinned_trust_list):
    from api.issuer_trust_list import verify_signed_trust_list

    ok, reason = verify_signed_trust_list(pinned_trust_list)
    assert ok, reason


def test_node_browser_canonical_matches_python(py_verify_module):
    credential = {
        "id": "ishuman_site_node_pin",
        "issuer": "did:lemma:issuer:test",
        "subject": "did:lemma:ppid_abc",
        "claims": {
            "assurance": "ishuman",
            "isHuman": True,
            "siteId": "example.com",
            "issuedAt": "1700000000",
            "expiresAt": "4102444800",
        },
    }
    py_bytes = py_verify_module.browser_canonical_message(credential)
    cred_json = json.dumps(credential)
    result = _node_eval(
        f"const cred = {cred_json};"
        "const bytes = m.browserCanonicalMessage(cred);"
        "const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');"
        f"if (hex !== '{py_bytes.hex()}') process.exit(2);"
        "console.log('match');"
    )
    assert result.returncode == 0, result.stderr
    assert "match" in result.stdout
