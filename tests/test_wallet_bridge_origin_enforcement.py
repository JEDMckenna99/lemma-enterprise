from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "templates" / "wallet_bridge.html"
WALLET_JS_PATH = ROOT / "static" / "js" / "lemma-wallet.js"
VERIFIER_JS_PATH = ROOT / "static" / "js" / "ishuman-verifier.js"
APP_PATH = ROOT / "app.py"
DEMO_JS_PATH = ROOT / "static" / "js" / "demo" / "ishuman-demo.js"


@pytest.fixture(name="wallet_bridge_source")
def fixture_wallet_bridge_source() -> str:
    return BRIDGE_PATH.read_text(encoding="utf-8")


@pytest.fixture(name="wallet_js_source")
def fixture_wallet_js_source() -> str:
    return WALLET_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(name="verifier_js_source")
def fixture_verifier_js_source() -> str:
    return VERIFIER_JS_PATH.read_text(encoding="utf-8")


@pytest.mark.unit
def test_bridge_message_handler_requires_parent_source(wallet_bridge_source):
    assert "event.source !== window.parent" in wallet_bridge_source
    assert "reportBridgeDenial('source_mismatch'" in wallet_bridge_source


@pytest.mark.unit
def test_bridge_uses_post_to_parent_with_known_origin(wallet_bridge_source):
    assert "function postToParent(message, forceWildcard)" in wallet_bridge_source
    assert "postToParent({" in wallet_bridge_source
    assert "bridge-audit" in wallet_bridge_source


@pytest.mark.unit
def test_lemma_wallet_uses_exact_origin_helper(wallet_js_source):
    assert "function isLemmaTrustedOrigin(origin)" in wallet_js_source
    assert "origin === 'https://lemma.id'" in wallet_js_source
    assert "isLemmaTrustedOrigin(event.origin)" in wallet_js_source
    assert "event.origin.includes('lemma.id')" not in wallet_js_source


@pytest.mark.unit
def test_lemma_wallet_validates_bridge_response_type(wallet_js_source):
    assert "response.type !== `${type}_response`" in wallet_js_source


@pytest.mark.unit
def test_ishuman_verifier_validates_bridge_source_and_type(verifier_js_source):
    assert "event.source !== this._bridgeIframe?.contentWindow" in verifier_js_source
    assert "expectedType: 'GET_CREDENTIAL_response'" in verifier_js_source
    assert "data.type !== expectedType" in verifier_js_source


@pytest.mark.unit
def test_wallet_bridge_route_headers_hardened():
    app_source = APP_PATH.read_text(encoding="utf-8")
    assert "X-Frame-Options': 'ALLOWALL'" not in app_source
    assert "'Referrer-Policy': 'no-referrer'" in app_source
    assert "/api/wallet/bridge-audit" in app_source


@pytest.mark.unit
def test_demo_js_gates_test_verify_buttons():
    source = DEMO_JS_PATH.read_text(encoding="utf-8")
    assert "applyTestVerifyGate" in source
    assert "test_verify_enabled" in source
    assert "ih-test-verify-disabled" in source
