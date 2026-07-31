-- Migration 047: Reserved identity subject alias table (opt-in continuity)
-- No public write API in Phase 1; schema only for future signed link protocol.

CREATE TABLE IF NOT EXISTS identity_subject_aliases (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(120),
    from_site_id VARCHAR(50) NOT NULL,
    from_ppid VARCHAR(255) NOT NULL,
    to_site_id VARCHAR(50) NOT NULL,
    to_ppid VARCHAR(255) NOT NULL,
    alias_type VARCHAR(64) NOT NULL DEFAULT 'explicit_link',
    status VARCHAR(32) NOT NULL DEFAULT 'reserved',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    evidence_jti VARCHAR(128)
);

CREATE INDEX IF NOT EXISTS idx_identity_subject_aliases_from
    ON identity_subject_aliases(from_site_id, from_ppid);

CREATE INDEX IF NOT EXISTS idx_identity_subject_aliases_to
    ON identity_subject_aliases(to_site_id, to_ppid);

CREATE INDEX IF NOT EXISTS idx_identity_subject_aliases_tenant
    ON identity_subject_aliases(tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_subject_aliases_active_from_to
    ON identity_subject_aliases(from_site_id, from_ppid, to_site_id)
    WHERE status IN ('reserved', 'active');

COMMENT ON TABLE identity_subject_aliases IS
    'Explicit cross-application subject continuity; default privacy remains hostname-private PPID';
