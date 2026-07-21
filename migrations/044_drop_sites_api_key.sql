-- Section 7 completion: drop legacy sites.api_key column (auth is hash-only via api_keys).
ALTER TABLE sites DROP COLUMN IF EXISTS api_key;
