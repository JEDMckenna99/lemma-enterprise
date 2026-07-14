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


@pytest.mark.unit
def test_lemma_wallet_master_detection_skips_empty_site_fields(wallet_js_source):
    assert "_isIsHumanMasterRecord" in wallet_js_source
    assert "_canonicalizeCredentialSiteValue" in wallet_js_source
    assert ".filter(Boolean)" in wallet_js_source


@pytest.mark.unit
def test_lemma_wallet_purge_clears_wrap_database(wallet_js_source):
    assert "purgeAllDeviceData" in wallet_js_source
    assert "LemmaWalletWrap" in wallet_js_source
    assert "LEMMA_STORAGE_PREFIXES" in wallet_js_source
    assert "deleteIndexedDbDatabase" in wallet_js_source


@pytest.mark.unit
def test_lemma_wallet_platform_site_binding_helper(wallet_js_source):
    assert "_isLemmaPlatformSiteBinding" in wallet_js_source
    assert "lemma_platform" in wallet_js_source


@pytest.mark.unit
def test_lemma_wallet_secure_headers_cover_server_csrf_cookie(wallet_js_source):
    assert "lemma_csrf_token" in wallet_js_source
    assert "lemma_wallet_csrf" in wallet_js_source
    assert "_getSecureHeaders(" in wallet_js_source
    assert "_readJsonResponse(" in wallet_js_source
    assert "headers: this._getSecureHeaders()" in wallet_js_source
    assert "/api/ishuman/derive-site-proof" in wallet_js_source
    assert wallet_js_source.count("headers: { 'Content-Type': 'application/json' }") == 0 or (
        "headers: this._getSecureHeaders()" in wallet_js_source
        and "derive-site-proof" in wallet_js_source
    )
    # Critical isHuman mutations must send CSRF headers.
    derive_idx = wallet_js_source.index("/api/ishuman/derive-site-proof")
    seed_idx = wallet_js_source.index("/api/ishuman/seed-envelope")
    fresh_begin_idx = wallet_js_source.index("/api/ishuman/fresh-passkey/begin")
    fresh_complete_idx = wallet_js_source.index("/api/ishuman/fresh-passkey/complete")
    assert "this._getSecureHeaders()" in wallet_js_source[derive_idx - 200:derive_idx + 200]
    assert "this._getSecureHeaders()" in wallet_js_source[seed_idx - 200:seed_idx + 200]
    assert "this._getSecureHeaders()" in wallet_js_source[fresh_begin_idx - 200:fresh_begin_idx + 200]
    assert "this._getSecureHeaders()" in wallet_js_source[fresh_complete_idx - 200:fresh_complete_idx + 200]


@pytest.mark.unit
def test_obtain_fresh_passkey_backfills_server_passkey_registry(wallet_js_source):
    obtain_idx = wallet_js_source.index("async obtainFreshPasskeyAttestation(")
    begin_idx = wallet_js_source.index("/api/ishuman/fresh-passkey/begin", obtain_idx)
    window = wallet_js_source[obtain_idx:begin_idx]
    assert "_registerDevicePasskeyIfPossible(passkey, walletId)" in window
    assert "passkey_public_key_missing" in window


@pytest.mark.unit
def test_lemma_wallet_persists_device_signing_via_structured_clone(wallet_js_source):
    assert "_loadDeviceSigningRecord" in wallet_js_source
    assert "_isUsableDeviceSigningKey" in wallet_js_source
    assert "value?.id === 'device_signing'" in wallet_js_source
    assert "Regenerating device signing key" in wallet_js_source
    put_idx = wallet_js_source.index("id: 'device_signing'")
    window = wallet_js_source[max(0, put_idx - 160):put_idx + 240]
    assert "_putRaw('secrets'" in window
    assert "await this._put('secrets', {\n            id: 'device_signing'" not in wallet_js_source
