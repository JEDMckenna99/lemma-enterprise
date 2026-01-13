-- Migration 012: Wallet Credentials Server Sync
-- Enables unified wallet view by syncing credentials across sites via server
-- Credentials remain locally verifiable (Ed25519) - server is just for storage/sync

-- Wallet credentials table: Synced credentials for unified wallet view
CREATE TABLE IF NOT EXISTS wallet_credentials (
    id SERIAL PRIMARY KEY,
    wallet_id VARCHAR(255) NOT NULL,            -- e.g., "wallet_8f5edafc3bb757d4842a2f3d2b30910a"
    credential_id VARCHAR(255) NOT NULL,        -- e.g., "cred_49e7962d-4bfd-4412-bab5-152a8c6cdc9c"
    site_id VARCHAR(255),                       -- e.g., "site_2edbd871d24f" or domain name
    site_domain VARCHAR(255),                   -- Human-readable domain for display
    credential_data JSONB NOT NULL,             -- Full signed credential blob (verifiable offline)
    package_type VARCHAR(50) DEFAULT 'permission', -- permission, identity, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,                       -- Optional credential expiry
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    
    -- Ensure no duplicate credentials per wallet
    CONSTRAINT unique_wallet_credential UNIQUE (wallet_id, credential_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_wallet_credentials_wallet ON wallet_credentials(wallet_id);
CREATE INDEX IF NOT EXISTS idx_wallet_credentials_site ON wallet_credentials(site_id);
CREATE INDEX IF NOT EXISTS idx_wallet_credentials_active ON wallet_credentials(wallet_id, revoked) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_wallet_credentials_type ON wallet_credentials(wallet_id, package_type);

-- Comment explaining the purpose
COMMENT ON TABLE wallet_credentials IS 'Server-synced credentials for unified wallet view. Credentials are cryptographically signed and verifiable offline - server storage is for convenience only.';
