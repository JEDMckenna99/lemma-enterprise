-- Migration 014: Create redirect_tokens table for mobile Safari auth
-- When Safari blocks third-party cookies/storage, we use redirect-based auth
-- Tokens are short-lived (60s), single-use, and stored in DB for multi-dyno Heroku

CREATE TABLE IF NOT EXISTS redirect_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(64) NOT NULL UNIQUE,           -- Cryptographically random token
    wallet_id VARCHAR(255) NOT NULL,             -- The wallet identifier
    wallet_secret TEXT NOT NULL,                 -- The wallet secret (encrypted in transit)
    return_url TEXT,                             -- URL to redirect back to
    expires_at TIMESTAMP NOT NULL,               -- Token expiration (60s from creation)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookups by token
CREATE INDEX IF NOT EXISTS idx_redirect_tokens_token ON redirect_tokens(token);

-- Index for cleanup of expired tokens
CREATE INDEX IF NOT EXISTS idx_redirect_tokens_expires_at ON redirect_tokens(expires_at);

-- Privacy note
COMMENT ON TABLE redirect_tokens IS 'Short-lived tokens for redirect-based auth on mobile Safari. Tokens expire in 60s and are single-use.';
