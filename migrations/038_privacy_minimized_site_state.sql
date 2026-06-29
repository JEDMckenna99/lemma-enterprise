-- Migration 038: privacy-minimized site usage, billing, and doubt state.

ALTER TABLE lemma_persons ALTER COLUMN person_root_hash TYPE TEXT;
DROP INDEX IF EXISTS ix_lemma_persons_person_root_hash;

CREATE TABLE IF NOT EXISTS ishuman_site_billing_subjects (
    id SERIAL PRIMARY KEY,
    site_scope VARCHAR(255) NOT NULL,
    subject_token VARCHAR(80) NOT NULL,
    first_issuance_month VARCHAR(7) NOT NULL,
    first_issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ishuman_site_billing_subject UNIQUE (site_scope, subject_token)
);
CREATE INDEX IF NOT EXISTS idx_ishuman_site_billing_subjects_scope
    ON ishuman_site_billing_subjects (site_scope);

CREATE TABLE IF NOT EXISTS ishuman_site_monthly_usage (
    id SERIAL PRIMARY KEY,
    site_scope VARCHAR(255) NOT NULL,
    month VARCHAR(7) NOT NULL,
    subject_token VARCHAR(80) NOT NULL,
    first_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ishuman_site_monthly_subject UNIQUE (site_scope, month, subject_token)
);
CREATE INDEX IF NOT EXISTS idx_ishuman_site_monthly_scope_month
    ON ishuman_site_monthly_usage (site_scope, month);

CREATE TABLE IF NOT EXISTS ishuman_site_usage_aggregates (
    id SERIAL PRIMARY KEY,
    site_scope VARCHAR(255) NOT NULL,
    month VARCHAR(7) NOT NULL,
    active_subjects INTEGER NOT NULL DEFAULT 0,
    initial_issuances INTEGER NOT NULL DEFAULT 0,
    mau_renewals INTEGER NOT NULL DEFAULT 0,
    doubt_reentries INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ishuman_site_usage_aggregate UNIQUE (site_scope, month)
);
ALTER TABLE ishuman_site_usage_aggregates
    ADD COLUMN IF NOT EXISTS active_subjects INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS ishuman_billing_outbox (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL UNIQUE,
    stripe_customer_id VARCHAR(255),
    site_scope VARCHAR(255) NOT NULL,
    month VARCHAR(7) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    unit_count INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reported_at TIMESTAMP,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ishuman_billing_outbox_status
    ON ishuman_billing_outbox (status, created_at);

CREATE TABLE IF NOT EXISTS site_doubts (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR NOT NULL,
    ppid VARCHAR NOT NULL,
    reason VARCHAR,
    requested_by VARCHAR,
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    cleared_at TIMESTAMP,
    cleared_by VARCHAR,
    CONSTRAINT uq_site_doubts_site_ppid UNIQUE (site_id, ppid)
);
CREATE INDEX IF NOT EXISTS idx_site_doubts_site_active
    ON site_doubts (site_id, is_active);
