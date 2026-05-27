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
def test_verifier_requests_session_presentation_on_first_verify(verifier_source):
    assert "_requestSessionFromBridge" in verifier_source
    assert "type: 'GET_SESSION_PRESENTATION'" in verifier_source
    assert "sessionNonce" in verifier_source
    assert "bloomSequence" in verifier_source
    assert "sessionTtlSec:" in verifier_source
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
def test_verifier_uses_site_vc_cache_on_repeat_verify(verifier_source):
    assert "_verifyFromSiteVcCache" in verifier_source
    assert "'session_valid'" in verifier_source
    assert "'vc_valid'" in verifier_source
    assert "localStorage.setItem(key, JSON.stringify(session))" in verifier_source
    assert "invalidateSession" in verifier_source
