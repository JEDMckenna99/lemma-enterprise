-- Migration 027: isHuman v2 provider_session_id + relax stripe_session_id (Phase 3.2)
-- Supports a second IDV issuer (didit) feeding the existing document-root pipeline.
-- The didit webhook correlates by provider_session_id; Stripe keeps keying on
-- stripe_session_id, which becomes nullable so non-Stripe rows can omit it.
-- Additive and backward compatible (see docs/architecture/OPERATIONAL_HARDENING.md).

ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS provider_session_id VARCHAR(255);

-- Non-Stripe issuers do not populate stripe_session_id.
ALTER TABLE ishuman_verifications ALTER COLUMN stripe_session_id DROP NOT NULL;

-- Backfill: existing Stripe rows mirror their session id into the generic column
-- so future provider-agnostic lookups remain consistent.
UPDATE ishuman_verifications
   SET provider_session_id = stripe_session_id
 WHERE provider_session_id IS NULL
   AND stripe_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_ishuman_verifications_provider_session_id
    ON ishuman_verifications (provider_session_id);
