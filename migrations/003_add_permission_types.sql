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
    
    UNIQUE (site_id, name),
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_permission_types_site (site_id),
    INDEX idx_permission_types_type (type),
    INDEX idx_permission_types_active (site_id, active)
);

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
    
    FOREIGN KEY (permission_type_id) REFERENCES permission_types(id) ON DELETE CASCADE,
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_permission_instances_email (email),
    INDEX idx_permission_instances_site (site_id, email),
    INDEX idx_permission_instances_active (email, revoked_at) WHERE revoked_at IS NULL,
    INDEX idx_permission_instances_expiring (expires_at) WHERE expires_at IS NOT NULL
);

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
    
    UNIQUE (site_id, name),
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_permission_policies_site (site_id),
    INDEX idx_permission_policies_active (site_id, active)
);

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
    user_agent TEXT,
    
    INDEX idx_audit_log_site (site_id, timestamp DESC),
    INDEX idx_audit_log_event (event_type, timestamp DESC),
    INDEX idx_audit_log_actor (actor, timestamp DESC),
    INDEX idx_audit_log_target (target, timestamp DESC)
);

-- Add comment
COMMENT ON TABLE permission_types IS 'Structured permission type definitions (role, scope, time-bound, etc.)';
COMMENT ON TABLE permission_instances IS 'Tracks which users have which permissions';
COMMENT ON TABLE permission_policies IS 'Complex permission rules and policies';
COMMENT ON TABLE iam_audit_log IS 'Audit trail for all IAM operations';

