-- Migration 031: Unified platform account on platform_users (single identity per PPID)

ALTER TABLE platform_users
ADD COLUMN IF NOT EXISTS account_type VARCHAR(50) DEFAULT 'customer';

ALTER TABLE platform_users
ADD COLUMN IF NOT EXISTS company VARCHAR(255);

ALTER TABLE platform_users
ADD COLUMN IF NOT EXISTS name VARCHAR(255);

ALTER TABLE platform_users
ADD COLUMN IF NOT EXISTS billing_customer_id VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_platform_users_account_type
ON platform_users(account_type);

CREATE INDEX IF NOT EXISTS idx_platform_users_billing_customer_id
ON platform_users(billing_customer_id);

-- Backfill account profile from customers where PPID matches
UPDATE platform_users pu
SET
    account_type = COALESCE(NULLIF(LOWER(c.role), ''), pu.account_type, 'customer'),
    email = COALESCE(pu.email, c.email),
    display_name = COALESCE(pu.display_name, c.display_name, c.name),
    name = COALESCE(pu.name, c.name),
    company = COALESCE(pu.company, c.company),
    wallet_id = COALESCE(pu.wallet_id, c.wallet_id),
    billing_customer_id = COALESCE(pu.billing_customer_id, c.customer_id)
FROM customers c
WHERE c.customer_did = pu.user_did;

-- Create platform_users rows for registered customers without a platform_users row
INSERT INTO platform_users (
    user_did,
    email,
    display_name,
    name,
    company,
    wallet_id,
    account_type,
    billing_customer_id,
    status,
    auth_method,
    verification_level,
    created_at,
    last_seen
)
SELECT
    c.customer_did,
    c.email,
    COALESCE(c.display_name, c.name),
    c.name,
    c.company,
    c.wallet_id,
    COALESCE(NULLIF(LOWER(c.role), ''), 'customer'),
    c.customer_id,
    COALESCE(c.status, 'active'),
    'wallet',
    'human_verified',
    COALESCE(c.created_at, CURRENT_TIMESTAMP),
    c.last_login
FROM customers c
WHERE c.customer_did IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM platform_users pu WHERE pu.user_did = c.customer_did
  );

-- Backfill owner accounts from active site_admins on lemma.id
UPDATE platform_users pu
SET account_type = 'owner'
FROM site_admins sa
WHERE sa.admin_did = pu.user_did
  AND sa.site_id IN ('lemma.id', 'lemma_platform')
  AND sa.is_active = TRUE
  AND LOWER(COALESCE(sa.admin_role, 'admin')) IN ('owner', 'super_admin', 'superadmin');

INSERT INTO platform_users (
    user_did,
    email,
    display_name,
    account_type,
    status,
    auth_method,
    verification_level,
    created_at,
    last_seen
)
SELECT
    sa.admin_did,
    sa.admin_email,
    split_part(sa.admin_email, '@', 1),
    COALESCE(NULLIF(LOWER(sa.admin_role), ''), 'owner'),
    'active',
    'wallet',
    'human_verified',
    COALESCE(sa.added_at, CURRENT_TIMESTAMP),
    sa.last_activity
FROM site_admins sa
WHERE sa.site_id IN ('lemma.id', 'lemma_platform')
  AND sa.is_active = TRUE
  AND sa.admin_did IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM platform_users pu WHERE pu.user_did = sa.admin_did
  );

COMMENT ON COLUMN platform_users.account_type IS 'Platform entitlement: owner, admin, developer, customer';
COMMENT ON COLUMN platform_users.billing_customer_id IS 'Optional link to customers.customer_id for Stripe/API keys';
