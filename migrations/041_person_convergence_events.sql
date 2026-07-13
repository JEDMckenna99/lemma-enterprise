-- Migration 041: signed PPID convergence for provisional -> known-person rebind
--
-- When a provisional wallet IDVs to an already-document-anchored person, the
-- wallet rebinds to the canonical person root. Sites that bound accounts to the
-- provisional PPID receive a short-lived, site-scoped convergence artifact at
-- the next derive-site-proof call.

CREATE TABLE IF NOT EXISTS person_convergence_events (
    id SERIAL PRIMARY KEY,
    convergence_id VARCHAR(64) NOT NULL UNIQUE,
    wallet_id VARCHAR NOT NULL,
    superseded_person_id VARCHAR NOT NULL,
    canonical_person_id VARCHAR NOT NULL,
    idv_session_id VARCHAR,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    completed_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_person_convergence_wallet
    ON person_convergence_events (wallet_id);

CREATE INDEX IF NOT EXISTS idx_person_convergence_canonical
    ON person_convergence_events (canonical_person_id);

CREATE TABLE IF NOT EXISTS ppid_convergence_issued (
    id SERIAL PRIMARY KEY,
    convergence_id VARCHAR(64) NOT NULL,
    target_site VARCHAR(255) NOT NULL,
    legacy_ppid VARCHAR NOT NULL,
    canonical_ppid VARCHAR NOT NULL,
    nonce VARCHAR(64) NOT NULL,
    issued_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ppid_convergence_site
    ON ppid_convergence_issued (convergence_id, target_site);
