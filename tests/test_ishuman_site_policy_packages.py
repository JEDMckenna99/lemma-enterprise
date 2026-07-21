"""Parity tests for site block/doubt enforcement helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE_POLICY_PATH = ROOT / "packages" / "ishuman-verify-py" / "lemma_ishuman_site_policy.py"
VERIFY_PATH = ROOT / "packages" / "ishuman-verify-py" / "lemma_ishuman_verify.py"


def _load_module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


site_policy = _load_module("lemma_ishuman_site_policy_tests", SITE_POLICY_PATH)
InMemorySitePolicyStore = site_policy.InMemorySitePolicyStore
LemmaCheckPolicyStore = site_policy.LemmaCheckPolicyStore
SiteDecision = site_policy.SiteDecision
enforce_site_policy = site_policy.enforce_site_policy


@pytest.mark.unit
def test_in_memory_store_blocked():
    store = InMemorySitePolicyStore(blocked={"did:lemma:ppid_blocked"})
    available, decision, err = store.check("did:lemma:ppid_blocked")
    assert available is True
    assert decision.blocked is True
    assert err == "ok"


@pytest.mark.unit
def test_in_memory_store_doubted():
    store = InMemorySitePolicyStore(doubted={"did:lemma:ppid_doubted"})
    available, decision, err = store.check("did:lemma:ppid_doubted")
    assert available is True
    assert decision.doubt_required is True
    assert err == "ok"


@pytest.mark.unit
def test_enforce_site_policy_clean():
    store = InMemorySitePolicyStore()
    ok, reason, decision = enforce_site_policy(
        ppid="did:lemma:ppid_clean",
        policy_store=store,
    )
    assert ok is True
    assert reason == "ok"
    assert decision is None


@pytest.mark.unit
def test_enforce_site_policy_blocked_canonical():
    store = InMemorySitePolicyStore(blocked={"did:lemma:ppid_blocked"})
    ok, reason, decision = enforce_site_policy(
        ppid="did:lemma:ppid_blocked",
        policy_store=store,
    )
    assert ok is False
    assert reason == "site_blocked"
    assert decision is not None
    assert decision.blocked is True


@pytest.mark.unit
def test_enforce_site_policy_legacy_carry_forward():
    store = InMemorySitePolicyStore(blocked={"did:lemma:ppid_legacy"})
    ok, reason, _decision = enforce_site_policy(
        ppid="did:lemma:ppid_canonical",
        policy_store=store,
        legacy_ppid="did:lemma:ppid_legacy",
    )
    assert ok is False
    assert reason == "site_blocked"


@pytest.mark.unit
def test_enforce_site_policy_doubt_required():
    store = InMemorySitePolicyStore(doubted={"did:lemma:ppid_doubt"})
    ok, reason, decision = enforce_site_policy(
        ppid="did:lemma:ppid_doubt",
        policy_store=store,
    )
    assert ok is False
    assert reason == "doubt_required"
    assert decision is not None
    assert decision.doubt_required is True


@pytest.mark.unit
def test_enforce_site_policy_not_configured():
    ok, reason, decision = enforce_site_policy(
        ppid="did:lemma:ppid_any",
        policy_store=None,
        require_policy=True,
    )
    assert ok is False
    assert reason == "site_policy_not_configured"
    assert decision is None


@pytest.mark.unit
def test_lemma_check_policy_store_fail_closed_on_error():
    store = LemmaCheckPolicyStore(
        site_id="example.com",
        lemma_origin="https://lemma.id",
        fail_closed=True,
    )
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
        available, decision, err = store.check("did:lemma:ppid_remote")
    assert available is False
    assert decision.blocked is False
    assert err == "site_policy_unavailable"


@pytest.mark.unit
def test_lemma_check_policy_store_parses_block_response():
    store = LemmaCheckPolicyStore(
        site_id="example.com",
        lemma_origin="https://lemma.id",
    )
    payload = json.dumps(
        {
            "success": True,
            "blocked": True,
            "doubt_required": False,
            "reason": "site_block",
        }
    ).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=mock_resp):
        available, decision, err = store.check("did:lemma:ppid_remote")

    assert available is True
    assert decision.blocked is True
    assert err == "ok"


@pytest.mark.unit
def test_verify_with_policy_blocks_before_business_logic(monkeypatch):
    verify_mod = _load_module("lemma_ishuman_verify_policy_tests", VERIFY_PATH)
    ctx = verify_mod.VerificationContext(site_id="example.com", required_assurance="passkey")
    monkeypatch.setattr(
        ctx,
        "verify",
        lambda _presentation: ctx.Result(
            True,
            "valid",
            ppid="did:lemma:ppid_blocked",
            assurance="passkey",
        ),
    )
    store = InMemorySitePolicyStore(blocked={"did:lemma:ppid_blocked"})
    result = ctx.verify_with_policy({"credential": {}}, policy_store=store)
    assert result.ok is False
    assert result.reason == "site_blocked"
    assert result.ppid == "did:lemma:ppid_blocked"
