"""Pytest fixtures for delivery prototype."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def app_module():
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app_module):
    return app_module.test_client()


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    keys_dir = tmp_path / "keys"
    monkeypatch.setattr("config.DB_PATH", db_path)
    monkeypatch.setattr("config.KEYS_DIR", keys_dir)
    monkeypatch.setattr("config.ISSUER_KEY_PATH", keys_dir / "issuer_private.pem")
    monkeypatch.setattr("config.DEVICE_KEY_PATH", keys_dir / "device_private.pem")
    import app as app_mod

    monkeypatch.setattr(app_mod, "DB_PATH", db_path)
    from models.db import init_db

    init_db(db_path)
    return db_path


@pytest.fixture
def seeded_route(client, temp_db):
    res = client.post("/api/routes", json={
        "route_id": "R-TEST",
        "driver_id": "D-1",
        "device_id": "DEVICE-001",
        "package_count": 3,
        "stops": ["S-014", "S-015"],
    })
    assert res.status_code == 200
    return res.get_json()


@pytest.fixture
def sample_assignment(seeded_route):
    return seeded_route["packages"][0]["assignment"]
