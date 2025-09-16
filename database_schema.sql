-- Lemma.id Platform Database Schema
-- Complete IAM platform with two-tier billing (PoH + Permissions)
-- Enhanced with vault storage for device sync and wallet recovery

-- Sites table: Customer sites registered on lemma.id platform
CREATE TABLE sites (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) UNIQUE NOT NULL,           -- e.g., "site_abc123def456"
    site_domain VARCHAR(255) NOT NULL,             -- e.g., "customer.com"
    company_name VARCHAR(255) NOT NULL,            -- e.g., "Customer Inc"
    admin_email VARCHAR(255) NOT NULL,             -- Primary contact
    plan VARCHAR(50) DEFAULT 'starter',            -- starter, professional, enterprise
    api_key VARCHAR(100) UNIQUE NOT NULL,          -- Site API key
    oauth_client_id VARCHAR(100) UNIQUE NOT NULL,  -- OAuth client ID
    oauth_client_secret VARCHAR(100) NOT NULL,     -- OAuth client secret
    status VARCHAR(20) DEFAULT 'active',           -- active, suspended, cancelled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Billing information
    stripe_customer_id VARCHAR(100),               -- Stripe customer ID
    billing_email VARCHAR(255),                    -- Billing contact
    
    -- Configuration
    max_permissions_per_user INTEGER DEFAULT 50,   -- Limit per user
    require_poh BOOLEAN DEFAULT TRUE,              -- Require PoH for access
    allow_federation BOOLEAN DEFAULT FALSE,        -- Cross-site permissions
    session_timeout INTEGER DEFAULT 3600,         -- Session timeout (seconds)
    mfa_required BOOLEAN DEFAULT FALSE,            -- Multi-factor auth required
    
    INDEX idx_site_id (site_id),
    INDEX idx_domain (site_domain),
    INDEX idx_status (status)
);

-- Permissions table: Permission definitions for each site
CREATE TABLE permissions (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    permission_id VARCHAR(100) NOT NULL,           -- e.g., "admin", "user", "read_only"
    display_name VARCHAR(255) NOT NULL,            -- e.g., "Administrator"
    description TEXT,                              -- Permission description
    scope JSON NOT NULL,                           -- Array of scope strings ["users:*", "posts:read"]
    conditions JSON DEFAULT '[]',                  -- Array of conditions ["ip_range:192.168.1.0/24"]
    expiry_days INTEGER,                           -- Default expiry in days (NULL = no expiry)
    delegation_allowed BOOLEAN DEFAULT FALSE,      -- Can be delegated to others
    priority INTEGER DEFAULT 100,                 -- Permission priority (higher = more access)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),                       -- DID of creator
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY unique_site_permission (site_id, permission_id),
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_site_permissions (site_id),
    INDEX idx_permission_priority (site_id, priority DESC)
);

-- User permissions table: Granted permissions for users
CREATE TABLE user_permissions (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    user_did VARCHAR(255) NOT NULL,                -- User's DID
    permission_id VARCHAR(100) NOT NULL,           -- References permissions.permission_id
    credential_fingerprint VARCHAR(128) NOT NULL,  -- Wallet credential fingerprint
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by VARCHAR(255) NOT NULL,              -- DID of granter
    expires_at TIMESTAMP,                          -- Permission expiry (NULL = no expiry)
    revoked_at TIMESTAMP,                          -- Revocation timestamp (NULL = active)
    revoked_by VARCHAR(255),                       -- DID of revoker
    revocation_reason TEXT,                        -- Reason for revocation
    
    UNIQUE KEY unique_user_site_permission (site_id, user_did, permission_id),
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    FOREIGN KEY (site_id, permission_id) REFERENCES permissions(site_id, permission_id) ON DELETE CASCADE,
    INDEX idx_user_permissions (user_did, site_id),
    INDEX idx_site_user_permissions (site_id, user_did),
    INDEX idx_active_permissions (site_id, user_did, revoked_at),
    INDEX idx_expiring_permissions (expires_at)
);

-- Monthly Active Users (MAU) tracking for two-tier billing
CREATE TABLE monthly_active_users (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,              -- References sites.site_id for site-level tracking
    user_id_hash VARCHAR(64) NOT NULL,             -- HMAC-SHA256 salted user ID for privacy
    activity_type VARCHAR(50) NOT NULL,            -- 'poh_network', 'site_iam'
    site_id VARCHAR(50),                           -- NULL for PoH network, site_id for IAM
    month_year VARCHAR(7) NOT NULL,                -- Format: "2024-01" 
    first_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activity_count INTEGER DEFAULT 1,              -- Number of activities this month
    
    UNIQUE KEY unique_user_month_activity (customer_id, user_id_hash, activity_type, site_id, month_year),
    FOREIGN KEY (customer_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_mau_billing (customer_id, month_year, activity_type),
    INDEX idx_mau_site (site_id, month_year),
    INDEX idx_mau_cleanup (month_year)
);

-- Stripe Identity verifications (one-time $2 fee)
CREATE TABLE stripe_identity_verifications (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,              -- References sites.site_id
    user_id_hash VARCHAR(64) NOT NULL,             -- HMAC-SHA256 salted user ID
    stripe_verification_id VARCHAR(100) NOT NULL,  -- Stripe verification session ID
    verification_status VARCHAR(50) NOT NULL,      -- verified, failed, pending
    verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    amount_charged DECIMAL(10,2) DEFAULT 2.00,     -- $2.00 fee
    stripe_charge_id VARCHAR(100),                 -- Stripe charge ID
    
    UNIQUE KEY unique_user_verification (customer_id, user_id_hash),
    FOREIGN KEY (customer_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_stripe_verifications (customer_id, verification_date),
    INDEX idx_stripe_status (verification_status)
);

-- OAuth authorization codes (temporary storage)
CREATE TABLE oauth_authorization_codes (
    id SERIAL PRIMARY KEY,
    auth_code VARCHAR(100) UNIQUE NOT NULL,        -- Authorization code
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    client_id VARCHAR(100) NOT NULL,               -- OAuth client ID
    redirect_uri TEXT NOT NULL,                    -- Callback URL
    scope VARCHAR(255) DEFAULT 'profile',          -- Requested scope
    state VARCHAR(255),                            -- CSRF protection state
    user_did VARCHAR(255),                         -- User DID (set after authorization)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,                 -- 10 minute expiry
    used_at TIMESTAMP,                             -- When code was exchanged
    
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_auth_codes (auth_code),
    INDEX idx_auth_expiry (expires_at),
    INDEX idx_auth_cleanup (created_at)
);

-- OAuth access tokens (JWT tokens for API access)
CREATE TABLE oauth_access_tokens (
    id SERIAL PRIMARY KEY,
    token_hash VARCHAR(64) UNIQUE NOT NULL,        -- SHA256 hash of JWT token
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    user_did VARCHAR(255) NOT NULL,                -- User DID
    scope VARCHAR(255) DEFAULT 'profile',          -- Token scope
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,                 -- 1 hour expiry
    revoked_at TIMESTAMP,                          -- Token revocation
    last_used TIMESTAMP,                           -- Last API usage
    
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_access_tokens (token_hash),
    INDEX idx_token_expiry (expires_at),
    INDEX idx_token_usage (site_id, user_did, last_used)
);

-- API usage tracking for rate limiting and analytics
CREATE TABLE api_usage (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    endpoint VARCHAR(255) NOT NULL,                -- API endpoint called
    method VARCHAR(10) NOT NULL,                   -- HTTP method
    user_did VARCHAR(255),                         -- User DID (if authenticated)
    ip_address INET,                               -- Client IP address
    user_agent TEXT,                               -- Client user agent
    response_status INTEGER NOT NULL,              -- HTTP response status
    response_time_ms INTEGER,                      -- Response time in milliseconds
    request_size INTEGER,                          -- Request size in bytes
    response_size INTEGER,                         -- Response size in bytes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_api_usage_site (site_id, created_at),
    INDEX idx_api_usage_endpoint (endpoint, created_at),
    INDEX idx_api_usage_user (user_did, created_at),
    INDEX idx_api_usage_cleanup (created_at)
);

-- Billing invoices and charges
CREATE TABLE billing_invoices (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    invoice_period VARCHAR(7) NOT NULL,            -- Format: "2024-01"
    
    -- PoH Network charges
    poh_mau_count INTEGER DEFAULT 0,               -- Monthly active users for PoH
    poh_rate DECIMAL(10,4) DEFAULT 0.05,          -- $0.05 per MAU
    poh_amount DECIMAL(10,2) DEFAULT 0.00,        -- Total PoH charges
    
    -- Site IAM charges  
    iam_mau_count INTEGER DEFAULT 0,               -- Monthly active users for IAM
    iam_rate DECIMAL(10,4) DEFAULT 0.15,          -- $0.15 per MAU per site
    iam_amount DECIMAL(10,2) DEFAULT 0.00,        -- Total IAM charges
    
    -- Stripe Identity charges
    identity_verification_count INTEGER DEFAULT 0, -- New verifications this month
    identity_rate DECIMAL(10,2) DEFAULT 2.00,     -- $2.00 per verification
    identity_amount DECIMAL(10,2) DEFAULT 0.00,   -- Total identity charges
    
    -- Invoice totals
    subtotal DECIMAL(10,2) NOT NULL,              -- Sum of all charges
    tax_rate DECIMAL(5,4) DEFAULT 0.00,           -- Tax rate (if applicable)
    tax_amount DECIMAL(10,2) DEFAULT 0.00,        -- Tax amount
    total_amount DECIMAL(10,2) NOT NULL,          -- Final amount
    
    -- Stripe billing
    stripe_invoice_id VARCHAR(100),               -- Stripe invoice ID
    stripe_charge_id VARCHAR(100),                -- Stripe charge ID
    payment_status VARCHAR(50) DEFAULT 'pending', -- pending, paid, failed
    payment_date TIMESTAMP,                       -- Payment completion date
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY unique_site_period (site_id, invoice_period),
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_billing_period (invoice_period),
    INDEX idx_billing_status (payment_status),
    INDEX idx_billing_amounts (site_id, total_amount)
);

-- Performance metrics and monitoring
CREATE TABLE performance_metrics (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(50) NOT NULL,                  -- References sites.site_id
    metric_type VARCHAR(50) NOT NULL,              -- 'verification_time', 'api_response', 'error_rate'
    metric_value DECIMAL(15,6) NOT NULL,           -- Metric value (microseconds, milliseconds, percentage)
    user_did VARCHAR(255),                         -- User DID (if user-specific)
    endpoint VARCHAR(255),                         -- API endpoint (if endpoint-specific)
    additional_data JSON,                          -- Additional metric metadata
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (site_id) REFERENCES sites(site_id) ON DELETE CASCADE,
    INDEX idx_metrics_site_type (site_id, metric_type, recorded_at),
    INDEX idx_metrics_performance (metric_type, metric_value, recorded_at),
    INDEX idx_metrics_cleanup (recorded_at)
);

-- System configuration and feature flags
CREATE TABLE system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,       -- Configuration key
    config_value TEXT NOT NULL,                    -- Configuration value (JSON)
    description TEXT,                              -- Configuration description
    is_public BOOLEAN DEFAULT FALSE,               -- Can be read by sites
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_config_key (config_key),
    INDEX idx_public_config (is_public)
);

-- Insert default system configuration
INSERT INTO system_config (config_key, config_value, description, is_public) VALUES
('poh_network_rate', '0.05', 'PoH network rate per MAU in USD', TRUE),
('iam_rate_per_site', '0.15', 'IAM rate per MAU per site in USD', TRUE),
('stripe_identity_rate', '2.00', 'Stripe Identity verification fee in USD', TRUE),
('max_api_requests_per_minute', '1000', 'Rate limit for API requests', TRUE),
('verification_target_time_us', '4.176', 'Target verification time in microseconds', TRUE),
('oauth_code_expiry_minutes', '10', 'OAuth authorization code expiry time', FALSE),
('access_token_expiry_hours', '1', 'OAuth access token expiry time', FALSE),
('session_cleanup_days', '30', 'Days to keep expired sessions', FALSE);

-- Create views for common queries

-- Active sites with current billing period
CREATE VIEW active_sites_billing AS
SELECT 
    s.*,
    COALESCE(bi.poh_mau_count, 0) as current_poh_mau,
    COALESCE(bi.iam_mau_count, 0) as current_iam_mau,
    COALESCE(bi.total_amount, 0) as current_month_charges,
    DATE_FORMAT(NOW(), '%Y-%m') as current_period
FROM sites s
LEFT JOIN billing_invoices bi ON s.site_id = bi.site_id 
    AND bi.invoice_period = DATE_FORMAT(NOW(), '%Y-%m')
WHERE s.status = 'active';

-- Monthly active users summary by site
CREATE VIEW mau_summary AS
SELECT 
    mau.customer_id,
    mau.month_year,
    COUNT(CASE WHEN mau.activity_type = 'poh_network' THEN 1 END) as poh_users,
    COUNT(CASE WHEN mau.activity_type = 'site_iam' THEN 1 END) as iam_users,
    COUNT(DISTINCT mau.site_id) as active_sites,
    SUM(mau.activity_count) as total_activities
FROM monthly_active_users mau
GROUP BY mau.customer_id, mau.month_year;

-- Permission usage analytics
CREATE VIEW permission_analytics AS
SELECT 
    p.site_id,
    p.permission_id,
    p.display_name,
    COUNT(up.id) as total_grants,
    COUNT(CASE WHEN up.revoked_at IS NULL AND (up.expires_at IS NULL OR up.expires_at > NOW()) THEN 1 END) as active_grants,
    COUNT(CASE WHEN up.revoked_at IS NOT NULL THEN 1 END) as revoked_grants,
    COUNT(CASE WHEN up.expires_at IS NOT NULL AND up.expires_at <= NOW() THEN 1 END) as expired_grants,
    AVG(CASE WHEN up.revoked_at IS NOT NULL THEN TIMESTAMPDIFF(SECOND, up.granted_at, up.revoked_at) END) as avg_duration_seconds
FROM permissions p
LEFT JOIN user_permissions up ON p.site_id = up.site_id AND p.permission_id = up.permission_id
GROUP BY p.site_id, p.permission_id, p.display_name;

-- API performance summary
CREATE VIEW api_performance AS
SELECT 
    au.site_id,
    au.endpoint,
    COUNT(*) as total_requests,
    AVG(au.response_time_ms) as avg_response_time_ms,
    COUNT(CASE WHEN au.response_status >= 200 AND au.response_status < 300 THEN 1 END) / COUNT(*) * 100 as success_rate,
    COUNT(CASE WHEN au.response_status >= 400 THEN 1 END) as error_count,
    DATE(au.created_at) as request_date
FROM api_usage au
WHERE au.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY au.site_id, au.endpoint, DATE(au.created_at);

-- Cleanup procedures (run daily)
DELIMITER //
CREATE PROCEDURE CleanupExpiredData()
BEGIN
    -- Clean up expired OAuth codes
    DELETE FROM oauth_authorization_codes 
    WHERE expires_at < DATE_SUB(NOW(), INTERVAL 1 HOUR);
    
    -- Clean up expired access tokens
    DELETE FROM oauth_access_tokens 
    WHERE expires_at < DATE_SUB(NOW(), INTERVAL 1 DAY);
    
    -- Clean up old API usage logs (keep 90 days)
    DELETE FROM api_usage 
    WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
    
    -- Clean up old performance metrics (keep 30 days)
    DELETE FROM performance_metrics 
    WHERE recorded_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
    
    -- Archive old MAU data (keep 24 months)
    DELETE FROM monthly_active_users 
    WHERE STR_TO_DATE(CONCAT(month_year, '-01'), '%Y-%m-%d') < DATE_SUB(NOW(), INTERVAL 24 MONTH);
END //
DELIMITER ;

-- Performance indexes for common queries
CREATE INDEX idx_sites_active ON sites(status, created_at);
CREATE INDEX idx_permissions_active ON permissions(site_id, created_at);
CREATE INDEX idx_user_permissions_active ON user_permissions(site_id, user_did, revoked_at, expires_at);
CREATE INDEX idx_mau_current_month ON monthly_active_users(customer_id, month_year, activity_type);
CREATE INDEX idx_billing_current ON billing_invoices(site_id, invoice_period, payment_status);
CREATE INDEX idx_api_recent ON api_usage(site_id, created_at DESC);

-- Vault Storage table: Encrypted wallet envelopes for device sync
CREATE TABLE vault_envelopes (
    id SERIAL PRIMARY KEY,
    vid VARCHAR(64) UNIQUE NOT NULL,                    -- Vault Index (privacy-preserving lookup)
    ciphertext TEXT NOT NULL,                          -- Hex-encoded encrypted wallet envelope
    counter INTEGER NOT NULL DEFAULT 1,               -- Monotonic counter for rollback protection
    aad TEXT,                                          -- Additional authenticated data (hex)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   -- When envelope was first stored
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   -- When envelope was last updated
    access_count INTEGER DEFAULT 0,                   -- Number of times accessed
    last_accessed_at TIMESTAMP,                       -- Last access timestamp
    client_ip INET,                                    -- Last client IP for security monitoring
    expires_at TIMESTAMP,                             -- Optional expiration (for temporary envelopes)
    
    INDEX idx_vid (vid),                              -- Fast VID lookup
    INDEX idx_created_at (created_at),                -- Cleanup queries
    INDEX idx_expires_at (expires_at)                 -- Expiration cleanup
);

-- Vault Access Log table: Audit trail for security monitoring
CREATE TABLE vault_access_log (
    id SERIAL PRIMARY KEY,
    vid VARCHAR(64) NOT NULL,                         -- Vault Index (partial for privacy)
    operation VARCHAR(20) NOT NULL,                  -- 'put', 'get', 'delete'
    client_ip INET NOT NULL,                          -- Client IP address
    user_agent TEXT,                                  -- User agent string
    success BOOLEAN NOT NULL,                        -- Operation success/failure
    error_message TEXT,                              -- Error details if failed
    response_time_ms INTEGER,                        -- Operation response time
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   -- When operation occurred
    
    INDEX idx_vid_operation (vid, operation),        -- Security queries
    INDEX idx_timestamp (timestamp),                 -- Time-based queries
    INDEX idx_client_ip (client_ip),                 -- IP-based monitoring
    INDEX idx_failed_attempts (success, timestamp)   -- Failed attempt monitoring
);

-- Vault Rate Limiting table: Track request rates per VID/IP
CREATE TABLE vault_rate_limits (
    id SERIAL PRIMARY KEY,
    vid VARCHAR(64) NOT NULL,                         -- Vault Index
    client_ip INET NOT NULL,                          -- Client IP address
    request_count INTEGER DEFAULT 1,                 -- Number of requests
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Rate limit window start
    last_request TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Last request time
    
    UNIQUE(vid, client_ip, window_start),            -- One record per VID/IP/hour
    INDEX idx_rate_limit_window (vid, client_ip, window_start),
    INDEX idx_rate_limit_cleanup (window_start)      -- Cleanup old windows
);
CREATE INDEX idx_metrics_recent ON performance_metrics(site_id, metric_type, recorded_at DESC);
