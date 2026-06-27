from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS_PATH = ROOT / "static" / "js" / "lemma-wallet.js"
DEMO_JS_PATH = ROOT / "static" / "js" / "demo" / "ishuman-demo.js"

# Phase 2.1: the cross-origin wallet bridge iframe (templates/wallet_bridge.html),
# its /wallet/bridge route, and the /api/wallet/bridge-audit telemetry endpoint
# were removed. The postMessage origin-enforcement helper is retained because the
# same-origin lock listener still uses it, so the exact-origin guard is still
# guarded against the historical `.includes('lemma.id')` substring bypass.


@pytest.fixture(name="wallet_js_source")
def fixture_wallet_js_source() -> str:
    return WALLET_JS_PATH.read_text(encoding="utf-8")


@pytest.mark.unit
def test_lemma_wallet_uses_exact_origin_helper(wallet_js_source):
    assert "function isLemmaTrustedOrigin(origin)" in wallet_js_source
    assert "origin === 'https://lemma.id'" in wallet_js_source
    assert "isLemmaTrustedOrigin(event.origin)" in wallet_js_source
    # Regression guard: never fall back to substring origin matching.
    assert "event.origin.includes('lemma.id')" not in wallet_js_source


@pytest.mark.unit
def test_lemma_wallet_uses_exact_hostname_helper(wallet_js_source):
    assert "function isLemmaHostname(hostname)" in wallet_js_source
    assert "return isLemmaHostname(window.location.hostname)" in wallet_js_source
    assert "hostname.includes('lemma.id')" not in wallet_js_source


@pytest.mark.unit
def test_unlock_with_redirect_omits_enc_key_from_url(wallet_js_source):
    start = wallet_js_source.index("unlockWithRedirect(options = {})")
    end = wallet_js_source.index("    /**", start + 1)
    block = wallet_js_source[start:end]
    assert "enc_key" not in block
    assert "encKey" not in block


@pytest.mark.unit
def test_bridge_iframe_fully_removed(wallet_js_source):
    # The hidden cross-origin bridge iframe must never be created again.
    assert "/wallet/bridge" not in wallet_js_source
    # Phase 2.1 cleanup: the inert bridge plumbing was excised entirely.
    assert "_sendBridgeMessage" not in wallet_js_source
    assert "_syncToCentralWallet" not in wallet_js_source
    assert "_getFromCentralWallet" not in wallet_js_source

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "@app.route('/wallet/bridge')" not in app_source
    assert "/api/wallet/bridge-audit" not in app_source
    assert not (ROOT / "templates" / "wallet_bridge.html").exists()


@pytest.mark.unit
def test_demo_js_gates_test_verify_buttons():
    source = DEMO_JS_PATH.read_text(encoding="utf-8")
    assert "applyTestVerifyGate" in source
    assert "test_verify_enabled" in source
    # Operator-only controls stay hidden unless staging test_verify is enabled.
    assert "ih-operator-console" in source
    assert "operatorConsole.hidden" in source
    assert "ih-start-idv-btn" in source
    assert "el.hidden" in source
