-- Migration 011: Consolidate storage to PostgreSQL
-- Moves data from customers.sites and customers.api_keys JSON to proper tables

-- Step 1: Add customer_id to sites table (links sites to customers)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'sites' AND column_name = 'customer_id') THEN
        ALTER TABLE sites ADD COLUMN customer_id VARCHAR(50);
    END IF;
END $$;

-- Step 2: Add environment column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'sites' AND column_name = 'environment') THEN
        ALTER TABLE sites ADD COLUMN environment VARCHAR(20) DEFAULT 'production';
    END IF;
END $$;

-- Step 3: Add site_label column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'sites' AND column_name = 'site_label') THEN
        ALTER TABLE sites ADD COLUMN site_label VARCHAR(255);
    END IF;
END $$;

-- Step 4: Make certain columns nullable for platform-registered sites
ALTER TABLE sites ALTER COLUMN api_key DROP NOT NULL;
ALTER TABLE sites ALTER COLUMN oauth_client_id DROP NOT NULL;
ALTER TABLE sites ALTER COLUMN company_name DROP NOT NULL;

-- Step 5: Create api_keys table (normalized from customers.api_keys JSON)
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    site_id VARCHAR(50) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_hint VARCHAR(8) NOT NULL,
    name VARCHAR(255) DEFAULT 'API Key',
    status VARCHAR(20) DEFAULT 'active',
    environment VARCHAR(20) DEFAULT 'production',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    revoked_at TIMESTAMP
);

-- Step 6: Add indexes
CREATE INDEX IF NOT EXISTS idx_sites_customer_id ON sites(customer_id);
CREATE INDEX IF NOT EXISTS idx_sites_environment ON sites(environment);
CREATE INDEX IF NOT EXISTS idx_api_keys_customer ON api_keys(customer_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_site ON api_keys(site_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status);
