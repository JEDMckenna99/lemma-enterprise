-- Migration 036: widen encrypted policy columns; drop plaintext indexes.

ALTER TABLE lemma_document_roots
    ALTER COLUMN issuing_subdivision TYPE VARCHAR(255),
    ALTER COLUMN document_expiration_date TYPE VARCHAR(255);

DROP INDEX IF EXISTS idx_lemma_document_roots_subdivision;
DROP INDEX IF EXISTS idx_lemma_document_roots_expiration;
