-- Migration 020: Add PPID-level revocation for multi-device support
-- 
-- Problem: When user has credentials on multiple devices (same PPID, different credential IDs),
-- revoking one credential doesn't revoke the user on other devices.
--
-- Solution: Add PPID column to revocation_list. When revoking a USER (not just a credential),
-- add their PPID. Verification checks both credential_id AND ppid in Bloom filter.

-- Add ppid column for user-level revocation
ALTER TABLE revocation_list ADD COLUMN IF NOT EXISTS ppid VARCHAR(255);

-- Add revocation_type to distinguish credential vs user revocation
ALTER TABLE revocation_list ADD COLUMN IF NOT EXISTS revocation_type VARCHAR(50) DEFAULT 'credential';
-- 'credential' = revoke one specific credential (one device)
-- 'user' = revoke all credentials for this PPID (all devices)

-- Create index for PPID lookups
CREATE INDEX IF NOT EXISTS idx_revocation_ppid ON revocation_list(ppid);
CREATE INDEX IF NOT EXISTS idx_revocation_type ON revocation_list(revocation_type);

-- Comment explaining the change
COMMENT ON COLUMN revocation_list.ppid IS 'Site-specific user identifier (PPID). When revocation_type=user, ALL credentials for this PPID are revoked.';
COMMENT ON COLUMN revocation_list.revocation_type IS 'credential=revoke one credential, user=revoke all credentials for PPID';
