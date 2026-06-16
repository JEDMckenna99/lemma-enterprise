"""SQLite persistence for delivery prototype."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    driver_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    credential_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_events (
    event_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    package_id TEXT NOT NULL,
    status TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    network_profile TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_route(db_path: Path, route_id: str, driver_id: str, device_id: str, credential: dict, created_at: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO routes (route_id, driver_id, device_id, credential_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (route_id, driver_id, device_id, json.dumps(credential), created_at),
        )


def get_route(db_path: Path, route_id: str) -> Optional[dict[str, Any]]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM routes WHERE route_id = ?", (route_id,)).fetchone()
        if not row:
            return None
        return {
            "route_id": row["route_id"],
            "driver_id": row["driver_id"],
            "device_id": row["device_id"],
            "credential": json.loads(row["credential_json"]),
            "created_at": row["created_at"],
        }


def list_routes(db_path: Path) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT route_id, driver_id, device_id, created_at FROM routes ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]


def save_event(
    db_path: Path,
    event_id: str,
    route_id: str,
    package_id: str,
    status: str,
    event: dict,
    created_at: str,
    synced_at: Optional[str] = None,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO delivery_events
            (event_id, route_id, package_id, status, event_json, created_at, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, route_id, package_id, status, json.dumps(event), created_at, synced_at),
        )


def get_events_for_route(db_path: Path, route_id: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM delivery_events WHERE route_id = ? ORDER BY created_at ASC",
            (route_id,),
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "route_id": row["route_id"],
                "package_id": row["package_id"],
                "status": row["status"],
                "event": json.loads(row["event_json"]),
                "created_at": row["created_at"],
                "synced_at": row["synced_at"],
            }
            for row in rows
        ]


def save_benchmark_run(db_path: Path, run_id: str, mode: str, network_profile: str, results: dict, created_at: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO benchmark_runs (run_id, mode, network_profile, results_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, mode, network_profile, json.dumps(results), created_at),
        )


def list_benchmark_runs(db_path: Path) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM benchmark_runs ORDER BY created_at DESC").fetchall()
        return [
            {
                "run_id": row["run_id"],
                "mode": row["mode"],
                "network_profile": row["network_profile"],
                "results": json.loads(row["results_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
