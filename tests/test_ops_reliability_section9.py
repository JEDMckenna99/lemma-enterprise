"""Section 9 operational reliability tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(name="ops_readiness_app")
def fixture_ops_readiness_app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.get("/health")
    def health():
        from api.operational_readiness import liveness_payload

        return liveness_payload(), 200

    @app.get("/ready")
    def ready():
        from api.operational_readiness import readiness_report

        payload, status_code = readiness_report()
        return payload, status_code

    return app


@pytest.fixture(name="ops_client")
def fixture_ops_client(ops_readiness_app):
    with ops_readiness_app.test_client() as client:
        yield client


def test_migration_checksum_drift_raises():
    from migrations.run_migration import MigrationChecksumDriftError, _verify_recorded_checksum

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = ("deadbeef",)

    migration = REPO_ROOT / "migrations" / "001_create_audit_logs.sql"
    expected = hashlib.sha256(migration.read_bytes()).hexdigest()
    assert expected != "deadbeef"

    with pytest.raises(MigrationChecksumDriftError):
        _verify_recorded_checksum(conn, str(migration))


def test_health_liveness_does_not_touch_database(monkeypatch, ops_client):
    def _boom():
        raise AssertionError("database should not be queried on /health")

    monkeypatch.setattr("api.database.engine.connect", _boom)
    resp = ops_client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "healthy"
    assert "timestamp" in body


def test_ready_fails_when_redis_unavailable(monkeypatch, ops_client):
    monkeypatch.setattr("api.operational_readiness._check_database", lambda: (True, {"ok": True}))
    monkeypatch.setattr(
        "api.operational_readiness._check_redis",
        lambda: (False, {"ok": False, "error": "redis_unavailable"}),
    )
    monkeypatch.setattr("api.operational_readiness._check_crypto", lambda: (True, {"ok": True}))
    monkeypatch.setattr(
        "api.operational_readiness._check_revocation",
        lambda: (True, {"ok": True, "age_seconds": 1.0, "max_age_seconds": 86400}),
    )
    monkeypatch.setattr(
        "api.operational_readiness._check_billing_outbox",
        lambda: (None, {"ok": True, "pending_count": 0}),
    )

    resp = ops_client.get("/ready")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["ready"] is False
    assert body["checks"]["redis"]["ok"] is False


def test_ready_fails_when_revocation_stale(monkeypatch, ops_client):
    monkeypatch.setattr("api.operational_readiness._check_database", lambda: (True, {"ok": True}))
    monkeypatch.setattr("api.operational_readiness._check_redis", lambda: (True, {"ok": True}))
    monkeypatch.setattr("api.operational_readiness._check_crypto", lambda: (True, {"ok": True}))
    monkeypatch.setattr(
        "api.operational_readiness._check_revocation",
        lambda: (
            False,
            {"ok": False, "reason": "bloom_snapshot_stale", "age_seconds": 99999, "max_age_seconds": 60},
        ),
    )
    monkeypatch.setattr(
        "api.operational_readiness._check_billing_outbox",
        lambda: (None, {"ok": True, "pending_count": 0}),
    )

    resp = ops_client.get("/ready")
    assert resp.status_code == 503
    assert resp.get_json()["checks"]["revocation"]["reason"] == "bloom_snapshot_stale"


def test_revocation_freshness_status_when_synced():
    from api import revocation_verifier as rv

    rv._revocation_sync_ready = False
    rv._revocation_last_sync_epoch = None
    ready, detail = rv.revocation_freshness_status()
    assert ready is False
    assert detail["reason"] == "bloom_verifier_not_initialized"

    rv.mark_revocation_sync_ready()
    monkeypatch_verifier = MagicMock()
    monkeypatch_verifier.return_value = MagicMock()
    import api.permission_verification as pv

    original = pv.get_global_verifier
    pv.get_global_verifier = lambda: MagicMock()
    try:
        ready, detail = rv.revocation_freshness_status()
        assert ready is True
        assert detail["ok"] is True
    finally:
        pv.get_global_verifier = original


def test_retention_once_calls_purge(monkeypatch):
    from retention import retention_worker as rw

    class _FakeSession:
        def close(self):
            return None

    monkeypatch.setattr("api.database.SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr("billing.credential_billing.purge_monthly_subject_usage", lambda db: 3)
    monkeypatch.setattr("api.config.is_ishuman_didit_purge_enabled", lambda: True)

    result = rw.run_retention_once()
    assert result["deleted_monthly_subject_rows"] == 3
    assert result["didit_purge_enabled"] is True


def test_procfile_has_release_and_retention_worker():
    proc = (REPO_ROOT / "Procfile").read_text(encoding="utf-8")
    assert "release:" in proc
    assert "retention_worker:" in proc
