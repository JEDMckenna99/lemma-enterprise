from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"
KEYS_JS = ROOT / "static" / "js" / "lemma-keys.js"
VERIFIER_JS = ROOT / "static" / "js" / "ishuman-verifier.js"
IDV_HTML = ROOT / "templates" / "wallet_ishuman_idv.html"
POPUP_HTML = ROOT / "templates" / "wallet_popup.html"
WALLET_UNLOCK_HTML = ROOT / "templates" / "wallet_unlock.html"
RECOVER_COMPLETE_HTML = ROOT / "templates" / "recover_complete.html"
MODERN_LAYOUT_HTML = ROOT / "templates" / "modern" / "layout.html"
WALLET_SIMPLE_HTML = ROOT / "templates" / "wallet_simple.html"


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
def test_wallet_ishuman_storage_fails_when_all_persistence_locked(wallet_source):
    assert "return false;" in wallet_source.split("async _putIsHumanCacheRecord(credential)", 1)[1].split("async syncIsHumanCacheFromWallet", 1)[0]
    assert "let storedInLemmas = false;" in wallet_source
    assert "storedInLemmas = true;" in wallet_source
    assert "const storedInCache = await this._putIsHumanCacheRecord(lemma);" in wallet_source
    assert "throw new Error('ishuman_storage_unavailable');" in wallet_source


@pytest.mark.browser
def test_verifier_site_vc_cache(verifier_source):
    assert "SITE_VC_STORAGE_KEY = 'ishuman_site_vc:v1'" in verifier_source
    assert "_verifyFromSiteVcCache" in verifier_source
    assert "'vc_valid'" in verifier_source
    assert "site_id_mismatch" in verifier_source
    assert "session_assertion_required" in verifier_source
    assert "verifyForBackend" in verifier_source
    assert "strictSession" in verifier_source
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
def test_verifier_requires_explicit_fresh_idv_for_doubt(verifier_source):
    """Site bans fail closed; revocation recovery and explicit doubt select fresh IDV."""
    popup_reasons = verifier_source.split("const popupReasons = new Set([", 1)[1].split("]);", 1)[0]
    assert "'revoked'," in popup_reasons
    assert "'invalid_signature'," not in popup_reasons
    assert "'site_blocked'," not in popup_reasons
    assert "'expired'," in verifier_source
    assert "const needsFreshIdv = result.reason === 'revoked';" in verifier_source
    assert "verifyFreshForBackend" in verifier_source
    assert "refreshReason: 'site_doubt'" in verifier_source
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
    assert "REVOCATION_SNAPSHOT_UPDATE" in verifier_source
    assert "NETWORK_REVOCATION" not in verifier_source


@pytest.mark.browser
def test_verifier_isblocked_locally_errors_fail_closed(verifier_source):
    assert "return { blocked: true, doubtRequired: false };" in verifier_source


@pytest.mark.browser
def test_wallet_handoff_wallet_id_reconciled_for_site_proof(wallet_source):
    """Handoff-linked wallets must bind passkey to the verified wallet_id, not mint a new one."""
    assert "_resolveStoredWalletIdentity" in wallet_source
    assert "reconcileSessionWalletIdForIssuance" in wallet_source
    assert "walletId = sess.walletId || walletId" in wallet_source
    assert "requirePasskeyForIssuance" in wallet_source
    assert "mustCreatePasskeyForIssuance" in wallet_source
    assert "canAutoFinishVerificationReturn" in IDV_HTML.read_text(encoding="utf-8")
    assert "ishuman_deferred_passkey" not in wallet_source


@pytest.mark.browser
def test_platform_auth_accepts_combined_master_claims(wallet_source):
    """lemma.id platform auth must accept the master isHuman credential when it carries IAM claims."""
    auto_init = (ROOT / "templates" / "modern" / "includes" / "wallet_auto_init_script.html").read_text(encoding="utf-8")
    layout = (ROOT / "templates" / "modern" / "layout.html").read_text(encoding="utf-8")
    platform_cta = (ROOT / "templates" / "modern" / "includes" / "platform_auth_cta_script.html").read_text(encoding="utf-8")
    utils_js = (ROOT / "static" / "js" / "lemma-credential-utils.js").read_text(encoding="utf-8")
    assert "hasPlatformPermissionClaims" in wallet_source
    assert "Get permission lemmas plus combined lemma.id isHuman+IAM master credentials" in wallet_source
    assert "_canonicalizeCredentialSiteValue" in wallet_source
    assert "_isLemmaPlatformSiteBinding" in wallet_source
    assert "selectPlatformCredentials" in auto_init
    assert "isCompleteLemmaId" in auto_init
    assert "selectPlatformCredentials" in layout
    assert "assessLemmaPlatformIdentity" in platform_cta
    assert "isCompleteLemmaIdCredential" in utils_js
    assert "const all = await wallet.getCredentials();" in layout
    login_payload = platform_cta.split("fetch('/api/wallet-auth/platform-login'", 1)[1].split("});", 1)[0]
    assert "ppid:" not in login_payload
    assert "wallet_id: clientWalletId" in login_payload


@pytest.mark.browser
def test_cleared_device_uses_fresh_wallet_id_and_repairs_key_conflict(wallet_source):
    assert "storedIdentity?.walletId && storedIdentity?.walletSecret" in wallet_source
    assert "_rotateIncompleteWalletId" in wallet_source
    assert "err?.code !== 'wallet_pubkey_mismatch'" in wallet_source
    assert "if (localMaster || cachedMaster) return null" in wallet_source
    assert "prfWalletId" in wallet_source


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
    assert "Your lemma.id is ready on this device." in idv_html


@pytest.mark.browser
def test_mobile_handoff_return_must_store_master_before_success():
    """A linked wallet alone is not enough; the popup must persist the master
    proof before showing the ready state and closing successfully."""
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    finish_block = idv_html.split("async function finishMobileHandoffStoreMaster", 1)[1]
    finish_block = finish_block.split("async function runSilentMobileHandoffCompletion", 1)[0]
    assert "await pollAndStoreMaster();" in finish_block
    assert "master poll pending after handoff" not in finish_block

    return_block = idv_html.rsplit("if (isVerificationReturn && sessionId) {", 1)[1]
    return_block = return_block.split("document.getElementById('primary-btn').classList.add('hidden');", 1)[0]
    assert "await adoptWalletState();" in return_block
    assert return_block.index("await adoptWalletState();") < return_block.index("await pollAndStoreMaster();")
    assert return_block.index("await pollAndStoreMaster();") < return_block.index("await showMobileHandoffCompleteUi")
    assert "handoff return master store failed" in return_block
    assert "Retry finish" in return_block


@pytest.mark.browser
def test_mobile_handoff_scrubs_mk_from_url():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "scrubHandoffSecretsFromUrl" in idv_html
    assert "params.delete('mk')" in idv_html
    assert "history.replaceState" in idv_html
    scrub_idx = idv_html.index("scrubHandoffSecretsFromUrl")
    claim_idx = idv_html.index("claimIdvMobileHandoff")
    assert scrub_idx < claim_idx


@pytest.mark.browser
def test_mobile_handoff_return_session_param_overrides_stale_storage(wallet_source):
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "let sessionId = ishumanSessionParam || localStorage.getItem(SESSION_KEY) || '';" in idv_html
    assert "if (ishumanSessionParam) {" in idv_html
    assert "const claimedSessionId = data.session_id || sessionId;" in wallet_source
    assert "this._idvHandoffAad(handoffId, claimedSessionId, data.wallet_id)" in wallet_source


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
    ensure_block = idv_html.split("async function ensureMasterProofForIssuance()", 1)[1]
    ensure_block = ensure_block.split("async function issueSiteProofAndClose()", 1)[0]
    assert "startHostedVerification();" in ensure_block
    assert "siteProofPending" not in ensure_block


@pytest.mark.browser
def test_idv_site_proof_clears_stale_session_without_verification_return():
    """A wallet with no master must start fresh IDV, not poll a stale popup session."""
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "ensureMasterProofForIssuance" in idv_html
    ensure_block = idv_html.split("async function ensureMasterProofForIssuance()", 1)[1]
    ensure_block = ensure_block.split("async function issueSiteProofAndClose()", 1)[0]
    assert "isVerificationReturn && sessionId" in ensure_block
    assert "clearIdvSession" in ensure_block
    assert "starting fresh IDV" in ensure_block


@pytest.mark.browser
def test_idv_popup_allows_same_origin_demo_hub_master_flow():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "isSameOriginMasterFlow" in idv_html
    assert "isMasterCreationFlow" in idv_html
    assert "PLATFORM_SITE_IDS" in idv_html
    assert "platformHost" in idv_html


@pytest.mark.browser
def test_idv_passkey_actions_require_a_user_click():
    """Popup boot must not invoke WebAuthn without transient user activation."""
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "async function showUserInitiatedPrimaryAction()" in idv_html
    assert "WebAuthn create/get requires a user gesture" in idv_html
    assert idv_html.count("await showUserInitiatedPrimaryAction();") == 3
    assert "Creating your lemma.id with a passkey" in idv_html


@pytest.mark.browser
def test_idv_site_proof_boot_does_not_reference_undefined_copy():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    site_proof_boot = idv_html.rsplit("if (isSiteProofIssue) {", 1)[1]
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
    assert "Starting a fresh verification" in idv_html


@pytest.mark.browser
def test_lemma_keys_uses_async_noble_ed25519_signing():
    keys_js = (ROOT / "static" / "js" / "lemma-keys.js").read_text(encoding="utf-8")
    assert "signAsync" in keys_js
    assert "sha512Async" in keys_js


@pytest.mark.browser
def test_idv_popup_has_lifecycle_guards():
    idv_html = IDV_HTML.read_text(encoding="utf-8")
    assert "lemma-ishuman-popup" in idv_html
    assert "ISHUMAN_POPUP_SUPERSEDE" in idv_html
    assert "isHandoffProtected" in idv_html
    assert "idle_timeout" in idv_html
    assert "withIdvBusy" in idv_html


@pytest.mark.browser
def test_ishuman_verifier_manages_popup_dedup():
    verifier_js = VERIFIER_JS.read_text(encoding="utf-8")
    assert "_openManagedLemmaPopup" in verifier_js
    assert "POPUP_CHANNEL_NAME" in verifier_js
    assert "ISHUMAN_POPUP_SUPERSEDE" in verifier_js
    assert "popup_token" in verifier_js


@pytest.mark.browser
def test_unlock_popup_has_lifecycle_guards():
    popup_html = POPUP_HTML.read_text(encoding="utf-8")
    assert "lemma-ishuman-popup" in popup_html
    assert "initUnlockLifecycle" in popup_html


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
    wallet_pages = {
        IDV_HTML: "2687",
        POPUP_HTML: "2687",
        WALLET_UNLOCK_HTML: "2687",
        RECOVER_COMPLETE_HTML: "2687",
        MODERN_LAYOUT_HTML: "2687",
        WALLET_SIMPLE_HTML: "2687",
    }
    for path, version in wallet_pages.items():
        source = path.read_text(encoding="utf-8")
        assert "lemma-wallet.js?v=2542" not in source
        assert "lemma-wallet.js" in source and f"?v={version}" in source
        assert "lemma-keys.js?v=2" not in source
        assert "lemma-keys.js?v=3" not in source
        assert "lemma-keys.js?v=7" not in source
        assert "lemma-keys.js') }}?v=8" in source or "lemma-keys.js?v=8" in source

    keys_source = KEYS_JS.read_text(encoding="utf-8")
    assert "generateDeviceSigningKeypair," in keys_source
    assert "wrapDeviceSigningKeypair," in keys_source
