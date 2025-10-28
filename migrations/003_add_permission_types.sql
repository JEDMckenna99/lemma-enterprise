-- Migration 003: Add Permission Types System
-- Adds structured permission type support (role, scope, time-bound, attribute, hierarchical)

-- Permission Types table
CREATE TABLE IF NOT EXISTS permission_types (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,                -- e.g., 'premium_tier_1', 'admin', 'moderator'
    type VARCHAR(50) NOT NULL,                  -- 'role', 'scope', 'time-bound', 'attribute', 'hierarchical'
    description TEXT,
    config JSONB DEFAULT '{}',                  -- Type-specific configuration
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    
    CONSTRAINT unique_site_permission_type UNIQUE (site_id, name),
    CONSTRAINT fk_permission_types_site FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_permission_types_site ON permission_types(site_id);
CREATE INDEX IF NOT EXISTS idx_permission_types_type ON permission_types(type);
CREATE INDEX IF NOT EXISTS idx_permission_types_active ON permission_types(site_id, active);

-- Permission Instances table (tracks who has which permission)
CREATE TABLE IF NOT EXISTS permission_instances (
    id SERIAL PRIMARY KEY,
    permission_type_id INTEGER NOT NULL,
    site_id VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL,               -- User email
    credential_did VARCHAR(255),                -- User's DID (if known)
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by VARCHAR(255),
    expires_at TIMESTAMP,                       -- NULL = never expires
    revoked_at TIMESTAMP,
    revoked_by VARCHAR(255),
    revocation_reason TEXT,
    metadata JSONB DEFAULT '{}',                -- Custom attributes
    
    CONSTRAINT fk_permission_instances_type FOREIGN KEY (permission_type_id) REFERENCES permission_types(id) ON DELETE CASCADE,
    CONSTRAINT fk_permission_instances_site FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_permission_instances_email ON permission_instances(email);
CREATE INDEX IF NOT EXISTS idx_permission_instances_site ON permission_instances(site_id, email);
CREATE INDEX IF NOT EXISTS idx_permission_instances_active ON permission_instances(email, revoked_at) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_permission_instances_expiring ON permission_instances(expires_at) WHERE expires_at IS NOT NULL;

-- Permission Policies table (complex permission rules)
CREATE TABLE IF NOT EXISTS permission_policies (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rules JSONB NOT NULL,                       -- Policy definition (JSON)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_site_policy UNIQUE (site_id, name),
    CONSTRAINT fk_permission_policies_site FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_permission_policies_site ON permission_policies(site_id);
CREATE INDEX IF NOT EXISTS idx_permission_policies_active ON permission_policies(site_id, active);

-- IAM Audit Log table
CREATE TABLE IF NOT EXISTS iam_audit_log (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(100) NOT NULL,           -- 'permission_granted', 'permission_revoked', etc.
    actor VARCHAR(255),                          -- Who performed the action
    target VARCHAR(255),                         -- Who was affected
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_log_site ON iam_audit_log(site_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_event ON iam_audit_log(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON iam_audit_log(actor, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_target ON iam_audit_log(target, timestamp);

-- Add comment
COMMENT ON TABLE permission_types IS 'Structured permission type definitions (role, scope, time-bound, etc.)';
COMMENT ON TABLE permission_instances IS 'Tracks which users have which permissions';
COMMENT ON TABLE permission_policies IS 'Complex permission rules and policies';
COMMENT ON TABLE iam_audit_log IS 'Audit trail for all IAM operations';

