-- Migration 022: Workspace-first Agent Ops schema
-- Adds canonical control-plane tables without removing legacy IAM storage.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'customers' AND column_name = 'workspace_id'
    ) THEN
        ALTER TABLE customers ADD COLUMN workspace_id VARCHAR(120);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sites' AND column_name = 'workspace_id'
    ) THEN
        ALTER TABLE sites ADD COLUMN workspace_id VARCHAR(120);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id VARCHAR(120) PRIMARY KEY,
    slug VARCHAR(120) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    owner_ppid VARCHAR(255),
    owner_email VARCHAR(255),
    owner_wallet_id VARCHAR(255),
    billing_customer_id VARCHAR(120),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspace_users (
    id SERIAL PRIMARY KEY,
    user_did VARCHAR(255) NOT NULL UNIQUE,
    primary_email VARCHAR(255),
    display_name VARCHAR(255),
    wallet_id VARCHAR(255),
    verification_level VARCHAR(64) NOT NULL DEFAULT 'base',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspace_memberships (
    id SERIAL PRIMARY KEY,
    workspace_id VARCHAR(120) NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    workspace_user_id INTEGER NOT NULL REFERENCES workspace_users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL DEFAULT 'viewer',
    invite_status VARCHAR(32) NOT NULL DEFAULT 'active',
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    invited_by VARCHAR(255),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (workspace_id, workspace_user_id)
);

CREATE TABLE IF NOT EXISTS policy_profiles (
    policy_profile_id VARCHAR(120) PRIMARY KEY,
    workspace_id VARCHAR(120) REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    policy_version VARCHAR(64) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    policy_document JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runtimes (
    id SERIAL PRIMARY KEY,
    runtime_id VARCHAR(120) NOT NULL UNIQUE,
    workspace_id VARCHAR(120) NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    site_id VARCHAR(120),
    owner_ppid VARCHAR(255),
    owner_wallet_id VARCHAR(255),
    agent_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    policy_profile_id VARCHAR(120) NOT NULL DEFAULT 'lemma_firewall_default_v1',
    policy_profile_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    risk_defaults_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    trust_state VARCHAR(64) NOT NULL DEFAULT 'clean_internal',
    taint_epoch INTEGER NOT NULL DEFAULT 0,
    kill_switch_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_connected_at TIMESTAMP WITH TIME ZONE,
    killed_at TIMESTAMP WITH TIME ZONE,
    kill_reason TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS delegations (
    id SERIAL PRIMARY KEY,
    delegation_id VARCHAR(120) NOT NULL UNIQUE,
    workspace_id VARCHAR(120) NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    runtime_id VARCHAR(120),
    token_id VARCHAR(120),
    delegator_ppid VARCHAR(255),
    delegated_by_user_ref VARCHAR(255),
    acting_for_ppid VARCHAR(255),
    acting_for_user_ref VARCHAR(255),
    requested_by_ppid VARCHAR(255),
    requested_by_user_ref VARCHAR(255),
    subject_type VARCHAR(64) NOT NULL DEFAULT 'agent_credential',
    subject_ref VARCHAR(255),
    audience VARCHAR(255),
    scope_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_sites_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    resource_bounds_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    task_description TEXT,
    task_hash VARCHAR(64),
    allowed_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    max_operations INTEGER,
    expires_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    reason TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decision_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    workspace_id VARCHAR(120) REFERENCES workspaces(workspace_id) ON DELETE SET NULL,
    runtime_id VARCHAR(120),
    agent_id VARCHAR(255),
    delegator_ppid VARCHAR(255),
    credential_ref VARCHAR(255),
    token_id VARCHAR(120),
    route VARCHAR(255),
    action VARCHAR(255),
    resource VARCHAR(255),
    method VARCHAR(16),
    path VARCHAR(500),
    decision VARCHAR(16) NOT NULL,
    reason_code VARCHAR(120) NOT NULL,
    policy_profile VARCHAR(120),
    policy_version VARCHAR(64),
    request_correlation_id VARCHAR(255),
    trust_state VARCHAR(64),
    taint_epoch INTEGER,
    status_code INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS agent_ops_revocations (
    id SERIAL PRIMARY KEY,
    revocation_id VARCHAR(120) NOT NULL UNIQUE,
    workspace_id VARCHAR(120) REFERENCES workspaces(workspace_id) ON DELETE SET NULL,
    subject_type VARCHAR(64) NOT NULL,
    subject_ref VARCHAR(255) NOT NULL,
    runtime_id VARCHAR(120),
    delegator_ppid VARCHAR(255),
    reason_code VARCHAR(120),
    revoked_by VARCHAR(255),
    revoked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    effective_epoch INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Phase 1+ foundation: root typing and org/environment partition keys.
ALTER TABLE policy_profiles ADD COLUMN IF NOT EXISTS org_id VARCHAR(120) NOT NULL DEFAULT 'org_default';
ALTER TABLE policy_profiles ADD COLUMN IF NOT EXISTS environment VARCHAR(32) NOT NULL DEFAULT 'prod';
ALTER TABLE policy_profiles ADD COLUMN IF NOT EXISTS root_type VARCHAR(32) NOT NULL DEFAULT 'passkey_root';
ALTER TABLE policy_profiles ADD COLUMN IF NOT EXISTS published_version VARCHAR(64);
ALTER TABLE policy_profiles ADD COLUMN IF NOT EXISTS previous_published_version VARCHAR(64);
ALTER TABLE policy_profiles ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active';

ALTER TABLE runtimes ADD COLUMN IF NOT EXISTS org_id VARCHAR(120) NOT NULL DEFAULT 'org_default';
ALTER TABLE runtimes ADD COLUMN IF NOT EXISTS environment VARCHAR(32) NOT NULL DEFAULT 'prod';
ALTER TABLE runtimes ADD COLUMN IF NOT EXISTS root_type VARCHAR(32) NOT NULL DEFAULT 'passkey_root';
ALTER TABLE runtimes ADD COLUMN IF NOT EXISTS emergency_stopped BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE runtimes ADD COLUMN IF NOT EXISTS quota_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE delegations ADD COLUMN IF NOT EXISTS org_id VARCHAR(120) NOT NULL DEFAULT 'org_default';
ALTER TABLE delegations ADD COLUMN IF NOT EXISTS environment VARCHAR(32) NOT NULL DEFAULT 'prod';
ALTER TABLE delegations ADD COLUMN IF NOT EXISTS root_type VARCHAR(32) NOT NULL DEFAULT 'passkey_root';

ALTER TABLE decision_logs ADD COLUMN IF NOT EXISTS org_id VARCHAR(120) NOT NULL DEFAULT 'org_default';
ALTER TABLE decision_logs ADD COLUMN IF NOT EXISTS environment VARCHAR(32) NOT NULL DEFAULT 'prod';
ALTER TABLE decision_logs ADD COLUMN IF NOT EXISTS root_type VARCHAR(32) NOT NULL DEFAULT 'passkey_root';

ALTER TABLE agent_ops_revocations ADD COLUMN IF NOT EXISTS org_id VARCHAR(120) NOT NULL DEFAULT 'org_default';
ALTER TABLE agent_ops_revocations ADD COLUMN IF NOT EXISTS environment VARCHAR(32) NOT NULL DEFAULT 'prod';
ALTER TABLE agent_ops_revocations ADD COLUMN IF NOT EXISTS root_type VARCHAR(32) NOT NULL DEFAULT 'passkey_root';

CREATE TABLE IF NOT EXISTS policy_profile_revisions (
    id SERIAL PRIMARY KEY,
    policy_profile_id VARCHAR(120) NOT NULL REFERENCES policy_profiles(policy_profile_id) ON DELETE CASCADE,
    org_id VARCHAR(120) NOT NULL DEFAULT 'org_default',
    environment VARCHAR(32) NOT NULL DEFAULT 'prod',
    policy_version VARCHAR(64) NOT NULL,
    policy_document JSONB NOT NULL DEFAULT '{}'::jsonb,
    change_summary TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (policy_profile_id, org_id, environment, policy_version)
);

CREATE TABLE IF NOT EXISTS runtime_org_controls (
    id SERIAL PRIMARY KEY,
    org_id VARCHAR(120) NOT NULL,
    environment VARCHAR(32) NOT NULL DEFAULT 'prod',
    emergency_stop_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    quota_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, environment)
);

CREATE TABLE IF NOT EXISTS decision_webhook_sinks (
    sink_id VARCHAR(120) PRIMARY KEY,
    org_id VARCHAR(120) NOT NULL,
    environment VARCHAR(32) NOT NULL DEFAULT 'prod',
    destination_url TEXT NOT NULL,
    shared_secret VARCHAR(255),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_ppid ON workspaces(owner_ppid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_memberships_unique
    ON workspace_memberships(workspace_id, workspace_user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_users_wallet_id ON workspace_users(wallet_id);
CREATE INDEX IF NOT EXISTS idx_workspace_memberships_workspace ON workspace_memberships(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user ON workspace_memberships(workspace_user_id);
CREATE INDEX IF NOT EXISTS idx_sites_workspace_id ON sites(workspace_id);
CREATE INDEX IF NOT EXISTS idx_customers_workspace_id ON customers(workspace_id);
CREATE INDEX IF NOT EXISTS idx_runtimes_workspace_id ON runtimes(workspace_id);
CREATE INDEX IF NOT EXISTS idx_runtimes_owner_ppid ON runtimes(owner_ppid);
CREATE INDEX IF NOT EXISTS idx_runtimes_owner_wallet_id ON runtimes(owner_wallet_id);
CREATE INDEX IF NOT EXISTS idx_runtimes_site_id ON runtimes(site_id);
CREATE INDEX IF NOT EXISTS idx_delegations_workspace_id ON delegations(workspace_id);
CREATE INDEX IF NOT EXISTS idx_delegations_token_id ON delegations(token_id);
CREATE INDEX IF NOT EXISTS idx_delegations_delegator_ppid ON delegations(delegator_ppid);
CREATE INDEX IF NOT EXISTS idx_decision_logs_workspace_id ON decision_logs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_decision_logs_runtime_id ON decision_logs(runtime_id);
CREATE INDEX IF NOT EXISTS idx_decision_logs_delegator_ppid ON decision_logs(delegator_ppid);
CREATE INDEX IF NOT EXISTS idx_decision_logs_timestamp ON decision_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_policy_profiles_org_env ON policy_profiles(org_id, environment);
CREATE INDEX IF NOT EXISTS idx_runtimes_org_env ON runtimes(org_id, environment);
CREATE INDEX IF NOT EXISTS idx_delegations_org_env ON delegations(org_id, environment);
CREATE INDEX IF NOT EXISTS idx_decision_logs_org_env ON decision_logs(org_id, environment);
CREATE INDEX IF NOT EXISTS idx_agent_ops_revocations_org_env ON agent_ops_revocations(org_id, environment);
CREATE INDEX IF NOT EXISTS idx_policy_profile_revisions_lookup
    ON policy_profile_revisions(policy_profile_id, org_id, environment, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_ops_revocations_subject_ref ON agent_ops_revocations(subject_ref);
CREATE INDEX IF NOT EXISTS idx_agent_ops_revocations_runtime_id ON agent_ops_revocations(runtime_id);
CREATE INDEX IF NOT EXISTS idx_agent_ops_revocations_workspace_id ON agent_ops_revocations(workspace_id);

INSERT INTO policy_profiles (
    policy_profile_id,
    workspace_id,
    policy_version,
    display_name,
    description,
    policy_document,
    is_active
)
VALUES (
    'lemma_firewall_default_v1',
    NULL,
    'v1',
    'Lemma Firewall Default',
    'Default proof-first Agent Ops runtime policy profile.',
    '{}'::jsonb,
    TRUE
)
ON CONFLICT (policy_profile_id) DO NOTHING;
