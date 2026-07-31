-- Migration 046: Canonical site_users column alignment (idempotent)
-- Ensures PPID-oriented directory columns exist and are backfilled from legacy names.

ALTER TABLE site_users ADD COLUMN IF NOT EXISTS user_ppid VARCHAR(255);
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user';
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP;
ALTER TABLE site_users ADD COLUMN IF NOT EXISTS metadata JSONB;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'user_did'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'user_ppid'
    ) THEN
        UPDATE site_users
        SET user_ppid = user_did
        WHERE user_ppid IS NULL AND user_did IS NOT NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'user_status'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'status'
    ) THEN
        UPDATE site_users
        SET status = user_status
        WHERE status IS NULL AND user_status IS NOT NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'user_role'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'role'
    ) THEN
        UPDATE site_users
        SET role = user_role
        WHERE role IS NULL AND user_role IS NOT NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'site_user_metadata'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'metadata'
    ) THEN
        UPDATE site_users
        SET metadata = site_user_metadata
        WHERE metadata IS NULL AND site_user_metadata IS NOT NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'user_ppid'
    ) THEN
        EXECUTE 'COMMENT ON COLUMN site_users.user_ppid IS ''Canonical external subject key for this application (hostname-bound PPID)''';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'status'
    ) THEN
        EXECUTE 'COMMENT ON COLUMN site_users.status IS ''Account state: active, suspended, banned, pending''';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'site_users' AND column_name = 'role'
    ) THEN
        EXECUTE 'COMMENT ON COLUMN site_users.role IS ''Site-defined role label (admin, user, etc.)''';
    END IF;
END
$$;
