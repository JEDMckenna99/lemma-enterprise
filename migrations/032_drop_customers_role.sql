-- Migration 032: Drop customers.role (entitlement lives on platform_users.account_type)

ALTER TABLE customers DROP COLUMN IF EXISTS role;
