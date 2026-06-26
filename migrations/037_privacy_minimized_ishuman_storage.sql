-- Migration 037: privacy-minimized isHuman identity storage.
--
-- document_country and document_type are retained only as encrypted policy
-- fields. Provider/session/report references are retained only as keyed HMACs
-- after terminal provider purge.

ALTER TABLE lemma_document_roots
    ALTER COLUMN document_country TYPE VARCHAR(255),
    ALTER COLUMN document_type TYPE VARCHAR(255),
    ADD COLUMN IF NOT EXISTS provider_session_id_hash VARCHAR(80),
    ADD COLUMN IF NOT EXISTS provider_report_id_hash VARCHAR(80);

ALTER TABLE ishuman_verifications
    ADD COLUMN IF NOT EXISTS provider_session_id_hash VARCHAR(80);

CREATE INDEX IF NOT EXISTS idx_lemma_document_roots_provider_session_hash
    ON lemma_document_roots (provider_session_id_hash);

CREATE INDEX IF NOT EXISTS idx_ishuman_verifications_provider_session_hash
    ON ishuman_verifications (provider_session_id_hash);
