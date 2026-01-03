-- Migration 008: Update to PPID-based user identification
-- =========================================================
-- 
-- The user_did column now stores PPIDs (Pairwise Pseudonymous Identifiers)
-- instead of global DIDs. PPIDs are site-specific:
--   did:lemma:ppid_<HMAC(wallet_secret, site_id)>
--
-- This ensures users cannot be correlated across sites.

-- 1. Clear old user_permissions data that used incorrect identifiers
-- Old format: did:lemma:user:xxx (global, linkable)
-- New format: did:lemma:ppid_xxx (site-specific, unlinkable)

DELETE FROM user_permissions 
WHERE user_did LIKE 'did:lemma:user:%';

-- 2. Update comments to reflect PPID usage
COMMENT ON COLUMN user_permissions.user_did IS 'User PPID (site-specific pairwise identifier) - did:lemma:ppid_xxx';

-- 3. Clear any test/dev data from platform_users that used global DIDs
DELETE FROM platform_users 
WHERE user_did LIKE 'did:lemma:user:%';

DELETE FROM platform_user_sites
WHERE user_did LIKE 'did:lemma:user:%';

-- 4. Update platform_users comments
COMMENT ON COLUMN platform_users.user_did IS 'User PPID for lemma.id platform - derived from passkey/wallet';

-- 5. Log this migration
INSERT INTO system_config (config_key, config_value, description, is_public)
VALUES ('ppid_migration_date', NOW()::TEXT, 'Date of migration to PPID-based user identification', FALSE)
ON CONFLICT (config_key) DO UPDATE SET config_value = NOW()::TEXT, updated_at = NOW();
