-- Section 8: billing outbox retry metadata + Stripe webhook idempotency store.

ALTER TABLE ishuman_billing_outbox
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_ishuman_billing_outbox_next_attempt
    ON ishuman_billing_outbox (status, next_attempt_at);

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) NOT NULL UNIQUE,
    event_type VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'processed',
    received_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    processed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_stripe_webhook_events_event_type
    ON stripe_webhook_events (event_type);
