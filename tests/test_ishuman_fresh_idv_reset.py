"""Regression test for the demo fresh-IDV revocation reset flow.

Pins:
1. The demo helper `_clear_wallet_revocations_for_demo` exists, has the right
   signature, and is wired into `verify-once-test-mode` via `reset_revocations`.
2. The SDK forces a Bloom snapshot refresh after the popup returns from a
   fresh-IDV flow so the newly-issued credential isn't blocked by a stale
   snapshot still containing the cleared revocations.
3. The verifier supports `_syncBloom({ force: true })` to bypass the cached
   staleness window.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_JS = ROOT / "static" / "js" / "ishuman-verifier.js"
ISHUMAN_DEMO_PY = ROOT / "api" / "ishuman_demo.py"


@pytest.fixture(name="verifier_source")
def fixture_verifier_source() -> str:
    return VERIFIER_JS.read_text(encoding="utf-8")


@pytest.fixture(name="demo_source")
def fixture_demo_source() -> str:
    return ISHUMAN_DEMO_PY.read_text(encoding="utf-8")


@pytest.mark.browser
def test_verifier_force_bloom_refresh_after_fresh_idv(verifier_source):
    """After the popup returns from fresh_idv, the SDK must force a Bloom
    refresh before validating the new credential — otherwise the cached
    pre-reset snapshot would still flag the (same) PPID as revoked."""
    assert "_syncBloom({ force: true })" in verifier_source
    assert "fresh_idv_complete" in verifier_source
    assert "wasFreshIdv" in verifier_source
    # The _syncBloom signature must accept a force option.
    assert "_syncBloom(options = {})" in verifier_source
    assert "const force = !!options.force;" in verifier_source


def test_demo_test_mode_resets_revocations(demo_source):
    """The demo /api/demo/ishuman/verify-once-test-mode endpoint must clear
    prior revocation state for the wallet when reset_revocations is true so
    the user can re-enter sites that previously blocked them."""
    assert "_clear_wallet_revocations_for_demo" in demo_source
    assert "reset_revocations = bool(body.get(\"reset_revocations\", True))" in demo_source
    assert "revocation_reset" in demo_source


def test_clear_wallet_revocations_helper_signature(demo_source):
    """Helper must drop RevocationList wallet/credential/user entries AND
    deactivate the corresponding SiteBlock rows AND invalidate the Bloom
    cache, so the next bloom-filter fetch reflects the cleared state."""
    tree = ast.parse(demo_source)
    func = next(
        (
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_clear_wallet_revocations_for_demo"
        ),
        None,
    )
    assert func is not None, "helper missing"
    source = ast.get_source_segment(demo_source, func) or ""
    assert "RevocationList" in source
    assert "SiteBlock" in source
    assert "DerivedCredential" in source
    assert "invalidate_bloom_filter_cache" in source
    assert "revocation_type == \"wallet\"" in source
    assert "revocation_type == \"credential\"" in source
    assert "revocation_type == \"user\"" in source


def test_demo_helper_returns_counts(demo_source):
    """Caller must be able to surface how many entries were cleared."""
    assert "\"cleared_revocation_entries\"" in demo_source
    assert "\"cleared_site_blocks\"" in demo_source
    assert "\"reactivated_derived_credentials\"" in demo_source
