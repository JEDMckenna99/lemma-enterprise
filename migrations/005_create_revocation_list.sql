-- Migration: Create revocation_list table for bloom filter distribution
-- This table stores revoked credentials for the global bloom filter

-- Create revocation_list table if it doesn't exist
CREATE TABLE IF NOT EXISTS revocation_list (
    id SERIAL PRIMARY KEY,
    credential_id VARCHAR(255) UNIQUE NOT NULL,      -- Unique credential identifier (for bloom filter lookup)
    lemma_id VARCHAR(255),                           -- Alias for credential_id (backward compatibility)
    lemma_type VARCHAR(50) NOT NULL DEFAULT 'permission',  -- 'poh' or 'permission'
    site_id VARCHAR(100),                            -- Site ID (NULL for global/PoH revocations)
    user_did VARCHAR(255),                           -- User DID associated with credential
    revoked_by VARCHAR(255),                         -- Who revoked it (admin email or 'user_self_revoke')
    revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When it was revoked
    reason VARCHAR(500),                             -- Revocation reason
    bloom_filter_updated BOOLEAN DEFAULT FALSE,      -- Has bloom filter been updated?
    metadata JSONB DEFAULT '{}'::jsonb               -- Additional metadata
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_revocation_credential_id ON revocation_list(credential_id);
CREATE INDEX IF NOT EXISTS idx_revocation_lemma_id ON revocation_list(lemma_id);
CREATE INDEX IF NOT EXISTS idx_revocation_site_id ON revocation_list(site_id);
CREATE INDEX IF NOT EXISTS idx_revocation_user_did ON revocation_list(user_did);
CREATE INDEX IF NOT EXISTS idx_revocation_revoked_at ON revocation_list(revoked_at);
CREATE INDEX IF NOT EXISTS idx_revocation_bloom_updated ON revocation_list(bloom_filter_updated);

-- Add trigger to set lemma_id from credential_id if not provided
CREATE OR REPLACE FUNCTION sync_lemma_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.lemma_id IS NULL THEN
        NEW.lemma_id := NEW.credential_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_sync_lemma_id ON revocation_list;
CREATE TRIGGER tr_sync_lemma_id
    BEFORE INSERT ON revocation_list
    FOR EACH ROW
    EXECUTE FUNCTION sync_lemma_id();

-- Comment explaining the table
COMMENT ON TABLE revocation_list IS 'Stores revoked credentials for bloom filter distribution. Credentials are added here when revoked and synced to the global bloom filter for client-side checking.';
COMMENT ON COLUMN revocation_list.credential_id IS 'Unique credential identifier used for bloom filter membership checking';
COMMENT ON COLUMN revocation_list.lemma_id IS 'Alias for credential_id (backward compatibility with older code)';
COMMENT ON COLUMN revocation_list.bloom_filter_updated IS 'Whether this revocation has been synced to the bloom filter';

