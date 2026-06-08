import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from api.services.wallet_service import (
    _is_site_scoped_credential,
    await_site_revocation,
)


@pytest.mark.parametrize(
    "credential_type,expected",
    [
        ("permission", True),
        ("identity", True),
        ("email", True),
        ("poh", False),
        ("unknown", False),
    ],
)
def test_site_scoped_credential_classification(credential_type, expected):
    assert _is_site_scoped_credential(credential_type, "site_specific") is expected


def test_await_site_revocation_syncs_bloom(monkeypatch):
    synced = []

    class _FakeRevocation:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.bloom_filter_updated = False

    class _FakeQuery:
        def __init__(self, store):
            self.store = store
            self._kwargs = {}

        def filter_by(self, **kwargs):
            self._kwargs = kwargs
            return self

        def first(self):
            for row in self.store:
                if row.lemma_id == self._kwargs.get("lemma_id"):
                    return row
            return None

    stored = []

    class _FakeSession:
        def query(self, _model):
            return _FakeQuery(stored)

        def add(self, row):
            stored.append(row)

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr("api.database.get_db", lambda: _FakeSession())
    monkeypatch.setattr(
        "api.permission_verification.sync_revocation_keys",
        lambda credential_id: synced.append(credential_id) or True,
    )
    monkeypatch.setattr(
        "api.bloom_snapshot.invalidate_bloom_filter_cache",
        lambda: None,
    )

    ok = await_site_revocation("cred_identity_site_1", "user_requested", "example.com")

    assert ok is True
    assert len(stored) == 1
    assert stored[0].lemma_id == "cred_identity_site_1"
    assert stored[0].site_id == "example.com"
    assert stored[0].bloom_filter_updated is True
    assert synced == ["cred_identity_site_1"]
