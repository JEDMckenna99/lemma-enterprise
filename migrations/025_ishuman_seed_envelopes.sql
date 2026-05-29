-- Migration 025: isHuman v2 seed envelopes (Phase 1.1)
-- Server-sealed envelopes that let a post-IDV wallet derive its
-- wallet_local_seed and person_root_proxy from the network without exposing
-- the server-only person_root. All columns are additive and nullable so the
-- feature stays inert until LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS is enabled.

ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS wallet_seed_envelope BYTEA;
ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS person_root_proxy_envelope BYTEA;
ALTER TABLE ishuman_verifications ADD COLUMN IF NOT EXISTS seed_version VARCHAR(16);
