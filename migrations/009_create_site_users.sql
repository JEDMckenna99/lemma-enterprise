-- Migration 009: Create site_users table for IAM user management
-- ===============================================================
-- 
-- This table tracks users added to each site by site admins.
-- Users are identified by PPID (Pairwise Pseudonymous Identifier).
-- 
-- PRIVACY: No global user identifiers - each site sees only their PPID.
-- Each user has a DIFFERENT PPID per site (unlinkable across sites).

CREATE TABLE IF NOT EXISTS site_users (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,                    -- References sites.site_id
    user_ppid VARCHAR(255) NOT NULL,                 -- User's PPID for THIS site (did:lemma:ppid_...)
    display_name VARCHAR(255),                       -- Optional display name
    role VARCHAR(50) DEFAULT 'user',                 -- user, moderator, admin
    status VARCHAR(20) DEFAULT 'active',             -- active, suspended, removed
    added_by VARCHAR(255) NOT NULL,                  -- Who added this user (admin PPID or 'api')
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- When user was added
    last_seen TIMESTAMP,                             -- Last activity timestamp
    metadata JSONB,                                  -- Additional site-specific metadata
    
    UNIQUE (site_id, user_ppid),                     -- One record per user per site
    
    -- Indexes for common queries
    CONSTRAINT fk_site_users_site FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_site_users_site ON site_users(site_id);
CREATE INDEX IF NOT EXISTS idx_site_users_ppid ON site_users(user_ppid);
CREATE INDEX IF NOT EXISTS idx_site_users_status ON site_users(site_id, status);
CREATE INDEX IF NOT EXISTS idx_site_users_role ON site_users(site_id, role);

-- Comments
COMMENT ON TABLE site_users IS 'Users added to sites for IAM - identified by site-specific PPID';
COMMENT ON COLUMN site_users.user_ppid IS 'Pairwise Pseudonymous Identifier - unique per user per site, unlinkable across sites';
COMMENT ON COLUMN site_users.display_name IS 'Optional display name (NOT email) - privacy-preserving';
