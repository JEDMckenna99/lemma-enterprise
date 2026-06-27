"""Canonical navigation and creation entry points for the lemma.id manager."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_root_is_manager_and_home_is_product_page(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        manager = client.get("/")
        product = client.get("/home")

    assert manager.status_code == 200
    assert b'id="create-wallet-btn"' in manager.data
    assert b"Create my lemma.id" in manager.data
    assert product.status_code == 200
    assert b"Make abuse harder to rotate" in product.data


def test_brand_and_manager_creation_use_canonical_routes():
    layout = (ROOT / "templates" / "modern" / "layout.html").read_text(encoding="utf-8")
    manager = (ROOT / "templates" / "wallet_simple.html").read_text(encoding="utf-8")

    assert '<a href="/" class="nav-logo">' in layout
    assert '<a href="/home" class="nav-link" id="nav-product">' in layout
    assert "new URL('/wallet/ishuman-idv', window.location.origin)" in manager
    assert "popupUrl.searchParams.set('site_id', 'lemma.id')" in manager
    assert "window.open(" in manager
    assert "async function hasCompleteLemmaId()" in manager
    assert "Create a lemma.id" in manager
    assert "req.onblocked = () => reject" in manager
    assert "instance?.db?.close?.()" in manager
    assert "localStorage.clear()" in manager
    assert "window.location.replace('/?removed=1')" in manager
