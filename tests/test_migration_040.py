"""Optional integration test for migration 040 on a scratch Postgres database."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_MIGRATION_DATABASE_URL", "").startswith("postgres"),
    reason="Set TEST_MIGRATION_DATABASE_URL to a scratch Postgres URL to run migration 040 integration test",
)


@pytest.mark.integration
def test_migration_040_idempotent_and_backfills_legacy():
    import psycopg2

    from scripts.run_migration_040 import main

    db_url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    conn = psycopg2.connect(db_url, sslmode="prefer")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS wallet_signing_keys (
                    wallet_id VARCHAR(128) NOT NULL,
                    pubkey BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
                    last_used_at TIMESTAMP,
                    revoked_at TIMESTAMP,
                    PRIMARY KEY (wallet_id)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO wallet_signing_keys (wallet_id, pubkey)
                VALUES ('wallet_migration_scratch', decode(repeat('ab', 32), 'hex'))
                ON CONFLICT (wallet_id) DO NOTHING
                """
            )
        conn.commit()
    finally:
        conn.close()

    os.environ["DATABASE_URL"] = db_url
    assert main() == 0
    assert main() == 0

    conn = psycopg2.connect(db_url, sslmode="prefer")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT device_id
                FROM wallet_signing_keys
                WHERE wallet_id = 'wallet_migration_scratch'
                """
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "legacy"

            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'wallet_passkeys'
                """
            )
            assert cur.fetchone() is not None
    finally:
        conn.close()
