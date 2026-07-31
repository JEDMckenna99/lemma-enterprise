#!/usr/bin/env python3
"""One-off prod schema check for CIAM Phase 0-1 migrations."""

from __future__ import annotations

import json
import os
import sys

import psycopg2


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print(json.dumps({"error": "DATABASE_URL missing"}))
        return 2

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT to_regclass('public.identity_subject_aliases')")
        alias_table = cur.fetchone()[0]

        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'site_users'
              AND column_name IN ('user_ppid', 'user_did', 'status', 'role')
            ORDER BY 1
            """
        )
        site_users_cols = [row[0] for row in cur.fetchall()]

        cur.execute(
            """
            SELECT migration_name
            FROM schema_migrations
            WHERE migration_name LIKE '%046%' OR migration_name LIKE '%047%'
            ORDER BY 1
            """
        )
        migrations = [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    result = {
        "alias_table": alias_table,
        "site_users_cols": site_users_cols,
        "migrations": migrations,
        "ok": alias_table == "identity_subject_aliases"
        and "user_ppid" in site_users_cols
        and any("046" in m for m in migrations)
        and any("047" in m for m in migrations),
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
