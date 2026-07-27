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
    os.environ.setdefault("LEMMA_IDENTITY_ROOT_PEPPER_V1", "y" * 32)
    os.environ.setdefault("LEMMA_PERSON_ROOT_SALT_V1", "z" * 32)


@pytest.fixture(name="ishuman_test_app")
def fixture_ishuman_test_app():
    from api.ishuman import ishuman_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ishuman_bp)
    return app


@pytest.fixture(name="ishuman_client")
def fixture_ishuman_client(ishuman_test_app, monkeypatch):
    # Section 5 fail-closed Bloom checks: unit tests that are not about
    # revocation availability should see a ready verifier. Tests that need
    # unavailable/revoked statuses override this monkeypatch.
    monkeypatch.setattr(
        "api.revocation_verifier.check_revocation_candidate",
        lambda _candidate: "ok",
    )
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
def attach_wallet_assertion(wallet_seed):
    """Attach a valid wallet_assertion to an API request body."""

    def _attach(body: dict, field_names: list[str], *, wallet_id: str | None = None, wallet_secret: str | None = None):
        from api.wallet_authn import (
            issue_device_enrollment_grant,
            issue_wallet_challenge,
            register_wallet_signing_key,
        )
        from api.wallet_keys import build_wallet_assertion, register_self_signature

        wid = (wallet_id or body.get("wallet_id") or wallet_seed["wallet_id"]).strip()
        secret = (wallet_secret or body.get("wallet_secret") or wallet_seed["wallet_secret"]).strip()
        pubkey_b64, sig_b64 = register_self_signature(wid, secret)
        # Idempotent same-key re-register skips the grant. New device keys need
        # a one-time enrollment grant (WebAuthn enroll, transfer, or recovery).
        reg = register_wallet_signing_key(
            wallet_id=wid,
            pubkey_b64=pubkey_b64,
            signature_b64=sig_b64,
            enrollment_grant=issue_device_enrollment_grant(
                wallet_id=wid,
                source="test_fixture_enrollment",
            ),
        )
        assert reg.ok, reg.error

        challenge = issue_wallet_challenge(wallet_id=wid)
        field_values = {}
        for name in field_names:
            key = str(name or "").strip()
            raw = body.get(key, body.get(name))
            if key == "issue_mode" and raw is None:
                raw = "site_proof"
            field_values[key] = "" if raw is None else str(raw)

        assertion = build_wallet_assertion(
            wallet_id=wid,
            wallet_secret=secret,
            field_names=field_names,
            field_values=field_values,
            nonce_b64=challenge["nonce"],
        )
        out = dict(body)
        out.setdefault("wallet_id", wid)
        out.pop("wallet_secret", None)
        out["wallet_assertion"] = {
            "nonce": assertion.nonce,
            "signature": assertion.signature,
        }
        return out

    return _attach



# Assertion field lists for wallet Ed25519 endpoint auth (Phase 1)
DERIVE_ASSERTION_FIELDS = ["master_credential_id", "target_site", "site_signing_pubkey", "issue_mode"]
START_ASSERTION_FIELDS = ["return_url"]


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
    def _factory(**overrides):
        row = SimpleNamespace(
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
        self._limit: int | None = None

    def filter_by(self, **kwargs):
        self._filters.update(kwargs)
        return self

    def first(self):
        for row in self._rows:
            if all(getattr(row, key, None) == value for key, value in self._filters.items()):
                return row
        return None

    def all(self):
        rows = [
            row
            for row in self._rows
            if all(getattr(row, key, None) == value for key, value in self._filters.items())
        ]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def one(self):
        rows = self.all()
        if len(rows) != 1:
            raise AssertionError(f"Expected one row, found {len(rows)}")
        return rows[0]

    def limit(self, value):
        self._limit = value
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return len(self.all())


class _FakeDbSession:
    def __init__(self, store: FakeStore):
        self._store = store

    def query(self, model):
        rows = self._store.data[model.__name__]
        return _FakeQuery(rows)

    def add(self, obj):
        self._store.data[obj.__class__.__name__].append(obj)

    def delete(self, obj):
        rows = self._store.data[obj.__class__.__name__]
        try:
            rows.remove(obj)
        except ValueError:
            pass

    def flush(self):
        from sqlalchemy.exc import IntegrityError

        webhook_rows = self._store.data.get("StripeWebhookEvent", [])
        seen: set[str] = set()
        for row in webhook_rows:
            event_id = getattr(row, "event_id", None)
            if not event_id:
                continue
            if event_id in seen:
                raise IntegrityError("duplicate stripe webhook event_id", None, None)
            seen.add(event_id)
        return None

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
