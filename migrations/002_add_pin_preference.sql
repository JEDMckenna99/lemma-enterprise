-- Migration 002: Add PIN Preference to Sites
-- Sites can RECOMMEND PIN but cannot enforce it (wallet-level decision)

-- Add PIN recommendation flag to sites table
ALTER TABLE sites 
ADD COLUMN IF NOT EXISTS recommend_pin BOOLEAN DEFAULT TRUE;

-- Add comment
COMMENT ON COLUMN sites.recommend_pin IS 'Whether to show PIN setup prompt for users (recommendation only, not enforced)';

-- Verify
SELECT 'PIN recommendation column added successfully' AS status;

