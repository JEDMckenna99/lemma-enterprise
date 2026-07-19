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
        manager = client.get("/app")
        product = client.get("/home")

    assert root.status_code == 200
    assert b"Stop the same abuser" in root.data
    assert b"assurance-levels" in root.data
    assert manager.status_code == 200
    assert b'id="create-wallet-btn"' in manager.data
    assert b"Create my lemma.id" in manager.data
    assert product.status_code == 200
    assert b"Stop the same abuser" in product.data
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
    assert "new URL('/wallet/ishuman-idv', window.location.origin)" in manager
    assert "popupUrl.searchParams.set('site_id', 'lemma.id')" in manager
    assert "window.open(" in manager
    assert "async function hasCompleteLemmaId()" in manager
    assert "getWalletInfo({ lite: true })" in manager
    assert "globalLemmaWallet" in manager
    assert "deferUnlockedProofCheck" in manager
    assert "Identity check not anchored yet" in manager
    assert 'id="anchor-wallet-btn"' in manager
    assert "Anchor this lemma.id" in manager
    assert "anchorWalletIdentity" in manager
    assert "showIncompleteLemmaIdState();\n            return;" not in manager
    assert 'rel="preload"' in manager and "lemma-wallet.js" in manager
    assert "assessLemmaPlatformIdentity" in manager
    assert "selectPlatformCredentials" in layout
    assert "selectPlatformCredentials" in wallet_auto
    assert "Create a lemma.id" in manager
    assert "window.location.replace('/app')" in wallet_auto
    assert "walletInfo.hasWallet" in wallet_auto
    assert "req.onblocked = () => reject" in manager
    assert "instance?.db?.close?.()" in manager
    assert "localStorage.clear()" in manager
    assert "window.location.replace('/?removed=1')" in manager
    assert "LemmaWallet.purgeAllDeviceData" in manager
    assert "returnWithExistingPasskey" in manager
    assert "removed-notice" in manager
    assert "LemmaWalletWrap" in manager or "purgeAllDeviceData" in (ROOT / "static" / "js" / "lemma-wallet.js").read_text(encoding="utf-8")
