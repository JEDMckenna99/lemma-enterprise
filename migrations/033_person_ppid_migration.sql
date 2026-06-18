-- Migration 033: controlled person merge + site-scoped PPID migration tokens
--
-- When a wallet re-proves with a new government document number, Lemma may
-- merge the old LemmaPerson into the new one (wallet-bound, IDV-gated).
-- Sites opt in to honoring signed ppid_migration.v1 objects delivered at
-- derive-site-proof time — never a global cross-site linkage API.

CREATE TABLE IF NOT EXISTS person_merges (
    id SERIAL PRIMARY KEY,
    merge_id VARCHAR(64) NOT NULL UNIQUE,
    wallet_id VARCHAR NOT NULL,
    old_person_id VARCHAR NOT NULL,
    new_person_id VARCHAR NOT NULL,
    old_document_root_hash VARCHAR(64),
    new_document_root_hash VARCHAR(64) NOT NULL,
    provider_session_id VARCHAR,
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_person_merges_wallet_id
    ON person_merges (wallet_id);

CREATE INDEX IF NOT EXISTS idx_person_merges_new_person
    ON person_merges (new_person_id);

CREATE TABLE IF NOT EXISTS ppid_migration_issued (
    id SERIAL PRIMARY KEY,
    migration_id VARCHAR(64) NOT NULL UNIQUE,
    merge_id VARCHAR(64) NOT NULL REFERENCES person_merges (merge_id),
    wallet_id VARCHAR NOT NULL,
    target_site VARCHAR(255) NOT NULL,
    legacy_ppid VARCHAR NOT NULL,
    current_ppid VARCHAR NOT NULL,
    nonce VARCHAR(64) NOT NULL,
    issued_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_ppid_migration_wallet_site
    ON ppid_migration_issued (wallet_id, target_site);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ppid_migration_merge_site
    ON ppid_migration_issued (merge_id, target_site);
