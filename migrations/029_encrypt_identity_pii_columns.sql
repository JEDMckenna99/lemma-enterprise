-- Migration 029: widen identity-linkage columns for at-rest encryption
--
-- lemma_persons.person_root_hash is the direct input to canonical PPID
-- derivation: a plaintext copy lets anyone with a DB dump enumerate every
-- site PPID for a person with NO additional secret. We now AES-GCM encrypt it
-- at rest (api.column_crypto) with a key held outside the database, so a
-- DB-only breach yields ciphertext. The same applies to the reference copy of
-- document_root_hash stored on ishuman_verifications (not a lookup key there).
--
-- lemma_document_roots.document_root_hash is intentionally left as plaintext:
-- it is the dedup lookup key (WHERE document_root_hash = ?), and is itself a
-- keyed HMAC of PII rather than raw PII.
--
-- This migration only widens the columns to hold the AES-GCM envelope. Existing
-- rows keep their legacy 64-hex plaintext (read path passes them through) and
-- encrypt lazily on next write; scripts/backfill_encrypt_identity_columns.py
-- upgrades existing rows in place.

ALTER TABLE lemma_persons
    ALTER COLUMN person_root_hash TYPE VARCHAR(255);

ALTER TABLE ishuman_verifications
    ALTER COLUMN document_root_hash TYPE VARCHAR(255);
