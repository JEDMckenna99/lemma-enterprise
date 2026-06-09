from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRYPTO_JS = ROOT / "static" / "js" / "wallet-at-rest-crypto.js"
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


@pytest.fixture(name="crypto_js")
def fixture_crypto_js() -> str:
    return CRYPTO_JS.read_text(encoding="utf-8")


@pytest.fixture(name="wallet_js")
def fixture_wallet_js() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_ishuman_cache_in_sensitive_stores(crypto_js):
    assert "'ishuman_cache'" in crypto_js
    assert "SENSITIVE_STORES = ['secrets', 'profiles', 'session', 'lemmas', 'ishuman_cache']" in crypto_js


@pytest.mark.unit
def test_put_ishuman_cache_uses_encrypted_put(wallet_js):
    start = wallet_js.index("async _putIsHumanCacheRecord(credential)")
    end = wallet_js.index("async syncIsHumanCacheFromWallet()", start)
    block = wallet_js[start:end]
    assert "await this._put('ishuman_cache', record)" in block
    assert "_putRaw('ishuman_cache'" not in block
    assert "storage key unavailable" in block


@pytest.mark.unit
def test_get_ishuman_cache_uses_encrypted_get_all(wallet_js):
    start = wallet_js.index("async getIsHumanCredentialsFromCache()")
    end = wallet_js.index("async hasIsHumanMasterInCache()", start)
    block = wallet_js[start:end]
    assert "await this._getAll('ishuman_cache')" in block
    assert "_getAllRaw('ishuman_cache'" not in block


@pytest.mark.unit
def test_migrate_plaintext_stores_includes_ishuman_cache(wallet_js):
    start = wallet_js.index("async _migratePlaintextStores()")
    end = wallet_js.index("async _getRaw(storeName, key)", start)
    block = wallet_js[start:end]
    assert "_getAllRaw('ishuman_cache')" in block
    assert "await this._put('ishuman_cache', cached)" in block


@pytest.mark.unit
def test_ishuman_cache_fail_closed_without_at_rest_key(wallet_js):
    start = wallet_js.index("async _encryptStoredValue(storeName, value)")
    end = wallet_js.index("async _decryptStoredValue(raw)", start)
    block = wallet_js[start:end]
    assert "storeName === 'ishuman_cache'" in block
    assert "storage_key_unavailable" in block


@pytest.mark.unit
def test_wallet_db_version_bumped_for_cache_encryption(wallet_js):
    assert "WALLET_DB_VERSION = 7" in wallet_js


@pytest.mark.unit
def test_encrypted_storage_needs_key_scans_ishuman_cache(wallet_js):
    start = wallet_js.index("async _encryptedStorageNeedsAtRestKey()")
    end = wallet_js.index("async _migratePlaintextStores()", start)
    block = wallet_js[start:end]
    assert "'ishuman_cache'" in block
