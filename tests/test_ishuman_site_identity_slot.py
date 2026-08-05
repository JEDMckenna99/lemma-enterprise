"""Source pins for one site-identity slot per hostname (upgrade-in-place)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


@pytest.fixture(name="wallet_js")
def fixture_wallet_js() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_wallet_has_prune_and_assurance_rank(wallet_js):
    assert "async pruneIsHumanCredentialsLocally(" in wallet_js
    assert "_assuranceRank(" in wallet_js
    assert "VERSION = '2.81.0'" in wallet_js


@pytest.mark.unit
def test_dedupe_keeps_one_slot_per_hostname_not_per_assurance(wallet_js):
    start = wallet_js.index("_dedupeCredentialsForTransfer(credentials)")
    end = wallet_js.index("async pruneIsHumanCredentialsLocally(", start)
    body = wallet_js[start:end]
    assert "bySite" in body
    assert "site|assurance" not in body
    assert "_assuranceRank(cred) > _assuranceRank(existing)" in body or \
        "this._assuranceRank(cred) > this._assuranceRank(existing)" in body


@pytest.mark.unit
def test_sync_prunes_before_mirroring_cache(wallet_js):
    start = wallet_js.index("async syncIsHumanCacheFromWallet(")
    end = wallet_js.index("async getIsHumanCredentialsFromCache(", start)
    body = wallet_js[start:end]
    assert "pruneIsHumanCredentialsLocally" in body
    assert body.index("pruneIsHumanCredentialsLocally") < body.index("_putIsHumanCacheRecord")


@pytest.mark.unit
def test_derive_site_proof_prunes_after_store(wallet_js):
    start = wallet_js.index("async deriveAndStoreSiteProof(")
    # Bound loosely by the next major method
    end = wallet_js.index("async reissueMasterCredential(", start)
    body = wallet_js[start:end]
    assert "findIsHumanSiteCredential" in body
    assert "pruneIsHumanCredentialsLocally" in body
    store_at = body.index("await this.storeCredential(derived)")
    prune_at = body.index("pruneIsHumanCredentialsLocally")
    assert store_at < prune_at


@pytest.mark.unit
def test_find_site_credential_prefers_highest_assurance(wallet_js):
    start = wallet_js.index("async findIsHumanSiteCredential(")
    end = wallet_js.index("\n    _credentialRecordAssurance(credential) {", start)
    body = wallet_js[start:end]
    assert "_isIsHumanMasterRecord(credential)" in body
    assert "this._assuranceRank(b) - this._assuranceRank(a)" in body
    assert "prefer highest assurance" in body


@pytest.mark.unit
def test_import_and_remove_touch_cache(wallet_js):
    import_start = wallet_js.index("async _importLinkedIsHumanCredentials(")
    import_end = wallet_js.index("async exportIsHumanCredentialsForBridge(", import_start)
    import_body = wallet_js[import_start:import_end]
    assert "pruneIsHumanCredentialsLocally" in import_body

    remove_start = wallet_js.index("async removeCredential(credentialId)")
    remove_end = wallet_js.index("get isReady", remove_start)
    remove_body = wallet_js[remove_start:remove_end]
    assert "ishuman_cache" in remove_body
