"""Backfill schema_migrations ledger for databases migrated outside run_migration.py."""

from __future__ import annotations

import glob
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from migrations.run_migration import (  # noqa: E402
    _migration_checksum,
    ensure_migration_ledger,
    get_database_url,
    record_migration_applied,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_ledger(*, dry_run: bool = False) -> bool:
    import psycopg2

    database_url = get_database_url()
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    migration_files = sorted(glob.glob(str(REPO_ROOT / "migrations" / "*.sql")))
    conn = psycopg2.connect(database_url)
    try:
        if not ensure_migration_ledger(conn):
            return False

        cur = conn.cursor()
        recorded = 0
        skipped = 0
        for migration_file in migration_files:
            rel = migration_file.replace("\\", "/")
            if "migrations/" not in rel:
                rel = f"migrations/{Path(migration_file).name}"
            cur.execute(
                "SELECT 1 FROM schema_migrations WHERE migration_name = %s",
                (rel,),
            )
            if cur.fetchone():
                skipped += 1
                continue
            checksum = _migration_checksum(rel)
            if dry_run:
                logger.info("would record %s checksum=%s", rel, checksum[:12])
                recorded += 1
                continue
            if not record_migration_applied(conn, rel):
                logger.error("failed to record %s", rel)
                return False
            logger.info("recorded %s", rel)
            recorded += 1
        cur.close()
        logger.info("backfill complete recorded=%s skipped=%s", recorded, skipped)
        return True
    finally:
        conn.close()


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    ok = backfill_ledger(dry_run=dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
