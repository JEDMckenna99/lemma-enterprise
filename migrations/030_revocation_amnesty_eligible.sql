-- Migration 030: governance carve-out so fraud kills survive a fresh IDV
--
-- clear_amnesty_eligible_wallet_revocations lifts a wallet/person's site blocks
-- and wallet-level kills when they re-prove identity. That is correct for
-- ordinary site anti-abuse blocks, but a coordinated-fraud kill approved by
-- Lemma.id governance must NOT be self-clearable by simply re-running IDV.
--
-- Add an is_amnesty_eligible flag (default TRUE = legacy behavior) to both
-- revocation surfaces. Governance kills set it FALSE so the amnesty reset skips
-- them; they stay sticky until the network explicitly reinstates the subject.
--
-- Additive and backward compatible: existing rows default TRUE (unchanged
-- behavior), and the amnesty query treats TRUE/NULL as eligible.

ALTER TABLE revocation_list
    ADD COLUMN IF NOT EXISTS is_amnesty_eligible BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE site_blocks
    ADD COLUMN IF NOT EXISTS is_amnesty_eligible BOOLEAN NOT NULL DEFAULT TRUE;
