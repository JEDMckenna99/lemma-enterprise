-- Migration 035: persist document attestation attributes for policy gates.
--
-- Stores expiration, issuing subdivision, encrypted DOB, and document-root schema
-- on each lemma_document_roots row (renewable attestations).

ALTER TABLE lemma_document_roots
    ADD COLUMN IF NOT EXISTS issuing_subdivision VARCHAR(16),
    ADD COLUMN IF NOT EXISTS document_expiration_date VARCHAR(10),
    ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR(255),
    ADD COLUMN IF NOT EXISTS document_root_schema VARCHAR(64) NOT NULL DEFAULT 'lemma.identity.document-root.v1';

CREATE INDEX IF NOT EXISTS idx_lemma_document_roots_subdivision
    ON lemma_document_roots (issuing_subdivision);

CREATE INDEX IF NOT EXISTS idx_lemma_document_roots_expiration
    ON lemma_document_roots (document_expiration_date);
