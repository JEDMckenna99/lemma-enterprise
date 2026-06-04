"""Invariants for the isHuman "daily unlock" bundle (Phase 2.2 — superseded).

Phase 2.2 of the v2 plan proposed deleting the localStorage "one passkey per
24h" bundle because an early *plaintext* version was a recurring source of
``envelope_invalid`` / stale-state bugs. That proposal is superseded: the bundle
is now encrypted under a non-extractable device key and is fail-closed, which
addresses the original bug class without losing the "one passkey per 24h" UX.

These tests pin the encrypted + fail-closed invariants so the bundle can't
silently regress back into the unsafe behavior 2.2 was worried about. The repo
has no JS execution harness, so (consistent with ``test_ishuman_lock_period.py``)
we assert against the exact guard logic in the wallet source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


@pytest.fixture(name="wallet_source")
def fixture_wallet_source() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.mark.browser
def test_lock_validity_requires_expiry_secret_and_wallet_id(wallet_source):
    """isIsHumanLockValid() must be true only for a non-expired bundle that has
    both a secret (encrypted ``sec`` or legacy plaintext) and a walletId, and
    must short-circuit when the daily-unlock feature is disabled."""
    assert "isIsHumanLockValid() {" in wallet_source
    assert "if (this._isHumanLockDisabled()) return false;" in wallet_source
    assert "const hasSecret = !!bundle.sec || !!bundle.walletSecret;" in wallet_source
    assert (
        "return expiresAt > Date.now() && hasSecret && !!bundle.walletId;"
        in wallet_source
    )


@pytest.mark.browser
def test_lock_restore_fail_closed_on_expiry_or_missing_wallet(wallet_source):
    """An expired bundle or one missing a walletId must be cleared and rejected,
    never restored."""
    block = (
        "        if (expiresAt <= Date.now() || !bundle.walletId) {\n"
        "            this._clearIsHumanLockBundle();\n"
        "            return false;\n"
        "        }"
    )
    assert block in wallet_source


@pytest.mark.browser
def test_lock_restore_fail_closed_on_undecryptable_envelope(wallet_source):
    """If the encrypted envelope can't be unwrapped (e.g. wrap key rotated or
    cleared) the restore must clear the bundle and demand a fresh passkey rather
    than proceeding without a recovered secret."""
    block = (
        "        if (!walletSecret) {\n"
        "            // Envelope undecryptable (e.g. wrap key cleared/rotated) or empty:\n"
        "            // require a fresh passkey unlock rather than proceeding without a\n"
        "            // secret.\n"
        "            this._clearIsHumanLockBundle();\n"
        "            return false;\n"
        "        }"
    )
    assert block in wallet_source


@pytest.mark.browser
def test_lock_restore_reimports_at_rest_key_and_tags_source(wallet_source):
    """A valid bundle restore must rebuild the session tagged as a daily-unlock
    restore and re-import the PRF-derived at-rest key so encrypted credential
    reads work for the 24h window without another passkey."""
    assert "source: 'daily_unlock_bundle'," in wallet_source
    assert "this._atRestKey = await mod.importStorageKey(raw);" in wallet_source


@pytest.mark.browser
def test_lock_bundle_sensitive_material_is_encrypted(wallet_source):
    """Sensitive material must be wrapped under the device key (bundle.sec); the
    plaintext path is only a warned, degraded fallback when WebCrypto/IndexedDB
    is unavailable."""
    assert "wrapped = await mod.wrapBundle(sensitive);" in wallet_source
    assert "bundle.sec = wrapped;" in wallet_source
    assert "bundle.secured = true;" in wallet_source
    assert (
        "console.warn('[Lemma] Unlock bundle stored unencrypted (device wrap key unavailable)');"
        in wallet_source
    )


@pytest.mark.browser
def test_lock_bundle_disabled_flag_short_circuits(wallet_source):
    """The runtime opt-out (LEMMA_DISABLE_DAILY_UNLOCK) must disable the bundle
    end-to-end: persist returns early and validity/restore return false. This is
    the escape hatch for ever evaluating per-popup unlock without deleting code."""
    assert "window.LEMMA_DISABLE_DAILY_UNLOCK === true" in wallet_source
    assert "window.LEMMA_DISABLE_DAILY_UNLOCK === 'true'" in wallet_source
    # persist short-circuits
    assert "if (this._isHumanLockDisabled()) return;" in wallet_source
    # validity + restore short-circuit (return false)
    assert wallet_source.count("if (this._isHumanLockDisabled()) return false;") >= 2
