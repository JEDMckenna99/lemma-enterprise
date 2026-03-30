-- Migration 007: Make DID the primary identifier, email optional
-- For wallet-first authentication, DID (from passkey) is the primary identifier
-- Email becomes optional and used only for notifications/recovery

-- Add user_did column to customers if it doesn't exist
ALTER TABLE customers 
ADD COLUMN IF NOT EXISTS user_did VARCHAR(255);

-- Create index on user_did for fast lookups
CREATE INDEX IF NOT EXISTS idx_customers_user_did ON customers(user_did);

-- Make email nullable (was required before)
-- Note: This requires removing the NOT NULL constraint
ALTER TABLE customers 
ALTER COLUMN email DROP NOT NULL;

-- Add unique constraint on user_did (for customers who have one)
-- Using partial unique index to allow multiple NULLs
CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_user_did_unique 
ON customers(user_did) WHERE user_did IS NOT NULL;

-- Backfill: Set user_did from customer_id for existing records that don't have one
UPDATE customers 
SET user_did = 'did:lemma:user:' || customer_id 
WHERE user_did IS NULL AND customer_id IS NOT NULL;

-- Add display_name column (optional, for UI)
ALTER TABLE customers 
ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);

-- Add wallet_id column to link to wallet
ALTER TABLE customers 
ADD COLUMN IF NOT EXISTS wallet_id VARCHAR(255);

-- Create platform_users table for permission system users (separate from billing customers)
CREATE TABLE IF NOT EXISTS platform_users (
    id SERIAL PRIMARY KEY,
    user_did VARCHAR(255) UNIQUE NOT NULL,          -- Primary identifier (did:lemma:user:xxx)
    
    -- Optional identity info
    email VARCHAR(255),                              -- Optional, for notifications only
    display_name VARCHAR(255),                       -- Optional, for UI
    
    -- Wallet linkage
    wallet_id VARCHAR(255),                          -- Browser wallet ID
    passkey_credential_id VARCHAR(255),              -- Primary passkey credential
    
    -- Account state
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',            -- active, suspended, deleted
    
    -- Metadata
    auth_method VARCHAR(50) DEFAULT 'passkey',      -- passkey, email_link, oauth
    verification_level VARCHAR(50) DEFAULT 'base',  -- base, email_verified, human_verified
    
    INDEX idx_platform_users_email (email),
    INDEX idx_platform_users_wallet (wallet_id),
    INDEX idx_platform_users_passkey (passkey_credential_id)
);

-- Link table: which platform users have permissions on which sites
-- This is separate from user_permissions which tracks the actual credential grants
CREATE TABLE IF NOT EXISTS platform_user_sites (
    id SERIAL PRIMARY KEY,
    user_did VARCHAR(255) NOT NULL,                 -- References platform_users.user_did
    site_id VARCHAR(50) NOT NULL,                   -- Site they have access to
    role VARCHAR(50) DEFAULT 'user',                -- user, admin, owner
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    invited_by VARCHAR(255),                        -- Who invited them
    status VARCHAR(20) DEFAULT 'active',            -- active, pending, revoked
    
    UNIQUE (user_did, site_id),
    INDEX idx_user_sites_user (user_did),
    INDEX idx_user_sites_site (site_id)
);

-- Comment explaining the architecture
COMMENT ON TABLE platform_users IS 'Users identified by DID for permission system. Email is optional.';
COMMENT ON COLUMN platform_users.user_did IS 'Primary identifier - derived from passkey or generated';
COMMENT ON COLUMN platform_users.email IS 'Optional - used for notifications and account recovery only';
