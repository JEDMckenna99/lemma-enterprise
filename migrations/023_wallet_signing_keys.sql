-- Wallet Ed25519 signing keys for local-first assertion auth (Phase 1)
CREATE TABLE IF NOT EXISTS wallet_signing_keys (
    wallet_id      VARCHAR(128) PRIMARY KEY,
    pubkey         BYTEA NOT NULL,
    algorithm      VARCHAR(32) NOT NULL DEFAULT 'ed25519',
    created_at     TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    last_used_at   TIMESTAMP,
    revoked_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wallet_signing_keys_last_used
    ON wallet_signing_keys (last_used_at);
