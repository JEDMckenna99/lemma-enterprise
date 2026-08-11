"""Monorepo smoke: oss/ protocol fixtures stay aligned with canonical packages."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
OSS_FIXTURES = REPO_ROOT / "oss" / "fixtures" / "protocol"
PY_PKG = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"


@pytest.fixture
def py_mod():
    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_oss_smoke", PY_PKG)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_oss_trust_list_fixture_rejects_unpinned_signer(py_mod):
    data = json.loads((OSS_FIXTURES / "trust_list_unpinned_signer.json").read_text(encoding="utf-8"))
    with pytest.raises(RuntimeError) as exc:
        py_mod._verify_signed_trust_list_payload(  # noqa: SLF001
            data["trust_list"],
            network_root_pubkeys=data["pinned_roots_hex"],
            now_unix=1700000100,
        )
    assert str(exc.value) == data["expected_reason"]


def test_oss_assurance_fixture_matches_package(py_mod):
    data = json.loads((OSS_FIXTURES / "assurance_policy_parity.json").read_text(encoding="utf-8"))
    for case in data["cases"]:
        assert py_mod.assurance_meets_policy(case["actual"] or None, case["required"]) is case["expected"]
