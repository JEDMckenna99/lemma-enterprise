-- Agent Credentials Table
-- Stores time-limited credentials issued to AI agents via passkey authorization
-- 
-- SECURITY MODEL:
-- 1. Human authenticates with passkey (biometric/hardware proof)
-- 2. Human issues credential with scope and TTL
-- 3. Agent uses credential in X-Agent-Token header
-- 4. Server validates: not expired, not revoked, scope matches
-- 5. Human can revoke at any time
--
-- This is NOT a backdoor. The security depends on:
-- - Passkey auth (hardware-bound, I can't fake it)
-- - Server-side validation (I can't modify runtime)
-- - Your ability to revoke (you maintain control)

CREATE TABLE IF NOT EXISTS agent_credentials (
    id SERIAL PRIMARY KEY,
    
    -- Unique token identifier (what the agent sends in headers)
    token_id VARCHAR(64) UNIQUE NOT NULL,
    
    -- Hashed token (we store hash, agent has plaintext)
    -- This means even DB access doesn't reveal valid tokens
    token_hash VARCHAR(128) NOT NULL,
    
    -- Who authorized this credential (passkey user)
    authorized_by_ppid VARCHAR(255) NOT NULL,
    authorized_by_email VARCHAR(255),
    
    -- What passkey was used to authorize (for audit)
    passkey_credential_id VARCHAR(255),
    
    -- Scope: what can this agent do?
    -- JSON array of allowed actions: ["read", "write", "admin"]
    scope JSONB NOT NULL DEFAULT '["read"]',
    
    -- Which sites can this agent access?
    -- NULL = all sites the authorizing user has access to
    -- JSON array of site_ids for restricted access
    allowed_sites JSONB,
    
    -- Time limits
    issued_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Revocation
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(255),
    
    -- Metadata
    agent_name VARCHAR(255) DEFAULT 'AI Agent',
    agent_type VARCHAR(50) DEFAULT 'coding_assistant',
    description TEXT,
    
    -- Usage tracking
    last_used_at TIMESTAMP WITH TIME ZONE,
    use_count INTEGER DEFAULT 0,
    
    -- Indexes for fast lookup
    CONSTRAINT valid_expiry CHECK (expires_at > issued_at)
);

-- Index for token lookup (most common operation)
CREATE INDEX IF NOT EXISTS idx_agent_credentials_token_hash 
    ON agent_credentials(token_hash) 
    WHERE revoked = FALSE;

-- Index for listing user's credentials
CREATE INDEX IF NOT EXISTS idx_agent_credentials_authorized_by 
    ON agent_credentials(authorized_by_ppid);

-- Index for cleanup of expired credentials
CREATE INDEX IF NOT EXISTS idx_agent_credentials_expires 
    ON agent_credentials(expires_at) 
    WHERE revoked = FALSE;

-- Audit log for agent actions
CREATE TABLE IF NOT EXISTS agent_audit_log (
    id SERIAL PRIMARY KEY,
    
    -- Which credential was used
    credential_id INTEGER REFERENCES agent_credentials(id),
    token_id VARCHAR(64) NOT NULL,
    
    -- What action was taken
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    
    -- Request details
    method VARCHAR(10),
    path VARCHAR(500),
    
    -- Result
    status_code INTEGER,
    success BOOLEAN,
    
    -- Timestamp
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Additional context
    metadata JSONB
);

-- Index for querying audit log by credential
CREATE INDEX IF NOT EXISTS idx_agent_audit_log_credential 
    ON agent_audit_log(credential_id);

-- Index for querying audit log by time
CREATE INDEX IF NOT EXISTS idx_agent_audit_log_timestamp 
    ON agent_audit_log(timestamp DESC);

COMMENT ON TABLE agent_credentials IS 'AI agent credentials issued via passkey authorization. Humans authorize, agents use, humans can revoke.';
COMMENT ON TABLE agent_audit_log IS 'Audit trail of all actions taken by AI agents. Every agent action is logged.';
