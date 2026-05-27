from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"
VERIFIER_JS = ROOT / "static" / "js" / "ishuman-verifier.js"
BRIDGE_HTML = ROOT / "templates" / "wallet_bridge.html"
IDV_HTML = ROOT / "templates" / "wallet_ishuman_idv.html"
POPUP_HTML = ROOT / "templates" / "wallet_popup.html"


@pytest.fixture(name="wallet_source")
def fixture_wallet_source() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.fixture(name="verifier_source")
def fixture_verifier_source() -> str:
    return VERIFIER_JS.read_text(encoding="utf-8")


@pytest.fixture(name="bridge_source")
def fixture_bridge_source() -> str:
    return BRIDGE_HTML.read_text(encoding="utf-8")


@pytest.mark.browser
def test_wallet_ishuman_lock_bundle_constants(wallet_source):
    assert "ISHUMAN_LOCK_STORAGE_KEY = 'lemma_ishuman_lock:v1'" in wallet_source
    assert "isHumanIssuance" in wallet_source
    assert "ensureIsHumanIssuanceReady" in wallet_source
    assert "ishuman_cache" in wallet_source
    assert "WALLET_DB_VERSION = 6" in wallet_source


@pytest.mark.browser
def test_wallet_lock_bundle_persist_and_restore(wallet_source):
    assert "_persistIsHumanLockBundle" in wallet_source
    assert "_restoreIsHumanLockBundleIfValid" in wallet_source
    assert "_clearIsHumanLockBundle" in wallet_source
    assert "isIsHumanLockValid" in wallet_source


@pytest.mark.browser
def test_bridge_ishuman_issuance_probe(bridge_source):
    assert "probeIsHumanIssuanceReady" in bridge_source
    assert "getIsHumanCredentialsForBridge" in bridge_source
    assert "isHumanIssuance: !!payload?.isHumanIssuance" in bridge_source


@pytest.mark.browser
def test_verifier_site_vc_cache(verifier_source):
    assert "SITE_VC_STORAGE_KEY = 'ishuman_site_vc:v1'" in verifier_source
    assert "_verifyFromSiteVcCache" in verifier_source
    assert "'vc_valid'" in verifier_source
    assert "isHumanIssuance: true" in verifier_source


@pytest.mark.browser
def test_idv_popup_uses_ensure_ishuman_issuance():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "ensureIsHumanIssuanceReady" in idv_html


@pytest.mark.browser
def test_unlock_popup_ishuman_flag():
    popup_html = POPUP_HTML.read_text(encoding="utf-8")
    assert "isHumanIssuance" in popup_html
    assert "ishuman" in popup_html
