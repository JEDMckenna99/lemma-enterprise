#!/usr/bin/env python3
"""Apply migration 038 only (idempotent, additive cutover schema)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 1
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "migrations", "038_privacy_minimized_site_state.sql",
    )
    with open(path, "r", encoding="utf-8") as handle:
        sql = handle.read()
    conn = psycopg2.connect(db_url, sslmode="require")
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("Migration 038 applied successfully.")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"Migration 038 failed: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
