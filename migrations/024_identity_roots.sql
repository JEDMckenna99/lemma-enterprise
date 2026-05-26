-- Migration 024: Lemma person-root identity (Stripe document-root anchors)

CREATE TABLE IF NOT EXISTS lemma_persons (
    id SERIAL PRIMARY KEY,
    person_id VARCHAR(64) NOT NULL UNIQUE,
    person_root_hash VARCHAR(64) NOT NULL,
    root_version VARCHAR(16) NOT NULL DEFAULT 'v1',
    primary_wallet_id VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lemma_persons_root_hash ON lemma_persons (person_root_hash);
CREATE INDEX IF NOT EXISTS idx_lemma_persons_primary_wallet ON lemma_persons (primary_wallet_id);

CREATE TABLE IF NOT EXISTS lemma_document_roots (
    id SERIAL PRIMARY KEY,
    document_root_hash VARCHAR(64) NOT NULL UNIQUE,
    lemma_person_id VARCHAR(64) NOT NULL,
    root_version VARCHAR(16) NOT NULL DEFAULT 'v1',
    provider VARCHAR(32) NOT NULL DEFAULT 'stripe_identity',
    stripe_verification_session_id VARCHAR(255),
    stripe_verification_report_id VARCHAR(255),
    document_country VARCHAR(8),
    document_type VARCHAR(32),
    confidence_level VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_lemma_document_roots_person ON lemma_document_roots (lemma_person_id);
CREATE INDEX IF NOT EXISTS idx_lemma_document_roots_stripe_session ON lemma_document_roots (stripe_verification_session_id);

CREATE TABLE IF NOT EXISTS lemma_wallet_bindings (
    id SERIAL PRIMARY KEY,
    wallet_id VARCHAR(255) NOT NULL UNIQUE,
    lemma_person_id VARCHAR(64) NOT NULL,
    binding_status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lemma_wallet_bindings_person ON lemma_wallet_bindings (lemma_person_id);

ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS lemma_person_id VARCHAR(64);
ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS document_root_hash VARCHAR(64);
ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS root_version VARCHAR(16) DEFAULT 'v1';
ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_ishuman_verifications_lemma_person ON ishuman_verifications (lemma_person_id);
CREATE INDEX IF NOT EXISTS idx_ishuman_verifications_document_root ON ishuman_verifications (document_root_hash);
