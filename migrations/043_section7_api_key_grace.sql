-- Section 7 follow-up: rotation grace metadata on normalized api_keys rows.
ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS grace_expires_at TIMESTAMP;
