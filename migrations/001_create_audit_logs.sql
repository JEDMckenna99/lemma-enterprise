-- Migration 001: Create Audit Logs Table
-- Run this to initialize audit logging for Lemma IAM

-- Create audit_logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    user_email VARCHAR(255),
    user_did VARCHAR(255),
    site_id VARCHAR(100),
    resource VARCHAR(500),
    action VARCHAR(50),
    result VARCHAR(20) NOT NULL,
    ip_address INET,
    user_agent TEXT,
    nonce VARCHAR(128),
    credential_id VARCHAR(128),
    metadata JSONB,
    
    -- Constraint to ensure result is one of allowed values
    CONSTRAINT audit_logs_result_check CHECK (result IN ('success', 'failure', 'warning'))
);

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user_email ON audit_logs (user_email);
CREATE INDEX IF NOT EXISTS idx_audit_site ON audit_logs (site_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_result ON audit_logs (result);
CREATE INDEX IF NOT EXISTS idx_audit_ip ON audit_logs (ip_address);

-- Grant permissions (adjust as needed for your database user)
-- GRANT SELECT, INSERT ON audit_logs TO your_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO your_app_user;

-- Verify table creation
SELECT 'Audit logs table created successfully' AS status;
SELECT COUNT(*) AS initial_count FROM audit_logs;

