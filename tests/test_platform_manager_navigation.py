"""Canonical navigation and creation entry points for the lemma.id manager."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_root_is_home_and_app_is_manager(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        root = client.get("/")
        # /app without a verified sign-in session serves the sign-in gate.
        gate = client.get("/app")

        # A verified presentation-backed session opens the real manager.
        from api.lemma_session_auth import SESSION_KEY

        with client.session_transaction() as sess:
            sess[SESSION_KEY] = {
                "ppid": "did:lemma:ppid_test",
                "assurance": "passkey",
                "signed_in_at": 0,
            }
        manager = client.get("/app")
        product = client.get("/home")

    assert root.status_code == 200
    assert b"Sign in with lemma.id" in root.data
    assert b"Passwordless login" in root.data
    assert b"assurance-levels" in root.data
    assert gate.status_code == 200
    assert b'id="sf-state-gate"' in gate.data
    assert b'id="sf-gate-signin-btn"' in gate.data
    assert b'id="create-wallet-btn"' not in gate.data
    assert manager.status_code == 200
    assert b'id="create-wallet-btn"' in manager.data
    assert b"Create my lemma.id" in manager.data
    assert b'id="identity-card"' in manager.data
    assert b'id="sf-manager-panels"' not in manager.data
    assert product.status_code == 200
    assert b"Passwordless login" in product.data
    assert b"assurance-levels" in product.data


def test_brand_and_manager_creation_use_canonical_routes():
    layout = (ROOT / "templates" / "modern" / "layout.html").read_text(encoding="utf-8")
    manager = (ROOT / "templates" / "wallet_simple.html").read_text(encoding="utf-8")
    wallet_auto = (ROOT / "templates" / "modern" / "includes" / "wallet_auto_init_script.html").read_text(
        encoding="utf-8"
    )

    assert 'class="nav-logo"' in layout
    assert 'href="/"' in layout and 'nav-logo' in layout
    assert 'id="nav-logo"' in layout
    assert 'stroke="currentColor"' in layout
    assert 'id="wallet-logo"' in manager
    assert 'stroke="currentColor"' in manager
    assert ".wallet-logo.is-unlocked" in manager
    assert "#4E3D8F" in manager
    assert '<a href="/home" class="nav-link" id="nav-product">' in layout
    assert "new URL('/verify', window.location.origin)" in manager
    assert "popupUrl.searchParams.set('site_id', 'lemma.id')" in manager
    assert "popupUrl.searchParams.set('flow_state', flowState)" in manager
    assert "mintPlatformVerifyFlowState" in manager
    assert "/api/verify/flow-state" in manager
    assert "window.open(" in manager
    assert "about:blank" in manager
    assert "async function hasCompleteLemmaId()" in manager
    assert "getWalletInfo({ lite: true })" in manager
    assert "globalLemmaWallet" in manager
    assert "deferUnlockedProofCheck" in manager
    assert "Identity check not anchored yet" in manager
    assert 'id="anchor-identity-card"' in manager
    assert 'id="anchor-wallet-btn"' in manager
    assert "Anchor this lemma.id" in manager
    assert "Anchor with your identity" in manager
    assert "No ID documents, selfies, or legal name are stored after verification." in manager
    assert "Sites only see a proof that you're human" in manager
    assert "updateAnchorIdentityCard" in manager
    assert "anchorWalletIdentity" in manager
    assert "function isHumanIdentityAnchor(" in manager
    assert "async function hasHumanIdentityAnchor(" in manager
    assert "requiredAssurance: 'ishuman'" in manager
    assert "showIncompleteLemmaIdState();\n            return;" not in manager
    assert 'rel="preload"' in manager and "lemma-wallet.js" in manager
    assert "assessLemmaPlatformIdentity" in manager
    assert "selectPlatformCredentials" in layout
    assert "selectPlatformCredentials" in wallet_auto
    assert "Create a lemma.id" in manager
    assert "window.location.replace('/app')" in wallet_auto
    assert "walletInfo.hasWallet" in wallet_auto
    assert "req.onblocked = () => {}" in manager or "purgeAllDeviceData" in manager
    assert "instance?.db?.close?.()" in manager
    assert "localStorage.clear()" in manager
    assert "window.location.replace('/?removed=1')" in manager
    assert "LemmaWallet.purgeAllDeviceData" in manager
    assert "SameSite=None" in manager
    assert "returnWithExistingPasskey" in manager
    assert "removed-notice" in manager
    assert 'id="devices-card"' in manager
    assert 'id="devices-list"' in manager
    assert "Your devices &amp; browsers" in manager or "Your devices & browsers" in manager
    assert "loadDevicesList" in manager
    assert "revokeOtherDevice" in manager
    wallet_js = (ROOT / "static" / "js" / "lemma-wallet.js").read_text(encoding="utf-8")
    assert "LemmaWalletWrap" in manager or "purgeAllDeviceData" in wallet_js
    assert "async listDevices(" in wallet_js
    assert "async revokeDevice(" in wallet_js
    assert "static VERSION = '2.81.0'" in wallet_js
    assert "Never call instance.lock()" in wallet_js
    assert "Safari/iOS-safe" in wallet_js
    assert "_handleDeviceRevoked" in wallet_js
    assert "isDeviceRevokedError" in wallet_js
    assert "rolling back local unlock" not in wallet_js
    assert "Browser verified user via biometrics (server session unlock)" in wallet_js
    assert "bootstrap_required" in wallet_js
    assert "Device revoked" in manager
    assert "e?.code === 'device_revoked'" in manager
