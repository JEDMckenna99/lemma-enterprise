"""Scale-hardening tests: Postgres pool wrapper, Redis factory, bloom cache headers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


@pytest.mark.unit
def test_shared_redis_is_singleton(monkeypatch):
    from api import redis_client as rc

    rc.reset_shared_redis_for_tests()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.delenv("REDISCLOUD_URL", raising=False)
    monkeypatch.delenv("REDIS_TLS_URL", raising=False)

    fake = MagicMock()
    fake.ping.return_value = True

    with patch("redis.from_url", return_value=fake) as from_url:
        a = rc.get_shared_redis()
        b = rc.get_shared_redis()
        assert a is b is fake
        assert from_url.call_count == 1

    rc.reset_shared_redis_for_tests()


@pytest.mark.unit
def test_pooled_connection_close_returns_to_pool(monkeypatch):
    from api import database as db

    db.reset_db_pools_for_tests()

    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur

    pool = MagicMock()
    pool.getconn.return_value = raw

    monkeypatch.setattr(db, "_get_raw_pg_pool", lambda: pool)

    conn = db.get_db_connection()
    assert pool.getconn.called
    conn.close()
    pool.putconn.assert_called_once_with(raw)
    db.reset_db_pools_for_tests()


@pytest.mark.unit
def test_bloom_filter_sets_etag_and_supports_304(monkeypatch):
    from api import revocation_api as rev_api

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(rev_api.revocation_api)

    class _Cursor:
        def execute(self, _sql):
            return None

        def fetchall(self):
            return []

        def fetchone(self):
            return (42,)

        def close(self):
            return None

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    monkeypatch.setattr("api.database.get_db_connection", lambda: _Conn())
    monkeypatch.setattr(
        "api.bloom_snapshot._issuer_signing_material",
        lambda: _fake_bloom_keys(),
    )
    rev_api._BLOOM_CACHE["payload"] = None
    rev_api._BLOOM_CACHE["count"] = None
    rev_api._BLOOM_CACHE["sequence"] = None
    rev_api._BLOOM_CACHE["built_at"] = 0.0

    with app.test_client() as client:
        first = client.get("/api/revocation/bloom-filter")
        assert first.status_code == 200
        assert first.headers.get("ETag") == '"bloom-seq-42"'
        assert "max-age=" in (first.headers.get("Cache-Control") or "")

        second = client.get(
            "/api/revocation/bloom-filter",
            headers={"If-None-Match": '"bloom-seq-42"'},
        )
        assert second.status_code == 304
        assert second.headers.get("ETag") == '"bloom-seq-42"'


def _fake_bloom_keys():
    from api.wallet_keys import derive_wallet_signing_keypair

    priv, pub = derive_wallet_signing_keypair("ab" * 32)
    return priv, pub, "did:lemma:" + ("b" * 64)


@pytest.mark.unit
def test_didit_circuit_opens_after_failures(monkeypatch):
    from api.circuit_breaker import CircuitBreaker
    from billing import didit_manager as dm

    breaker = CircuitBreaker("didit-test", failure_threshold=2, recovery_seconds=60)
    monkeypatch.setattr(dm, "_didit_breaker", breaker)

    mgr = dm.DiditManager.__new__(dm.DiditManager)
    mgr.enabled = True
    mgr.api_base = "https://example.test"
    mgr.api_key = "k"
    mgr.workflow_id = "wf"

    class _Resp:
        status_code = 500
        text = "boom"
        content = b""

        def json(self):
            return {}

    with patch.object(dm.requests, "post", return_value=_Resp()):
        r1 = mgr.create_identity_verification_session("u1", "https://return")
        r2 = mgr.create_identity_verification_session("u1", "https://return")
        r3 = mgr.create_identity_verification_session("u1", "https://return")

    assert r1["success"] is False
    assert r2["success"] is False
    assert r3["error"] == "didit_circuit_open"
