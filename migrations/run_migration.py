#!/usr/bin/env python3
"""
Database Migration Runner for Lemma IAM
Run this to apply database migrations
"""

import os
import sys
import psycopg2
from psycopg2 import sql
import logging
from pathlib import Path
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        logger.error(f"❌ Base schema bootstrap failed: {exc}")
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
        logger.error(f"❌ Failed to initialize schema_migrations table: {exc}")
        return False
    finally:
        cur.close()


def _migration_checksum(migration_file):
    data = Path(migration_file).read_bytes()
    return hashlib.sha256(data).hexdigest()


def migration_already_applied(conn, migration_file):
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
            logger.warning(
                "⚠️ Migration '%s' already recorded but checksum changed. "
                "Keeping recorded state and skipping re-run.",
                migration_file,
            )
        return True
    finally:
        cur.close()


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
        logger.error(f"❌ Failed to record migration '{migration_file}': {exc}")
        return False
    finally:
        cur.close()

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL') or os.getenv('HEROKU_POSTGRESQL_JADE_URL')

def run_migration(migration_file):
    """
    Run a SQL migration file
    
    Usage:
        python migrations/run_migration.py migrations/001_create_audit_logs.sql
    """
    database_url = get_database_url()
    
    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        logger.error("   Set DATABASE_URL environment variable")
        return False
    
    try:
        # Read migration file
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        logger.info(f"📝 Running migration: {migration_file}")
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Execute migration
        cur.execute(migration_sql)
        conn.commit()
        
        logger.info(f"✅ Migration completed successfully")
        
        # Close connection
        cur.close()
        conn.close()
        
        return True
        
    except FileNotFoundError:
        logger.error(f"❌ Migration file not found: {migration_file}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

def run_all_migrations():
    """Run all pending migrations in order"""
    import glob
    
    migration_files = sorted(glob.glob('migrations/*.sql'))
    
    if not migration_files:
        logger.warning("⚠️ No migration files found")
        return

    database_url = get_database_url()
    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        logger.error("   Set DATABASE_URL environment variable")
        return False

    try:
        conn = psycopg2.connect(database_url)
        if not ensure_base_schema(conn):
            conn.close()
            return False
        if not ensure_migration_ledger(conn):
            conn.close()
            return False
        conn.close()
    except Exception as exc:
        logger.error(f"❌ Failed to connect for schema bootstrap: {exc}")
        return False
    
    logger.info(f"Found {len(migration_files)} migration files")

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        for migration_file in migration_files:
            if migration_already_applied(conn, migration_file):
                logger.info(f"⏭️ Skipping already-applied migration: {migration_file}")
                continue

            success = run_migration(migration_file)
            if not success:
                logger.error(f"❌ Migration failed, stopping: {migration_file}")
                return False

            if not record_migration_applied(conn, migration_file):
                logger.error(f"❌ Could not record migration, stopping: {migration_file}")
                return False
    finally:
        if conn:
            conn.close()
    
    logger.info("✅ All migrations completed successfully")
    return True

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Run specific migration
        migration_file = sys.argv[1]
        run_migration(migration_file)
    else:
        # Run all migrations
        run_all_migrations()

