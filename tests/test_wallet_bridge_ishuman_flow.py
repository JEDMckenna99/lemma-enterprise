from __future__ import annotations

from pathlib import Path

import pytest


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "templates" / "wallet_bridge.html"


@pytest.fixture(name="wallet_bridge_source")
def fixture_wallet_bridge_source() -> str:
    return BRIDGE_PATH.read_text(encoding="utf-8")


@pytest.mark.browser
def test_get_credential_uses_requesting_site_as_default(wallet_bridge_source):
    assert "const ihSite = payload?.siteId || requestingSite;" in wallet_bridge_source


@pytest.mark.browser
def test_get_credential_checks_site_bound_match_before_derivation(wallet_bridge_source):
    assert "let match = allCreds.find(c => {" in wallet_bridge_source
    assert "const boundSite = getCredentialSiteBinding(cl);" in wallet_bridge_source
    assert "return boundSite === ihSite;" in wallet_bridge_source
    # Match must also carry the browser-canonical signature so the verifier
    # can validate it locally; legacy creds are intentionally skipped.
    assert "matchHasBrowserSig" in wallet_bridge_source
    assert "match.claims?.site_signing_pubkey || match.credentialSubject?.site_signing_pubkey" in wallet_bridge_source
    assert "&& matchHasBrowserSig)" in wallet_bridge_source
    assert "const signed = await signPresentation(match);" in wallet_bridge_source
    assert "respond({ success: true, ...signed });" in wallet_bridge_source


@pytest.mark.browser
def test_get_credential_requires_master_when_site_credential_missing(wallet_bridge_source):
    assert "const master = allCreds.find(c => {" in wallet_bridge_source
    assert "return cl.isHuman && (boundSite === 'lemma.id' || !boundSite);" in wallet_bridge_source
    assert "respond({ success: false, error: 'no_ishuman_credential' });" in wallet_bridge_source


@pytest.mark.browser
def test_bridge_refuses_legacy_cached_credentials_without_browser_signature(wallet_bridge_source):
    """Legacy isHuman credentials lacking proof.signatureValueWeb cannot be
    verified by the browser verifier; the bridge must treat them as missing
    and force a popup re-issue against the upgraded issuer."""
    assert "matchHasBrowserSig" in wallet_bridge_source
    assert "sessionMatchHasBrowserSig" in wallet_bridge_source
    assert "signatureValueWeb" in wallet_bridge_source


@pytest.mark.browser
def test_get_session_presentation_returns_site_proof_required_when_site_credential_missing(wallet_bridge_source):
    assert "case 'GET_SESSION_PRESENTATION':" in wallet_bridge_source
    assert wallet_bridge_source.count("error: 'site_proof_required'") >= 2


@pytest.mark.browser
def test_bridge_loads_wallet_at_rest_crypto_before_wallet(wallet_bridge_source):
    assert "wallet-at-rest-crypto.js" in wallet_bridge_source
    crypto_idx = wallet_bridge_source.index("wallet-at-rest-crypto.js")
    wallet_idx = wallet_bridge_source.index("lemma-wallet.js")
    assert crypto_idx < wallet_idx


@pytest.mark.browser
def test_bridge_enforces_site_binding_on_store_and_verify(wallet_bridge_source):
    assert "case 'STORE_CREDENTIAL':" in wallet_bridge_source
    assert "Cannot store credentials for other sites" in wallet_bridge_source
    assert "case 'VERIFY_CREDENTIAL':" in wallet_bridge_source
    assert "Cannot verify credentials for other sites" in wallet_bridge_source


@pytest.mark.browser
def test_bridge_handles_get_session_presentation(wallet_bridge_source):
    assert "case 'GET_SESSION_PRESENTATION':" in wallet_bridge_source
    assert "SESSION_PRESENTATION_PREFIX = 'lemma:site-session-presentation:v1'" in wallet_bridge_source
    assert "buildSessionPresentationPayload" in wallet_bridge_source
    assert "session_assertion" in wallet_bridge_source
    assert "session_signature" in wallet_bridge_source
    assert "await siteKeys.keypair.sign(payloadBytes)" in wallet_bridge_source
    assert "Math.min(" in wallet_bridge_source
    assert "MAX_SESSION_TTL_SECONDS" in wallet_bridge_source
    assert "MIN_SESSION_TTL_SECONDS" in wallet_bridge_source
    assert "bloom_sequence_required" in wallet_bridge_source


@pytest.mark.browser
def test_bridge_preserves_get_credential_for_backwards_compat(wallet_bridge_source):
    assert "case 'GET_CREDENTIAL':" in wallet_bridge_source
    assert "presentation_signature" in wallet_bridge_source
    assert "signPresentation" in wallet_bridge_source
