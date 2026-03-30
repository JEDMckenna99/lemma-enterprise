-- Migration 013: Create wallet_sessions table for cross-device session sync
-- This enables "one passkey per day" across all devices with the same wallet

CREATE TABLE IF NOT EXISTS wallet_sessions (
    id SERIAL PRIMARY KEY,
    wallet_id VARCHAR(255) NOT NULL UNIQUE,  -- The wallet identifier
    unlocked_at TIMESTAMP NOT NULL,           -- When passkey was last used
    expires_at TIMESTAMP NOT NULL,            -- Session expiration (24h from unlock)
    profile_id VARCHAR(100) DEFAULT 'default', -- Active profile when unlocked
    profile_name VARCHAR(255) DEFAULT 'Personal', -- Profile display name
    device_hint VARCHAR(255),                 -- Optional hint like "iPhone"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookups by wallet_id
CREATE INDEX IF NOT EXISTS idx_wallet_sessions_wallet_id ON wallet_sessions(wallet_id);

-- Index for cleanup of expired sessions
CREATE INDEX IF NOT EXISTS idx_wallet_sessions_expires_at ON wallet_sessions(expires_at);

-- Add comment explaining privacy
COMMENT ON TABLE wallet_sessions IS 'Cross-device session sync for one-passkey-per-day UX. Only stores wallet_id and timestamps - no user identity or activity tracking.';
