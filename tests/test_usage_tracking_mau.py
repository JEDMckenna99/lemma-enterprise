"""MAU tracking for site-bound credential issuance."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_hash_ppid_for_mau_is_stable(monkeypatch):
    monkeypatch.setenv("LEMMA_MAU_HASH_KEY", "test_mau_hash_key_32bytes_minimum")

    from api.usage_tracking import _hash_ppid_for_mau

    a = _hash_ppid_for_mau("did:lemma:ppid_abc123")
    b = _hash_ppid_for_mau("did:lemma:ppid_abc123")
    c = _hash_ppid_for_mau("did:lemma:ppid_other")

    assert a == b
    assert a != c
    assert len(a) == 64


@pytest.mark.unit
def test_track_site_proof_mau_deduplicates(monkeypatch):
    store: dict[str, set[str]] = {}

    class FakeRedis:
        def sadd(self, key, value):
            bucket = store.setdefault(key, set())
            before = len(bucket)
            bucket.add(value)
            return 1 if len(bucket) > before else 0

        def expire(self, key, seconds):
            return True

    import api.usage_tracking as usage_tracking

    usage_tracking.REDIS_AVAILABLE = True
    usage_tracking.redis_client = FakeRedis()

    first = usage_tracking.track_site_proof_mau(
        "site_example",
        "did:lemma:ppid_mau_test",
        month="2026-02",
    )
    second = usage_tracking.track_site_proof_mau(
        "site_example",
        "did:lemma:ppid_mau_test",
        month="2026-02",
    )

    assert first is True
    assert second is False
    assert len(store["mau:site_example:2026-02"]) == 1
