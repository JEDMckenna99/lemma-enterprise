from __future__ import annotations

import os
from pathlib import Path

import pytest

VERIFIER_PATH = Path(__file__).resolve().parents[1] / "static" / "js" / "ishuman-verifier.js"


@pytest.fixture(name="verifier_source")
def fixture_verifier_source() -> str:
    return VERIFIER_PATH.read_text(encoding="utf-8")


@pytest.mark.browser
def test_verifier_defines_session_constants(verifier_source):
    assert "SESSION_PRESENTATION_PREFIX = 'lemma:site-session-presentation:v1'" in verifier_source
    assert "DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60" in verifier_source
    assert "MIN_SESSION_TTL_SECONDS = 60" in verifier_source
    assert "MAX_SESSION_TTL_SECONDS = 24 * 60 * 60" in verifier_source
    assert "SESSION_STORAGE_KEY = 'ishuman_session_v1'" in verifier_source
    assert "SITE_VC_STORAGE_KEY = 'ishuman_site_vc:v1'" in verifier_source


@pytest.mark.browser
def test_verifier_site_vc_cache_helpers(verifier_source):
    assert "_verifyFromSiteVcCache" in verifier_source
    assert "checkStatus" in verifier_source


@pytest.mark.browser
def test_verifier_requests_session_presentation_via_popup_on_first_verify(verifier_source):
    # Phase 2.1: the bridge iframe is gone. On a cache miss the verifier issues
    # a fresh site proof through the Lemma-hosted popup, carrying the session
    # nonce / bloom sequence / ttl so the popup can sign a session presentation.
    assert "_issueSiteProofViaPopup" in verifier_source
    assert "'session_nonce'" in verifier_source
    assert "'bloom_sequence'" in verifier_source
    assert "'session_ttl_sec'" in verifier_source
    assert "this.sessionTtlSec" in verifier_source


@pytest.mark.browser
def test_verifier_validates_session_assertion_signature(verifier_source):
    assert "buildSessionPresentationPayload" in verifier_source
    assert "verifySessionAssertion" in verifier_source
    assert "SESSION_PRESENTATION_PREFIX" in verifier_source
    assert "session_bloom_sequence_mismatch" in verifier_source
    assert "session_expired" in verifier_source
    assert "invalid_session_signature" in verifier_source
    assert "claims.site_signing_pubkey" in verifier_source


@pytest.mark.browser
def test_verifier_bloom_sync_is_snapshot_driven(verifier_source):
    assert "BLOOM_SYNC_INTERVAL_MS" not in verifier_source
    assert "snapshotAgeSec" in verifier_source
    assert "max_staleness_seconds" in verifier_source
    assert "generated_at_unix" in verifier_source


@pytest.mark.browser
def test_verifier_invalidates_session_on_bloom_sequence_change(verifier_source):
    assert "_clearSessionCache" in verifier_source
    assert "localStorage.removeItem(key)" in verifier_source
    assert "Number(prevSequence) !== Number(newSequence)" in verifier_source


@pytest.mark.browser
def test_verifier_fails_closed_when_session_signature_invalid(verifier_source):
    assert "'invalid_session_signature'" in verifier_source
    assert "_verifyFromSiteVcCache" in verifier_source


@pytest.mark.browser
def test_verifier_opens_popup_for_missing_site_proof(verifier_source):
    assert "_issueSiteProofViaPopup" in verifier_source
    # site_proof is the default issue_mode; fresh_idv is used after revocation.
    assert "options.freshIdv ? 'fresh_idv' : 'site_proof'" in verifier_source
    assert "ISHUMAN_SITE_PROOF_ISSUED" in verifier_source
    assert "_applyIssuedSiteProof" in verifier_source
    assert "popupUrl.searchParams.set('redirect_return', window.location.href);" in verifier_source


@pytest.mark.browser
def test_verifier_cached_bloom_for_fast_cache_hits_and_no_bridge(verifier_source):
    """Cache-hit fast path: no iframe, no network block.

    The Bloom snapshot must be hydrated from localStorage during _init() so a
    cached verify() can complete without waiting for /api/revocation/bloom-filter.
    Phase 2.1: the bridge iframe path is gone entirely — a cache miss returns
    'site_proof_required' so verify() routes to the popup.
    """
    assert "_hydrateBloomFromCache" in verifier_source
    assert "this._bloomNetworkRefresh = this._syncBloom()" in verifier_source
    assert "_setupBridge" not in verifier_source
    assert "'site_proof_required'" in verifier_source


@pytest.mark.browser
def test_verifier_passkey_assurance_respects_required_policy(verifier_source):
    assert "_assuranceMeetsPolicy(assurance, policy)" in verifier_source
    assert "return actual === required" in verifier_source
    assert "cached assurance" in verifier_source
    assert "required_assurance" in verifier_source
    assert "_activeRequiredAssurance" in verifier_source


@pytest.mark.browser
def test_verifier_uses_site_vc_cache_on_repeat_verify(verifier_source):
    assert "_verifyFromSiteVcCache" in verifier_source
    assert "'session_valid'" in verifier_source
    assert "'vc_valid'" in verifier_source
    assert "localStorage.setItem(key, JSON.stringify(session))" in verifier_source
    assert "invalidateSession" in verifier_source
