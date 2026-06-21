-- Migration 034: person_root_source distinguishes assigned vs document-derived anchors.
--
-- assigned_v1: server-assigned random person_root; document_root rows are
-- renewable attestations linked to the same lemma_person.
-- document_derived_v1: legacy HKDF(document_root) person_root (default).

ALTER TABLE lemma_persons
    ADD COLUMN IF NOT EXISTS person_root_source VARCHAR(32) NOT NULL DEFAULT 'document_derived_v1';

CREATE INDEX IF NOT EXISTS idx_lemma_persons_root_source
    ON lemma_persons (person_root_source);
