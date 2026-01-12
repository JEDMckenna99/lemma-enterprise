-- Migration 011: Consolidate storage to PostgreSQL
-- Moves data from customers.sites and customers.api_keys JSON to proper tables
-- This eliminates fragmented storage and enables proper queries/indexes

-- Step 1: Add customer_id to sites table (links sites to customers)
ALTER TABLE sites 
ADD COLUMN IF NOT EXISTS customer_id VARCHAR(50);

-- Step 2: Make certain columns nullable for platform-registered sites
-- (they may not have OAuth credentials initially)
ALTER TABLE sites 
ALTER COLUMN api_key DROP NOT NULL,
ALTER COLUMN oauth_client_id DROP NOT NULL,
ALTER COLUMN company_name DROP NOT NULL;

-- Step 3: Add environment column for staging/production distinction
ALTER TABLE sites
ADD COLUMN IF NOT EXISTS environment VARCHAR(20) DEFAULT 'production',
ADD COLUMN IF NOT EXISTS site_label VARCHAR(255);

-- Step 4: Create api_keys table (normalized from customers.api_keys JSON)
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    site_id VARCHAR(50) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,              -- SHA256 hash of the key
    key_hint VARCHAR(8) NOT NULL,               -- Last 8 chars for display
    name VARCHAR(255) DEFAULT 'API Key',
    status VARCHAR(20) DEFAULT 'active',        -- active, revoked
    environment VARCHAR(20) DEFAULT 'production',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    usage_count INTEGER DEFAULT 0,
    revoked_at TIMESTAMP,
    
    -- Indexes for common queries
    UNIQUE (key_hash),
    INDEX idx_api_keys_customer (customer_id),
    INDEX idx_api_keys_site (site_id),
    INDEX idx_api_keys_status (status)
);

-- Step 5: Add foreign key indexes to sites table
CREATE INDEX IF NOT EXISTS idx_sites_customer_id ON sites(customer_id);
CREATE INDEX IF NOT EXISTS idx_sites_environment ON sites(environment);

-- Step 6: Create a view for easy customer-site-apikey lookups
CREATE OR REPLACE VIEW customer_sites_view AS
SELECT 
    c.customer_id,
    c.email as customer_email,
    c.name as customer_name,
    s.site_id,
    s.site_domain,
    s.company_name,
    s.site_label,
    s.environment,
    s.status as site_status,
    s.created_at as site_created_at,
    COUNT(ak.id) as api_key_count
FROM customers c
LEFT JOIN sites s ON c.customer_id = s.customer_id
LEFT JOIN api_keys ak ON s.site_id = ak.site_id AND ak.status = 'active'
GROUP BY c.customer_id, c.email, c.name, s.site_id, s.site_domain, 
         s.company_name, s.site_label, s.environment, s.status, s.created_at;

-- Note: After running this migration, run the Python migration script to:
-- 1. Copy data from customers.sites JSON to sites table
-- 2. Copy data from customers.api_keys JSON to api_keys table
-- 3. Update customer_id foreign keys
