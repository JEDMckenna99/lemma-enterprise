-- Migration 028: enforce one isHuman verification row per (provider_session_id, wallet_id)
--
-- Root cause of the "Verification pending forever" bug: the provider (Didit)
-- can reuse one hosted session across repeated start-verification calls, which
-- created sibling rows sharing the same provider_session_id. The webhook only
-- flips the FIRST matching sibling to verified, so a client polling the other
-- sibling never saw 'verified'. Application-level dedup is racy under
-- concurrency; this makes the invariant a hard database constraint.
--
-- Additive and backward compatible. Partial index so rows that legitimately
-- omit either column (legacy/NULL provider session) stay unconstrained.

-- 1) Resolve any pre-existing duplicates so the unique index can be created.
--    Keep the best row per (provider_session_id, wallet_id) -- prefer a row that
--    already issued a credential / is verified / is newest -- and DETACH the
--    losers by nulling provider_session_id. Detached rows are orphaned pending
--    rows; verification_status still resolves them to the kept verified row via
--    the wallet_id sibling fallback.
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY provider_session_id, wallet_id
               ORDER BY (credential_id IS NOT NULL) DESC,
                        (status = 'verified') DESC,
                        verified_at DESC NULLS LAST,
                        created_at DESC
           ) AS rn
      FROM ishuman_verifications
     WHERE provider_session_id IS NOT NULL
       AND wallet_id IS NOT NULL
)
UPDATE ishuman_verifications v
   SET provider_session_id = NULL
  FROM ranked r
 WHERE v.id = r.id
   AND r.rn > 1;

-- 2) Enforce uniqueness going forward.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ishuman_provider_session_wallet
    ON ishuman_verifications (provider_session_id, wallet_id)
    WHERE provider_session_id IS NOT NULL
      AND wallet_id IS NOT NULL;
