-- Migration: Add passkeys table for WebAuthn support
-- Run this against your Heroku Postgres database

CREATE TABLE IF NOT EXISTS passkeys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    credential_id VARCHAR(1024) UNIQUE NOT NULL,
    public_key TEXT NOT NULL,
    sign_count INTEGER DEFAULT 0,
    
    -- Device/authenticator info
    device_name VARCHAR(255),
    authenticator_type VARCHAR(50),
    transports JSONB DEFAULT '[]'::jsonb,
    
    -- Attestation (for hardware verification)
    attestation_format VARCHAR(50),
    attestation_data TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_passkeys_user_id ON passkeys(user_id);
CREATE INDEX IF NOT EXISTS idx_passkeys_credential_id ON passkeys(credential_id);
CREATE INDEX IF NOT EXISTS idx_passkeys_active ON passkeys(user_id, is_active) WHERE is_active = TRUE;

-- Comment
COMMENT ON TABLE passkeys IS 'WebAuthn passkey credentials for hardware-backed authentication';
