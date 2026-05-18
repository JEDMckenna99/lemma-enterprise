from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from flask import Flask


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def _default_test_env() -> None:
    """Provide safe defaults so API modules can import in tests."""
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("LEMMA_PPID_ROOT_KEY", "x" * 32)


@pytest.fixture(name="ishuman_test_app")
def fixture_ishuman_test_app():
    from api.ishuman import ishuman_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_bp)
    return app


@pytest.fixture(name="ishuman_client")
def fixture_ishuman_client(ishuman_test_app):
    with ishuman_test_app.test_client() as client:
        yield client


@pytest.fixture
def wallet_seed() -> dict[str, str]:
    return {
        "wallet_id": "wallet_test_001",
        "wallet_secret": "ab" * 32,
        "master_credential_id": "ishuman_master_seed_001",
        "target_site": "example.com",
    }


@pytest.fixture
def make_ishuman_verification() -> Callable[..., Any]:
    from api.database import IsHumanVerification

    def _factory(**overrides):
        now = datetime.utcnow()
        row = IsHumanVerification(
            session_id=overrides.pop("session_id", "ishuman_sess_seed_001"),
            stripe_session_id=overrides.pop("stripe_session_id", "vs_seed_001"),
            wallet_id=overrides.pop("wallet_id", "wallet_test_001"),
            ppid=overrides.pop("ppid", "did:lemma:ppid_seed"),
            credential_id=overrides.pop("credential_id", "ishuman_master_seed_001"),
            status=overrides.pop("status", "verified"),
            verified_at=overrides.pop("verified_at", now),
            issued_at=overrides.pop("issued_at", now),
            expires_at=overrides.pop("expires_at", now + timedelta(days=30)),
            metadata_json=overrides.pop("metadata_json", {}),
        )
        for key, value in overrides.items():
            setattr(row, key, value)
        return row

    return _factory


@pytest.fixture
def make_derived_credential() -> Callable[..., Any]:
    from api.database import DerivedCredential

    def _factory(**overrides):
        row = DerivedCredential(
            master_credential_id=overrides.pop("master_credential_id", "ishuman_master_seed_001"),
            derived_credential_id=overrides.pop("derived_credential_id", "ishuman_site_seed_001"),
            wallet_id=overrides.pop("wallet_id", "wallet_test_001"),
            target_site=overrides.pop("target_site", "example.com"),
            derived_ppid=overrides.pop("derived_ppid", "did:lemma:ppid_site_seed"),
            is_active=overrides.pop("is_active", True),
            revoked_at=overrides.pop("revoked_at", None),
        )
        for key, value in overrides.items():
            setattr(row, key, value)
        return row

    return _factory


@pytest.fixture
def make_revocation_row() -> Callable[..., Any]:
    from api.database import RevocationList

    def _factory(**overrides):
        now = datetime.utcnow()
        row = RevocationList(
            lemma_id=overrides.pop("lemma_id", f"revoke_{int(now.timestamp())}"),
            credential_id=overrides.pop("credential_id", None),
            lemma_type=overrides.pop("lemma_type", "ishuman"),
            wallet_id=overrides.pop("wallet_id", "wallet_test_001"),
            revocation_type=overrides.pop("revocation_type", "wallet"),
            revoked_by=overrides.pop("revoked_by", "test"),
            reason=overrides.pop("reason", "test"),
        )
        for key, value in overrides.items():
            setattr(row, key, value)
        return row

    return _factory


@dataclass
class FakeStore:
    data: dict[str, list[Any]]
    commits: int = 0
    rollbacks: int = 0


class _FakeQuery:
    def __init__(self, rows: list[Any]):
        self._rows = rows
        self._filters: dict[str, Any] = {}

    def filter_by(self, **kwargs):
        self._filters.update(kwargs)
        return self

    def first(self):
        for row in self._rows:
            if all(getattr(row, key, None) == value for key, value in self._filters.items()):
                return row
        return None

    def all(self):
        return [
            row
            for row in self._rows
            if all(getattr(row, key, None) == value for key, value in self._filters.items())
        ]

    def count(self):
        return len(self.all())

    def order_by(self, *_args, **_kwargs):
        return self


class _FakeDbSession:
    def __init__(self, store: FakeStore):
        self._store = store

    def query(self, model):
        rows = self._store.data[model.__name__]
        return _FakeQuery(rows)

    def add(self, obj):
        self._store.data[obj.__class__.__name__].append(obj)

    def commit(self):
        self._store.commits += 1

    def rollback(self):
        self._store.rollbacks += 1

    def close(self):
        return None


@pytest.fixture
def fake_ishuman_db_session_factory():
    store = FakeStore(data=defaultdict(list))

    def _session_local():
        return _FakeDbSession(store)

    return SimpleNamespace(store=store, session_local=_session_local)
