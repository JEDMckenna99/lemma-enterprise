"""Trust bundle URL failover for offline verifiers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_MODULE = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("lemma_proof_verifier_mirror_test", PY_MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def verifier_mod():
    return _load_module()


@pytest.mark.unit
def test_resolve_trust_bundle_urls_defaults_include_mirror(verifier_mod):
    urls = verifier_mod.resolve_trust_bundle_urls("https://lemma.id", None)
    assert urls[0] == "https://lemma.id/api/revocation/bloom-filter"
    assert "github.io" in urls[1]
    assert urls[1].endswith("bloom-filter.json")


@pytest.mark.unit
def test_resolve_trust_bundle_urls_env_override(monkeypatch, verifier_mod):
    monkeypatch.setenv(
        "LEMMA_TRUST_BUNDLE_URLS",
        "https://mirror-a.example/bloom.json,https://mirror-b.example/bloom.json",
    )
    urls = verifier_mod.resolve_trust_bundle_urls("https://lemma.id", None)
    assert urls == [
        "https://mirror-a.example/bloom.json",
        "https://mirror-b.example/bloom.json",
    ]


@pytest.mark.unit
def test_fetch_signed_bundle_failover(verifier_mod, monkeypatch):
    mod = verifier_mod
    bundle = {
        "success": True,
        "hashed_revoked_ids": [],
        "trust_list": {"version": 1},
        "snapshot": {"sequence_number": 1},
    }

    calls: list[str] = []

    def fake_fetch(url: str):
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("primary down")
        return mod._Snapshot(  # noqa: SLF001
            sequence_number=1,
            revoked_hash_set=set(),
            valid_until_unix=9999999999,
            fetched_at_unix=1.0,
            max_staleness_seconds=900,
            issuers={},
        )

    ctx = mod.VerificationContext(
        site_id="app.example.com",
        trust_bundle_urls=[
            "https://primary.example/bloom-filter",
            "https://mirror.example/bloom-filter.json",
        ],
    )

    with patch.object(ctx, "_fetch_signed_bundle_from_url", side_effect=fake_fetch):
        snap = ctx._fetch_signed_bundle()  # noqa: SLF001

    assert snap.sequence_number == 1
    assert calls == [
        "https://primary.example/bloom-filter",
        "https://mirror.example/bloom-filter.json",
    ]


@pytest.mark.unit
def test_fetch_signed_bundle_all_fail_closed(verifier_mod):
    ctx = verifier_mod.VerificationContext(
        site_id="app.example.com",
        trust_bundle_urls=["https://a.example/fail", "https://b.example/fail"],
    )

    with patch.object(
        ctx,
        "_fetch_signed_bundle_from_url",
        side_effect=RuntimeError("bad signature"),
    ):
        with pytest.raises(RuntimeError, match="trust_refresh_failed"):
            ctx._fetch_signed_bundle()  # noqa: SLF001
