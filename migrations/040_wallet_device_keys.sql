-- Per-device wallet signing keys (device-bound registry)
ALTER TABLE wallet_signing_keys
    ADD COLUMN IF NOT EXISTS device_id VARCHAR(128);

ALTER TABLE wallet_signing_keys
    ADD COLUMN IF NOT EXISTS device_name VARCHAR(256);

UPDATE wallet_signing_keys
SET device_id = 'legacy'
WHERE device_id IS NULL OR device_id = '';

ALTER TABLE wallet_signing_keys
    ALTER COLUMN device_id SET DEFAULT 'legacy';

ALTER TABLE wallet_signing_keys
    ALTER COLUMN device_id SET NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'wallet_signing_keys_pkey'
          AND conrelid = 'wallet_signing_keys'::regclass
    ) THEN
        ALTER TABLE wallet_signing_keys DROP CONSTRAINT wallet_signing_keys_pkey;
    END IF;
END $$;

ALTER TABLE wallet_signing_keys
    ADD PRIMARY KEY (wallet_id, device_id);

CREATE INDEX IF NOT EXISTS idx_wallet_signing_keys_wallet_active
    ON wallet_signing_keys (wallet_id)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS wallet_passkeys (
    id SERIAL PRIMARY KEY,
    wallet_id VARCHAR(128) NOT NULL,
    device_id VARCHAR(128) NOT NULL,
    credential_id TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    attestation_format VARCHAR(64),
    device_name VARCHAR(256),
    created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP,
    UNIQUE (wallet_id, device_id, credential_id)
);

CREATE INDEX IF NOT EXISTS idx_wallet_passkeys_wallet_active
    ON wallet_passkeys (wallet_id)
    WHERE revoked_at IS NULL;
