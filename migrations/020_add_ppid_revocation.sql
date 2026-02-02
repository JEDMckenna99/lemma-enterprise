-- Migration 020: Add PPID and wallet-level revocation for multi-device support
-- 
-- Problem: When user has credentials on multiple devices (same PPID, different credential IDs),
-- revoking one credential doesn't revoke the user on other devices.
--
-- Solution: Add PPID and wallet_id columns to revocation_list:
-- - PPID revocation: All devices for one user on ONE site
-- - Wallet revocation: All devices for one user on ALL sites (account compromise)

-- Add ppid column for user-level revocation (per-site)
ALTER TABLE revocation_list ADD COLUMN IF NOT EXISTS ppid VARCHAR(255);

-- Add wallet_id column for global revocation (all sites)
ALTER TABLE revocation_list ADD COLUMN IF NOT EXISTS wallet_id VARCHAR(255);

-- Add revocation_type to distinguish credential vs user vs wallet revocation
ALTER TABLE revocation_list ADD COLUMN IF NOT EXISTS revocation_type VARCHAR(50) DEFAULT 'credential';
-- 'credential' = revoke one specific credential (one device)
-- 'user' = revoke all credentials for this PPID (all devices, one site)
-- 'wallet' = revoke all credentials for this wallet (all devices, ALL sites)

-- Create indexes for lookups
CREATE INDEX IF NOT EXISTS idx_revocation_ppid ON revocation_list(ppid);
CREATE INDEX IF NOT EXISTS idx_revocation_wallet_id ON revocation_list(wallet_id);
CREATE INDEX IF NOT EXISTS idx_revocation_type ON revocation_list(revocation_type);

-- Comments explaining the columns
COMMENT ON COLUMN revocation_list.ppid IS 'Site-specific user identifier (PPID). When revocation_type=user, ALL credentials for this PPID are revoked on that site.';
COMMENT ON COLUMN revocation_list.wallet_id IS 'Global wallet identifier. When revocation_type=wallet, ALL credentials for this wallet are revoked across ALL sites.';
COMMENT ON COLUMN revocation_list.revocation_type IS 'credential=one credential, user=all credentials per site, wallet=all credentials globally';
