"""Unit tests for site-local presale code allocation ledger."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_SITES = ROOT / "demo-sites"


def _load_ledger_module():
    name = "presale_allocation_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, DEMO_SITES / "presale_allocation.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_first_claim_succeeds_second_denied():
    mod = _load_ledger_module()
    ledger = mod.PresaleAllocationLedger()
    first = ledger.claim("drop-a", "did:lemma:ppid_one", assurance="ishuman")
    second = ledger.claim("drop-a", "did:lemma:ppid_one", assurance="ishuman")

    assert first.ok is True
    assert first.code is not None
    assert len(first.code) == 8
    assert second.ok is False
    assert second.reason == "allocation_already_claimed"
    assert second.existing is not None
    assert second.existing.code == first.code


def test_legacy_ppid_denied_after_canonical_claim():
    mod = _load_ledger_module()
    ledger = mod.PresaleAllocationLedger()
    canonical = "did:lemma:ppid_canonical"
    legacy = "did:lemma:ppid_legacy"

    first = ledger.claim("drop-a", canonical, legacy_ppid=legacy, assurance="ishuman")
    assert first.ok is True

    via_legacy = ledger.claim("drop-a", legacy, assurance="ishuman")
    assert via_legacy.ok is False
    assert via_legacy.reason == "allocation_already_claimed"


def test_legacy_claim_blocks_canonical_convergence_subject():
    mod = _load_ledger_module()
    ledger = mod.PresaleAllocationLedger()
    legacy = "did:lemma:ppid_legacy"
    canonical = "did:lemma:ppid_canonical"

    first = ledger.claim("drop-a", legacy, assurance="ishuman")
    assert first.ok is True

    second = ledger.claim(
        "drop-a",
        canonical,
        legacy_ppid=legacy,
        assurance="ishuman",
    )
    assert second.ok is False
    assert second.reason == "allocation_already_claimed"


def test_codes_unique_across_ppids():
    mod = _load_ledger_module()
    ledger = mod.PresaleAllocationLedger()
    one = ledger.claim("drop-a", "did:lemma:ppid_a", assurance="ishuman")
    two = ledger.claim("drop-a", "did:lemma:ppid_b", assurance="ishuman")

    assert one.ok is True
    assert two.ok is True
    assert one.code != two.code


def test_reset_clears_drop():
    mod = _load_ledger_module()
    ledger = mod.PresaleAllocationLedger()
    ledger.claim("drop-a", "did:lemma:ppid_a", assurance="ishuman")
    ledger.claim("drop-b", "did:lemma:ppid_b", assurance="ishuman")

    removed = ledger.reset("drop-a")
    assert removed >= 1

    again = ledger.claim("drop-a", "did:lemma:ppid_a", assurance="ishuman")
    assert again.ok is True

    still_blocked = ledger.lookup("drop-b", "did:lemma:ppid_b")
    assert still_blocked is not None


def test_clear_claim_releases_ppid_for_replay():
    mod = _load_ledger_module()
    ledger = mod.PresaleAllocationLedger()
    first = ledger.claim("drop-a", "did:lemma:ppid_a", assurance="ishuman")
    assert first.ok is True

    blocked = ledger.claim("drop-a", "did:lemma:ppid_a", assurance="ishuman")
    assert blocked.ok is False
    assert blocked.reason == "allocation_already_claimed"

    removed = ledger.clear_claim("drop-a", "did:lemma:ppid_a")
    assert removed >= 1
    assert ledger.lookup("drop-a", "did:lemma:ppid_a") is None

    again = ledger.claim("drop-a", "did:lemma:ppid_a", assurance="ishuman")
    assert again.ok is True
    assert again.code != first.code


def test_registration_store_tracks_drop_ppid():
    mod = _load_ledger_module()
    store = mod.PresaleRegistrationStore()
    registered = store.register("drop-a", "did:lemma:ppid_a", email="a@x.com", phone="+1")
    assert registered.ok is True
    assert store.is_registered("drop-a", "did:lemma:ppid_a") is True
    assert store.is_registered("drop-a", "did:lemma:other") is False

    removed = store.reset("drop-a")
    assert removed == 1
    assert store.is_registered("drop-a", "did:lemma:ppid_a") is False
