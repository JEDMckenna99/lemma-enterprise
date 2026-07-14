"""Platform identity contract regression tests (frontend source + backend binding)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UTILS_JS = ROOT / "static" / "js" / "lemma-credential-utils.js"
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


@pytest.fixture(name="utils_js_source")
def fixture_utils_js_source() -> str:
    return UTILS_JS.read_text(encoding="utf-8")


@pytest.fixture(name="wallet_js_source")
def fixture_wallet_js_source() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_credential_utils_exports_platform_contract(utils_js_source):
    for symbol in (
        "canonicalPlatformSite",
        "isPlatformSiteBinding",
        "getCredentialSiteBinding",
        "isCompleteLemmaIdCredential",
        "isPlatformOperatorCredential",
        "selectPlatformCredentials",
        "assessLemmaPlatformIdentity",
    ):
        assert symbol in utils_js_source


@pytest.mark.unit
def test_credential_utils_skips_internal_site_ids(utils_js_source):
    assert "isInternalSiteIdentifier" in utils_js_source
    assert "startsWith('site_')" in utils_js_source


@pytest.mark.unit
def test_credential_utils_platform_aliases(utils_js_source):
    assert "'lemma_platform'" in utils_js_source
    assert "'www.lemma.id'" in utils_js_source
    assert "PLATFORM_SITE_CANONICAL = 'lemma.id'" in utils_js_source


@pytest.mark.unit
def test_credential_utils_admin_permission_is_admin_access(utils_js_source):
    assert "'admin_access'" in utils_js_source
    assert "includes('lemma')" not in utils_js_source


@pytest.mark.unit
def test_wallet_skips_empty_site_before_canonicalization(wallet_js_source):
    assert "_canonicalizeCredentialSiteValue" in wallet_js_source
    assert "if (value == null || value === '') return ''" in wallet_js_source
    assert ".map((value) => this._canonicalizeCredentialSiteValue(value))" in wallet_js_source


@pytest.mark.unit
def test_wallet_version_bumped_for_platform_identity(wallet_js_source):
    assert "static VERSION = '2.74.0'" in wallet_js_source


@pytest.mark.unit
def test_get_verified_permissions_uses_browser_sig_for_ishuman(wallet_js_source):
    assert "_verifyIsHumanCredentialBrowser" in wallet_js_source
    assert "_shouldVerifyAsIsHumanCredential" in wallet_js_source
    assert "_browserCanonicalMessage" in wallet_js_source
    assert "signatureValueWeb" in wallet_js_source
    assert "await this._verifyIsHumanCredentialBrowser(perm)" in wallet_js_source


@pytest.mark.unit
def test_ishuman_verifier_unlock_uses_unified_idv_popup():
    verifier = (ROOT / "static" / "js" / "ishuman-verifier.js").read_text(encoding="utf-8")
    assert "issue_mode', 'unlock'" in verifier
    assert "this.idvPopupPath" in verifier.split("_unlockViaPopup")[1][:400]


@pytest.mark.unit
def test_idv_popup_supports_unlock_mode():
    idv = (ROOT / "templates" / "wallet_ishuman_idv.html").read_text(encoding="utf-8")
    assert "isUnlockOnly = issueMode === 'unlock'" in idv
    assert "prepareUnlockOnlyUi" in idv
    assert "LEMMA_UNLOCK_SUCCESS" in idv


@pytest.mark.unit
def test_idv_action_sign_uses_passkey_continuity_unlock():
    idv = (ROOT / "templates" / "wallet_ishuman_idv.html").read_text(encoding="utf-8")
    assert "isActionSign || isActionSign" not in idv
    assert "(isSiteProofIssue || isActionSign) && !isFreshIdv" in idv


@pytest.mark.unit
def test_wallet_popup_redirects_to_unified_idv():
    popup = (ROOT / "templates" / "wallet_popup.html").read_text(encoding="utf-8")
    assert "redirectToUnifiedPopup" in popup
    assert "/wallet/ishuman-idv" in popup


@pytest.mark.unit
def test_platform_auth_cta_auto_reissue_on_verify_failure():
    cta = (ROOT / "templates" / "modern" / "includes" / "platform_auth_cta_script.html").read_text(
        encoding="utf-8"
    )
    assert "reissueMasterCredential" in cta
    assert "__lemmaDevPermReissueAttempted" in cta


@pytest.mark.unit
def test_templates_use_shared_platform_helpers():
    layout = (ROOT / "templates" / "modern" / "layout.html").read_text(encoding="utf-8")
    wallet_auto = (ROOT / "templates" / "modern" / "includes" / "wallet_auto_init_script.html").read_text(
        encoding="utf-8"
    )
    platform_cta = (ROOT / "templates" / "modern" / "includes" / "platform_auth_cta_script.html").read_text(
        encoding="utf-8"
    )
    agent_delegation = (ROOT / "templates" / "admin" / "agent_delegation.html").read_text(encoding="utf-8")
    wallet_simple = (ROOT / "templates" / "wallet_simple.html").read_text(encoding="utf-8")

    assert "selectPlatformCredentials" in layout
    assert "selectPlatformCredentials" in wallet_auto
    assert "assessLemmaPlatformIdentity" in platform_cta
    assert "isPlatformOperatorCredential" in agent_delegation
    assert "assessLemmaPlatformIdentity" in wallet_simple


@pytest.mark.unit
def test_sdk_cache_bust_bumped_in_templates():
    for rel in (
        "templates/modern/layout.html",
        "templates/wallet_unlock.html",
        "templates/wallet_popup.html",
        "templates/wallet_ishuman_idv.html",
        "templates/recover_complete.html",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "lemma-wallet.js" in text and "v=2677" in text, rel


def _encode_credential(credential: dict) -> str:
    raw = json.dumps(credential).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


@pytest.mark.unit
def test_authz_engine_normalizes_platform_alias_site_binding(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    from api.authz_engine import extract_user_lemma_principal

    credential = {
        "id": "cred_platform_alias",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("b" * 64),
        "claims": {
            "permissionId": "admin_access",
            "siteId": "lemma_platform",
        },
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    principal, error = extract_user_lemma_principal(headers)
    assert error is None
    assert principal is not None
    assert principal.site_binding == "lemma.id"


@pytest.mark.unit
def test_authz_engine_rejects_internal_site_id_as_runtime_binding(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    from api.authz_engine import extract_user_lemma_principal

    credential = {
        "id": "cred_internal_only",
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_" + ("c" * 64),
        "claims": {
            "permissionId": "admin_access",
            "siteId": "site_abc123def456",
        },
    }
    headers = {"X-Lemma-Credential": _encode_credential(credential)}

    principal, error = extract_user_lemma_principal(headers)
    assert error is None
    assert principal is not None
    assert principal.site_binding is None


@pytest.mark.unit
def test_noble_curves_vendor_uses_local_hash_imports():
    vendor = (ROOT / "static" / "js" / "vendor" / "noble-curves-ed25519.mjs").read_text(encoding="utf-8")
    assert 'from"/npm/' not in vendor
    assert "./noble-hashes-sha512.mjs" in vendor
    assert "./noble-hashes-utils.mjs" in vendor


@pytest.mark.unit
def test_device_link_bundles_ishuman_credentials_and_unlock_token(wallet_js_source):
    """Cross-device QR/link must carry encrypted human proof + session bootstrap."""
    assert "_importLinkedIsHumanCredentials" in wallet_js_source
    assert "ishumanCredentials" in wallet_js_source
    assert "link-unlock-token" in wallet_js_source
    assert "humanProofRestored" in wallet_js_source
    assert "beginLinkReceive" in wallet_js_source
    assert "sendLinkDepositFromScan" in wallet_js_source
    assert "2.74.0" in wallet_js_source
