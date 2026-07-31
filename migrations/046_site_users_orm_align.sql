-- Migration 046: Canonical site_users column alignment (idempotent)
-- Ensures PPID-oriented directory columns are authoritative for new writes.

UPDATE site_users
SET user_ppid = user_did
WHERE user_ppid IS NULL
  AND user_did IS NOT NULL
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
  AND user_status IS NOT NULL
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
  AND user_role IS NOT NULL
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
  AND site_user_metadata IS NOT NULL
  AND EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'site_users'
        AND column_name = 'site_user_metadata'
  );

COMMENT ON COLUMN site_users.user_ppid IS 'Canonical external subject key for this application (hostname-bound PPID)';
COMMENT ON COLUMN site_users.status IS 'Account state: active, suspended, banned, pending';
COMMENT ON COLUMN site_users.role IS 'Site-defined role label (admin, user, etc.)';
