-- Migration 019: Create site_api_keys table
-- ===========================================
-- Stores API keys for each site with rotation support

CREATE TABLE IF NOT EXISTS site_api_keys (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    key_name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,      -- SHA-256 hash of the full key
    key_prefix VARCHAR(20) NOT NULL,           -- First 12 chars + ... for display
    key_type VARCHAR(10) DEFAULT 'live',       -- 'test' or 'live'
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),                   -- PPID of creator
    last_used TIMESTAMP,
    expires_at TIMESTAMP,
    permissions JSONB DEFAULT '["read", "write"]'::jsonb
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_site_api_keys_site ON site_api_keys(site_id);
CREATE INDEX IF NOT EXISTS idx_site_api_keys_hash ON site_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_site_api_keys_active ON site_api_keys(site_id, is_active);

-- Comments
COMMENT ON TABLE site_api_keys IS 'API keys for site SDK authentication';
COMMENT ON COLUMN site_api_keys.key_hash IS 'SHA-256 hash of full key - original key never stored';
COMMENT ON COLUMN site_api_keys.key_prefix IS 'First 12 chars for display (sk_live_xxxx...)';
