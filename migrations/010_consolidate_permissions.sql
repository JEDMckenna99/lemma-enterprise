-- Migration 010: Consolidate Platform Permissions
-- ================================================
-- 
-- Standard permission structure for lemma.id platform and customer sites.
-- 
-- IMPORTANT: The wallet page (/wallet) requires NO permission.
-- Any user can manage their own wallet/credentials without signing up.
-- Permissions are only needed for:
-- - Developer features (site registration, API keys, user management)
-- - Premium features (analytics, priority support)
-- - Admin features (platform administration)

-- Clear old permission types for lemma_platform
DELETE FROM permission_types WHERE site_id = 'lemma_platform';

-- Insert consolidated permission types for lemma.id platform
INSERT INTO permission_types (site_id, name, type, description, config, created_by, active) VALUES

-- Developer Access (registered developers who want to use lemma.id IAM)
('lemma_platform', 'developer', 'role', 'Developer access - register sites, manage API keys', 
 '{"scopes": ["site:create", "site:manage", "api_keys:manage", "dashboard:read"]}', 'system', true),

-- Site Admin (for each registered site)
('lemma_platform', 'site_admin', 'role', 'Full admin for a registered site',
 '{"scopes": ["users:manage", "permissions:define", "analytics:view", "settings:manage"]}', 'system', true),

-- Premium Tiers
('lemma_platform', 'premium_starter', 'subscription', 'Starter plan - up to 1,000 MAU',
 '{"mau_limit": 1000, "sites_limit": 3, "scopes": ["analytics:basic"]}', 'system', true),

('lemma_platform', 'premium_pro', 'subscription', 'Pro plan - up to 10,000 MAU',
 '{"mau_limit": 10000, "sites_limit": 10, "scopes": ["analytics:full", "support:priority"]}', 'system', true),

('lemma_platform', 'premium_enterprise', 'subscription', 'Enterprise plan - unlimited',
 '{"mau_limit": null, "sites_limit": null, "scopes": ["analytics:full", "support:dedicated", "sla:99.9"]}', 'system', true),

-- Platform Admin (lemma.id staff only)
('lemma_platform', 'platform_admin', 'role', 'Full platform administration',
 '{"scopes": ["admin:full", "billing:manage", "users:admin", "sites:admin"]}', 'system', true);

-- Add standard permission types that sites can use as templates
-- These are for customer sites, not lemma_platform

-- Create a template site for default permissions
INSERT INTO sites (site_id, site_domain, company_name, admin_email, api_key, oauth_client_id, oauth_client_secret, status)
VALUES ('_template', 'template.example', 'Template', 'template@lemma.id', 'template_key', 'template_client', 'template_secret', 'template')
ON CONFLICT (site_id) DO NOTHING;

-- Standard permission templates for customer sites
INSERT INTO permission_types (site_id, name, type, description, config, created_by, active) VALUES
('_template', 'viewer', 'role', 'Read-only access to the site', 
 '{"scopes": ["content:read"]}', 'system', true),
('_template', 'member', 'role', 'Standard member access',
 '{"scopes": ["content:read", "content:write", "profile:manage"]}', 'system', true),
('_template', 'moderator', 'role', 'Content moderation access',
 '{"scopes": ["content:read", "content:write", "content:moderate", "users:view"]}', 'system', true),
('_template', 'admin', 'role', 'Full site administration',
 '{"scopes": ["*"]}', 'system', true),
('_template', 'trial', 'time-bound', '14-day trial access',
 '{"duration_days": 14, "scopes": ["content:read", "content:write"]}', 'system', true)
ON CONFLICT DO NOTHING;

-- Add comments
COMMENT ON TABLE permission_types IS 'Permission type definitions. Sites can define custom permissions or use templates from _template site.';
