#!/usr/bin/env python3
"""
Database Migration Runner for Lemma IAM
Run this to apply database migrations
"""

import glob
import hashlib
import logging
import os
import sys
import time
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Stable advisory lock key for production migration runs (Section 9).
MIGRATION_ADVISORY_LOCK_KEY = 20260721001
MIGRATION_LOCK_TIMEOUT_SECONDS = 120


class MigrationChecksumDriftError(RuntimeError):
    """Raised when an applied migration file checksum no longer matches the ledger."""


class MigrationLockTimeoutError(RuntimeError):
    """Raised when the migration advisory lock cannot be acquired in time."""


def _table_exists(cursor, table_name):
    """Return True if table exists in current schema path."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        )
        """,
        (table_name,),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def ensure_base_schema(conn):
    """
    Bootstrap core schema for fresh databases.

    Migrations in this repo are incremental and mostly idempotent, but some
    legacy paths assume compatibility tables exist. We create the minimum
    Postgres-compatible bootstrap tables when missing.
    """
    cur = conn.cursor()
    try:
        required_tables = ("user_permissions", "system_config")
        missing_tables = [name for name in required_tables if not _table_exists(cur, name)]

        if not missing_tables:
            logger.info("✅ Base schema already present")
            return True

        logger.info("🧱 Bootstrapping compatibility tables: %s", ", ".join(missing_tables))

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_permissions (
                id SERIAL PRIMARY KEY,
                site_id VARCHAR(50) NOT NULL,
                user_did VARCHAR(255) NOT NULL,
                permission_id VARCHAR(100) NOT NULL,
                granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                granted_by VARCHAR(255),
                expires_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                UNIQUE (site_id, user_did, permission_id)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_permissions
            ON user_permissions (user_did, site_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_site_user_permissions
            ON user_permissions (site_id, user_did)
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS system_config (
                config_key VARCHAR(100) PRIMARY KEY,
                config_value TEXT,
                description TEXT,
                is_public BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()
        logger.info("✅ Base schema bootstrap completed")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("❌ Base schema bootstrap failed: %s", exc)
        return False
    finally:
        cur.close()


def ensure_migration_ledger(conn):
    """Create schema_migrations table used for one-time migration tracking."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("❌ Failed to initialize schema_migrations table: %s", exc)
        return False
    finally:
        cur.close()


def _migration_checksum(migration_file):
    data = Path(migration_file).read_bytes()
    normalized = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def _verify_recorded_checksum(conn, migration_file) -> bool:
    """Return True if migration is recorded with a matching checksum."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT checksum FROM schema_migrations WHERE migration_name = %s",
            (migration_file,),
        )
        row = cur.fetchone()
        if not row:
            return False

        recorded_checksum = row[0]
        current_checksum = _migration_checksum(migration_file)
        if recorded_checksum != current_checksum:
            raise MigrationChecksumDriftError(
                f"Migration '{migration_file}' checksum drift: "
                f"recorded={recorded_checksum} current={current_checksum}"
            )
        return True
    finally:
        cur.close()


def migration_already_applied(conn, migration_file):
    return _verify_recorded_checksum(conn, migration_file)


def record_migration_applied(conn, migration_file):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO schema_migrations (migration_name, checksum)
            VALUES (%s, %s)
            ON CONFLICT (migration_name)
            DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = NOW()
            """,
            (migration_file, _migration_checksum(migration_file)),
        )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("❌ Failed to record migration '%s': %s", migration_file, exc)
        return False
    finally:
        cur.close()


def get_database_url():
    """Get database URL from environment"""
    return os.getenv("DATABASE_URL") or os.getenv("HEROKU_POSTGRESQL_JADE_URL")


def acquire_migration_lock(conn, *, timeout_seconds: int = MIGRATION_LOCK_TIMEOUT_SECONDS) -> bool:
    """Acquire session-level advisory lock; fail closed on timeout."""
    cur = conn.cursor()
    deadline = time.time() + max(1, timeout_seconds)
    try:
        while time.time() < deadline:
            cur.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (MIGRATION_ADVISORY_LOCK_KEY,),
            )
            acquired = bool(cur.fetchone()[0])
            if acquired:
                logger.info("🔒 Acquired migration advisory lock")
                return True
            time.sleep(1.0)
        return False
    finally:
        cur.close()


def release_migration_lock(conn) -> None:
    cur = conn.cursor()
    try:
        cur.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))
        released = bool(cur.fetchone()[0])
        if released:
            logger.info("🔓 Released migration advisory lock")
    finally:
        cur.close()


def run_migration_sql(conn, migration_file):
    """Execute one migration file on an existing connection."""
    migration_sql = Path(migration_file).read_text(encoding="utf-8")
    logger.info("📝 Running migration: %s", migration_file)
    cur = conn.cursor()
    try:
        cur.execute(migration_sql)
        conn.commit()
        logger.info("✅ Migration completed successfully")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("❌ Migration failed: %s", exc)
        return False
    finally:
        cur.close()


def run_migration(migration_file):
    """
    Run a SQL migration file

    Usage:
        python migrations/run_migration.py migrations/001_create_audit_logs.sql
    """
    database_url = get_database_url()

    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        return False

    if not Path(migration_file).is_file():
        logger.error("❌ Migration file not found: %s", migration_file)
        return False

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        if not ensure_migration_ledger(conn):
            return False
        if not acquire_migration_lock(conn):
            logger.error("❌ Could not acquire migration advisory lock")
            return False
        if migration_already_applied(conn, migration_file):
            logger.info("⏭️ Skipping already-applied migration: %s", migration_file)
            return True
        if not run_migration_sql(conn, migration_file):
            return False
        return record_migration_applied(conn, migration_file)
    except MigrationChecksumDriftError as exc:
        logger.error("❌ %s", exc)
        return False
    finally:
        if conn is not None:
            try:
                release_migration_lock(conn)
            finally:
                conn.close()


def run_all_migrations():
    """Run all pending migrations in order under one advisory lock."""
    migration_files = sorted(glob.glob("migrations/*.sql"))

    if not migration_files:
        logger.warning("⚠️ No migration files found")
        return True

    database_url = get_database_url()
    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        return False

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        if not ensure_base_schema(conn):
            return False
        if not ensure_migration_ledger(conn):
            return False
        if not acquire_migration_lock(conn):
            raise MigrationLockTimeoutError(
                f"Could not acquire migration lock within {MIGRATION_LOCK_TIMEOUT_SECONDS}s"
            )

        logger.info("Found %s migration files", len(migration_files))
        for migration_file in migration_files:
            if migration_already_applied(conn, migration_file):
                logger.info("⏭️ Skipping already-applied migration: %s", migration_file)
                continue

            if not run_migration_sql(conn, migration_file):
                logger.error("❌ Migration failed, stopping: %s", migration_file)
                return False

            if not record_migration_applied(conn, migration_file):
                logger.error("❌ Could not record migration, stopping: %s", migration_file)
                return False

        logger.info("✅ All migrations completed successfully")
        return True
    except MigrationChecksumDriftError as exc:
        logger.error("❌ %s", exc)
        return False
    except MigrationLockTimeoutError as exc:
        logger.error("❌ %s", exc)
        return False
    except Exception as exc:
        logger.error("❌ Migration runner failed: %s", exc)
        return False
    finally:
        if conn is not None:
            try:
                release_migration_lock(conn)
            finally:
                conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        ok = run_migration(sys.argv[1])
    else:
        ok = run_all_migrations()
    raise SystemExit(0 if ok else 1)
