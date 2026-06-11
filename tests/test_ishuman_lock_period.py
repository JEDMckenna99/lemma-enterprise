from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"
VERIFIER_JS = ROOT / "static" / "js" / "ishuman-verifier.js"
IDV_HTML = ROOT / "templates" / "wallet_ishuman_idv.html"
POPUP_HTML = ROOT / "templates" / "wallet_popup.html"
WALLET_UNLOCK_HTML = ROOT / "templates" / "wallet_unlock.html"
RECOVER_COMPLETE_HTML = ROOT / "templates" / "recover_complete.html"
MODERN_LAYOUT_HTML = ROOT / "templates" / "modern" / "layout.html"


@pytest.fixture(name="wallet_source")
def fixture_wallet_source() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.fixture(name="verifier_source")
def fixture_verifier_source() -> str:
    return VERIFIER_JS.read_text(encoding="utf-8")


@pytest.mark.browser
def test_wallet_ishuman_lock_bundle_constants(wallet_source):
    assert "ISHUMAN_LOCK_STORAGE_KEY = 'lemma_ishuman_lock:v1'" in wallet_source
    assert "isHumanIssuance" in wallet_source
    assert "ensureIsHumanIssuanceReady" in wallet_source
    assert "ishuman_cache" in wallet_source
    assert "WALLET_DB_VERSION = 7" in wallet_source


@pytest.mark.browser
def test_wallet_lock_bundle_persist_and_restore(wallet_source):
    assert "_persistIsHumanLockBundle" in wallet_source
    assert "_restoreIsHumanLockBundleIfValid" in wallet_source
    assert "_clearIsHumanLockBundle" in wallet_source
    assert "isIsHumanLockValid" in wallet_source


@pytest.mark.browser
def test_wallet_daily_unlock_helpers(wallet_source):
    assert "exportIsHumanCredentialsForBridge" in wallet_source
    assert "issueSiteProofPackage" in wallet_source
    assert "deriveAndStoreSiteProof" in wallet_source
    assert "signSiteSessionPresentation" in wallet_source
    assert "applyIsHumanCredentialsToCache" in wallet_source
    assert "hasIsHumanMasterInCache" in wallet_source
    assert "localStorage.setItem(ISHUMAN_LOCK_STORAGE_KEY" in wallet_source
    assert "request.onblocked" in wallet_source
    assert "rows.some((row) => mod.isEncryptedEnvelope(row))" in wallet_source


@pytest.mark.browser
def test_verifier_site_vc_cache(verifier_source):
    assert "SITE_VC_STORAGE_KEY = 'ishuman_site_vc:v1'" in verifier_source
    assert "_verifyFromSiteVcCache" in verifier_source
    assert "'vc_valid'" in verifier_source
    assert "TIME_SKEW_SECONDS" in verifier_source
    assert "signatureValueWeb" in verifier_source
    assert "legacy_credential_format" in verifier_source
    assert "_hydrateBloomFromCache" in verifier_source
    assert "broadcastBlockUpdate" in verifier_source
    assert "fresh_idv" in verifier_source
    assert "result.credential" in verifier_source or "credential: cred" in verifier_source
    assert "_issueSiteProofViaPopup" in verifier_source
    assert "_applyIssuedSiteProof" in verifier_source
    assert "ISHUMAN_SITE_PROOF_ISSUED" in verifier_source
    assert "site_proof_required" in verifier_source


@pytest.mark.browser
def test_verifier_routes_revocation_to_fresh_idv_flow(verifier_source):
    """A revoked credential must open the popup in fresh_idv mode so the user
    can regain access by completing a new identity check, rather than being
    permanently blocked."""
    assert "'revoked'," in verifier_source
    assert "'site_blocked'," in verifier_source
    assert "'expired'," in verifier_source
    assert "freshIdv: needsFreshIdv" in verifier_source
    assert "options.freshIdv ? 'fresh_idv' : 'site_proof'" in verifier_source
    assert "refresh_reason" in verifier_source


@pytest.mark.browser
def test_verifier_broadcasts_site_block_updates_cross_tab(verifier_source):
    """A per-site block in one tab must invalidate cached sessions in other
    tabs on the same origin immediately, without waiting for the next poll."""
    assert "lemma-ishuman-blocks" in verifier_source
    assert "BroadcastChannel" in verifier_source
    assert "broadcastBlockUpdate" in verifier_source
    assert "SITE_BLOCK_UPDATE" in verifier_source
    assert "NETWORK_REVOCATION" in verifier_source


@pytest.mark.browser
def test_wallet_handoff_wallet_id_reconciled_for_site_proof(wallet_source):
    """Handoff-linked wallets must bind passkey to the verified wallet_id, not mint a new one."""
    assert "_resolveStoredWalletIdentity" in wallet_source
    assert "reconcileSessionWalletIdForIssuance" in wallet_source
    assert "requirePasskeyForIssuance" in wallet_source
    assert "mustCreatePasskeyForIssuance" in wallet_source
    assert "canAutoFinishVerificationReturn" in IDV_HTML.read_text(encoding="utf-8")
    assert "ishuman_deferred_passkey" not in wallet_source


@pytest.mark.browser
def test_idv_site_proof_polls_master_when_session_pending():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "if (sessionId) {" in idv_html
    assert "await pollAndStoreMaster();" in idv_html
    assert "reconcileSessionWalletIdForIssuance" in idv_html


@pytest.mark.browser
def test_mobile_handoff_shows_success_ui():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "showMobileHandoffCompleteUi" in idv_html
    assert "hasHandoffLinkedWallet" in idv_html
    assert "Your lemma.id is ready on this phone." in idv_html


@pytest.mark.browser
def test_idv_popup_issues_site_proof_via_wallet():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "ensureIsHumanIssuanceReady" in idv_html
    assert "issueSiteProofPackage" in idv_html
    assert "ISHUMAN_SITE_PROOF_ISSUED" in idv_html
    assert "issue_mode" in idv_html
    assert "site_proof" in idv_html


@pytest.mark.browser
def test_idv_site_proof_starts_hosted_verification_without_master():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    site_proof_block = idv_html.split("async function issueSiteProofAndClose()", 1)[1]
    site_proof_block = site_proof_block.split("async function runFreshIdvAndClose()", 1)[0]
    assert "startHostedVerification();" in site_proof_block
    assert "siteProofPending" not in site_proof_block


@pytest.mark.browser
def test_idv_popup_allows_same_origin_demo_hub_master_flow():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "isSameOriginMasterFlow" in idv_html
    assert "isMasterCreationFlow" in idv_html


@pytest.mark.browser
def test_idv_site_proof_boot_does_not_reference_undefined_copy():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    site_proof_boot = idv_html.split("if (isSiteProofIssue) {", 1)[1]
    site_proof_boot = site_proof_boot.split("if (isVerificationReturn && sessionId) {", 1)[0]
    assert "setStatus(copy.status" not in site_proof_boot


@pytest.mark.browser
def test_wallet_prefers_newest_credential_after_fresh_idv(wallet_source):
    """After fresh IDV the wallet cache holds both the old and new master.
    Lookups must prefer the most-recently-issued credential or the
    server-side derive-site-proof will 404 on the stale master_credential_id.
    """
    assert "_sortCredentialsNewestFirst" in wallet_source
    assert "_credentialIssuedAtSeconds" in wallet_source
    assert "this._sortCredentialsNewestFirst(matches)[0]" in wallet_source
    assert "this._sortCredentialsNewestFirst(cachedMasters)[0]" in wallet_source


@pytest.mark.browser
def test_idv_popup_supports_fresh_idv_mode():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "fresh_idv" in idv_html
    assert "runFreshIdvAndClose" in idv_html
    assert "Complete a fresh identity check" in idv_html


@pytest.mark.browser
def test_lemma_keys_uses_async_noble_ed25519_signing():
    keys_js = (ROOT / "static" / "js" / "lemma-keys.js").read_text(encoding="utf-8")
    assert "signAsync" in keys_js
    assert "sha512Async" in keys_js


@pytest.mark.browser
def test_unlock_popup_ishuman_flag():
    popup_html = POPUP_HTML.read_text(encoding="utf-8")
    assert "isHumanIssuance" in popup_html
    assert "ishuman" in popup_html
    assert "isHumanCredentials" in popup_html
    assert "Wallet status check timed out" in popup_html


@pytest.mark.browser
def test_idv_popup_handles_encrypted_master_without_raw_error():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "Unlock wallet with passkey to read encrypted human proof." in idv_html
    assert "envelope_invalid" in idv_html


@pytest.mark.browser
def test_wallet_pages_use_current_wallet_bundle():
    wallet_pages = [
        IDV_HTML,
        POPUP_HTML,
        WALLET_UNLOCK_HTML,
        RECOVER_COMPLETE_HTML,
        MODERN_LAYOUT_HTML,
    ]
    for path in wallet_pages:
        source = path.read_text(encoding="utf-8")
        assert "lemma-wallet.js?v=2542" not in source
        if path == IDV_HTML:
            assert "lemma-wallet.js?v=2549" in source
        else:
            assert "lemma-wallet.js') }}?v=2549" in source or "lemma-wallet.js?v=2549" in source
        assert "lemma-keys.js?v=2" not in source
        assert "lemma-keys.js?v=3" not in source
        assert "lemma-keys.js') }}?v=4" in source or "lemma-keys.js?v=4" in source
