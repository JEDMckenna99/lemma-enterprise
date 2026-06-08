from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS_PATH = ROOT / "static" / "js" / "lemma-wallet.js"


def _is_lemma_hostname(hostname: str) -> bool:
    """Mirror of isLemmaHostname() in static/js/lemma-wallet.js."""
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host == "lemma.id" or host.endswith(".lemma.id"):
        return True
    if host in {"localhost", "127.0.0.1"}:
        return True
    return False


@pytest.mark.parametrize(
    ("hostname", "expected"),
    [
        ("lemma.id", True),
        ("api.lemma.id", True),
        ("www.lemma.id", True),
        ("notlemma.id", False),
        ("lemma.id.evil.com", False),
        ("lemma.id.attacker.com", False),
        ("localhost", True),
        ("127.0.0.1", True),
        ("evil.localhost.evil.com", False),
        ("", False),
    ],
)
def test_is_lemma_hostname_contract(hostname: str, expected: bool):
    assert _is_lemma_hostname(hostname) is expected


@pytest.fixture(name="wallet_js_source")
def fixture_wallet_js_source() -> str:
    return WALLET_JS_PATH.read_text(encoding="utf-8")


@pytest.mark.unit
def test_lemma_wallet_defines_is_lemma_hostname_helper(wallet_js_source):
    assert "function isLemmaHostname(hostname)" in wallet_js_source
    assert "host.endsWith('.lemma.id')" in wallet_js_source


@pytest.mark.unit
def test_is_lemma_domain_delegates_to_helper(wallet_js_source):
    assert "return isLemmaHostname(window.location.hostname)" in wallet_js_source


@pytest.mark.unit
def test_lemma_wallet_rejects_hostname_substring_matching(wallet_js_source):
    assert "hostname.includes('lemma.id')" not in wallet_js_source
    assert "includes('localhost')" not in wallet_js_source
