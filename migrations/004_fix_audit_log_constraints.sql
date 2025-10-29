-- Migration 004: Fix IAM Audit Log Constraints for Multi-Tenant Security
-- Adds missing NOT NULL, foreign key, and index to iam_audit_log

-- Step 1: Update existing NULL site_id values to 'unknown' (shouldn't happen, but just in case)
UPDATE iam_audit_log 
SET site_id = 'unknown' 
WHERE site_id IS NULL;

-- Step 2: Make site_id NOT NULL
ALTER TABLE iam_audit_log 
ALTER COLUMN site_id SET NOT NULL;

-- Step 3: Add foreign key constraint (with CASCADE delete)
-- Note: This will fail if there are orphaned records (audit logs with invalid site_id)
-- If it fails, you need to clean up orphaned records first
ALTER TABLE iam_audit_log 
ADD CONSTRAINT fk_audit_log_site 
FOREIGN KEY (site_id) 
REFERENCES sites(site_id) 
ON DELETE CASCADE;

-- Step 4: Add index for efficient site-specific queries
-- (idx_audit_log_site already exists with composite (site_id, timestamp), but add single column index too)
CREATE INDEX IF NOT EXISTS idx_audit_log_site_only ON iam_audit_log(site_id);

-- Step 5: Add Row-Level Security (RLS) for extra protection
-- This ensures even with SQL injection, customers can only see their own data
ALTER TABLE permission_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE permission_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE permission_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam_audit_log ENABLE ROW LEVEL SECURITY;

-- Create RLS policies (requires PostgreSQL 9.5+)
-- Policy: Users can only see records for their site_id
CREATE POLICY permission_types_isolation ON permission_types
    FOR ALL
    TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

CREATE POLICY permission_instances_isolation ON permission_instances
    FOR ALL
    TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

CREATE POLICY permission_policies_isolation ON permission_policies
    FOR ALL
    TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

CREATE POLICY iam_audit_log_isolation ON iam_audit_log
    FOR ALL
    TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

-- Comments
COMMENT ON CONSTRAINT fk_audit_log_site ON iam_audit_log IS 
    'Ensures audit logs are deleted when site is deleted (CASCADE)';

COMMENT ON POLICY permission_types_isolation ON permission_types IS 
    'Row-level security: Customers can only see their own permission types';

COMMENT ON POLICY permission_instances_isolation ON permission_instances IS 
    'Row-level security: Customers can only see their own permission instances';

COMMENT ON POLICY permission_policies_isolation ON permission_policies IS 
    'Row-level security: Customers can only see their own permission policies';

COMMENT ON POLICY iam_audit_log_isolation ON iam_audit_log IS 
    'Row-level security: Customers can only see their own audit logs';

-- Migration complete

