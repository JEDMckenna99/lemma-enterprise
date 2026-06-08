from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"
LAYOUT = ROOT / "templates" / "modern" / "layout.html"
INDEX = ROOT / "templates" / "modern" / "index.html"
DEV_LAYOUT = ROOT / "templates" / "developer" / "layout.html"


@pytest.fixture(name="wallet_source")
def fixture_wallet_source() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_default_session_hours_is_ten_hours(wallet_source):
    assert "const DEFAULT_SESSION_HOURS = 10;" in wallet_source
    assert "const MAX_SESSION_HOURS = 10;" in wallet_source


@pytest.mark.unit
def test_layout_wallet_auto_init_default_empty():
    layout = LAYOUT.read_text(encoding="utf-8")
    assert "{% block wallet_auto_init %}" in layout
    start = layout.index("{% block wallet_auto_init %}")
    block = layout[start:start + 80]
    assert "wallet_auto_init_script.html" not in block


@pytest.mark.unit
def test_public_index_skips_wallet_auto_init():
    index = INDEX.read_text(encoding="utf-8")
    assert "wallet_auto_init_script.html" not in index


@pytest.mark.unit
def test_developer_layout_enables_wallet_auto_init():
    dev = DEV_LAYOUT.read_text(encoding="utf-8")
    assert "wallet_auto_init_script.html" in dev


@pytest.mark.unit
def test_debug_panel_requires_server_flag(wallet_source):
    assert "function isLemmaWalletDebugEnabled()" in wallet_source
    assert "window.LEMMA_WALLET_DEBUG" in wallet_source
    assert "Debug panel disabled in production" in wallet_source
