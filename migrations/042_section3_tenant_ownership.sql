-- Migration 042: Section 3 tenant ownership (domain transfers + site-table RLS)

CREATE TABLE IF NOT EXISTS domain_verification_challenges (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    token VARCHAR(64) NOT NULL,
    customer_id VARCHAR(255) NOT NULL,
    actor_ppid VARCHAR(255) NOT NULL,
    purpose VARCHAR(64) NOT NULL DEFAULT 'site_registration',
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_domain_verification_domain ON domain_verification_challenges(domain);
CREATE INDEX IF NOT EXISTS idx_domain_verification_customer ON domain_verification_challenges(customer_id);

CREATE TABLE IF NOT EXISTS domain_transfers (
    id SERIAL PRIMARY KEY,
    transfer_id VARCHAR(64) NOT NULL UNIQUE,
    site_id VARCHAR(255) NOT NULL,
    site_domain VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    from_customer_id VARCHAR(255) NOT NULL,
    to_customer_id VARCHAR(255),
    initiated_by_ppid VARCHAR(255) NOT NULL,
    accepted_by_ppid VARCHAR(255),
    verification_method VARCHAR(32) NOT NULL DEFAULT 'well-known',
    verification_token VARCHAR(64) NOT NULL,
    audit_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    cancelled_at TIMESTAMP WITHOUT TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_domain_transfers_site ON domain_transfers(site_id);
CREATE INDEX IF NOT EXISTS idx_domain_transfers_status ON domain_transfers(status);
CREATE INDEX IF NOT EXISTS idx_domain_transfers_from_customer ON domain_transfers(from_customer_id);

-- Row-level security for high-value site tables
ALTER TABLE IF EXISTS sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS site_admins ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS site_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS site_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS site_doubts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS sites_isolation ON sites;
CREATE POLICY sites_isolation ON sites
    FOR ALL TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

DROP POLICY IF EXISTS site_admins_isolation ON site_admins;
CREATE POLICY site_admins_isolation ON site_admins
    FOR ALL TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

DROP POLICY IF EXISTS site_users_isolation ON site_users;
CREATE POLICY site_users_isolation ON site_users
    FOR ALL TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

DROP POLICY IF EXISTS site_blocks_isolation ON site_blocks;
CREATE POLICY site_blocks_isolation ON site_blocks
    FOR ALL TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

DROP POLICY IF EXISTS site_doubts_isolation ON site_doubts;
CREATE POLICY site_doubts_isolation ON site_doubts
    FOR ALL TO PUBLIC
    USING (site_id = current_setting('app.current_site_id', TRUE));

COMMENT ON POLICY sites_isolation ON sites IS
    'Row-level security: tenant-scoped site rows via app.current_site_id';
