-- Migration 009: Create site_users table for IAM user management
-- ===============================================================
--
-- This migration is intentionally compatibility-safe. Some environments
-- already have a legacy site_users shape (user_did/user_status/user_role).
-- We preserve legacy columns and add PPID-oriented columns when missing.

CREATE TABLE IF NOT EXISTS site_users (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,
    user_ppid VARCHAR(255),
    display_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    status VARCHAR(20) DEFAULT 'active',
    added_by VARCHAR(255) NOT NULL DEFAULT 'api',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP,
    metadata JSONB,
    CONSTRAINT fk_site_users_site FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE
);

ALTER TABLE site_users ADD COLUMN IF NOT EXISTS user_ppid VARCHAR(255);
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user';
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP;
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Legacy compatibility backfill
UPDATE site_users
SET user_ppid = user_did
WHERE user_ppid IS NULL
  AND EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'site_users'
        AND column_name = 'user_did'
  );

UPDATE site_users
SET status = user_status
WHERE status IS NULL
  AND EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'site_users'
        AND column_name = 'user_status'
  );

UPDATE site_users
SET role = user_role
WHERE role IS NULL
  AND EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'site_users'
        AND column_name = 'user_role'
  );

UPDATE site_users
SET metadata = site_user_metadata
WHERE metadata IS NULL
  AND EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'site_users'
        AND column_name = 'site_user_metadata'
  );

ALTER TABLE site_users
ALTER COLUMN user_ppid SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'site_users_site_ppid_unique'
    ) THEN
        ALTER TABLE site_users
        ADD CONSTRAINT site_users_site_ppid_unique UNIQUE (site_id, user_ppid);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_site_users_site ON site_users(site_id);
CREATE INDEX IF NOT EXISTS idx_site_users_ppid ON site_users(user_ppid);
CREATE INDEX IF NOT EXISTS idx_site_users_status ON site_users(site_id, status);
CREATE INDEX IF NOT EXISTS idx_site_users_role ON site_users(site_id, role);

COMMENT ON TABLE site_users IS 'Users added to sites for IAM - identified by site-specific PPID';
COMMENT ON COLUMN site_users.user_ppid IS 'Pairwise Pseudonymous Identifier - unique per user per site, unlinkable across sites';
COMMENT ON COLUMN site_users.display_name IS 'Optional display name (NOT email) - privacy-preserving';
