-- Migration 026: isHuman v2 issuer_id scaffold (Phase 3.2)
-- Records which IDV issuer produced each verification. Additive and defaulted
-- to the only integrated issuer today (stripe_identity); multi-issuer trust-list
-- integration is deferred (see docs/architecture/OPERATIONAL_HARDENING.md).

ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS issuer_id VARCHAR(64) DEFAULT 'stripe_identity';

UPDATE ishuman_verifications SET issuer_id = 'stripe_identity' WHERE issuer_id IS NULL;

CREATE INDEX IF NOT EXISTS ix_ishuman_verifications_issuer_id ON ishuman_verifications (issuer_id);
