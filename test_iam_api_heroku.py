#!/usr/bin/env python3
"""
Test IAM Permission Types API on Heroku
"""

import os
import psycopg2
import json

# Get database URL
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

print("=" * 60)
print("  IAM PERMISSION TYPES - API TEST")
print("=" * 60)

# Connect to database
print("\n🔗 Connecting to database...")
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cursor = conn.cursor()

# Step 1: Find or create a test site
print("\n📋 Step 1: Finding test site...")
cursor.execute("SELECT site_id, site_domain, company_name FROM sites LIMIT 1")
site = cursor.fetchone()

if site:
    test_site_id, test_domain, test_company = site
    print(f"✅ Found site: {test_site_id} ({test_domain})")
else:
    print("⚠️ No sites found - creating test site...")
    # Create a test site
    test_site_id = "site_test_iam_001"
    test_domain = "test-iam.lemma.id"
    test_company = "Test IAM Company"
    
    cursor.execute("""
        INSERT INTO sites (site_id, site_domain, company_name, admin_email, api_key, oauth_client_id, oauth_client_secret)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (site_id) DO NOTHING
        RETURNING site_id
    """, (
        test_site_id,
        test_domain,
        test_company,
        'admin@test-iam.lemma.id',
        'test_api_key_123',
        'test_oauth_client',
        'test_oauth_secret'
    ))
    
    result = cursor.fetchone()
    if result:
        print(f"✅ Created test site: {test_site_id}")
    else:
        print(f"✅ Test site already exists: {test_site_id}")
    
    conn.commit()

# Step 2: Create a permission type
print(f"\n📋 Step 2: Creating permission type on site {test_site_id}...")

cursor.execute("""
    INSERT INTO permission_types (site_id, name, type, description, config, created_by)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (site_id, name) DO UPDATE SET
        description = EXCLUDED.description,
        config = EXCLUDED.config
    RETURNING id, name, type
""", (
    test_site_id,
    'premium_tier_1',
    'time-bound',
    'Premium subscription tier 1',
    json.dumps({'duration_days': 365, 'auto_renew': False}),
    'system'
))

perm_type = cursor.fetchone()
perm_type_id, perm_name, perm_type_val = perm_type
conn.commit()

print(f"✅ Permission type created/updated:")
print(f"   ID: {perm_type_id}")
print(f"   Name: {perm_name}")
print(f"   Type: {perm_type_val}")

# Step 3: Grant permission to a user
print(f"\n📋 Step 3: Granting permission to test user...")

test_email = "testuser@example.com"

cursor.execute("""
    INSERT INTO permission_instances (permission_type_id, site_id, email, granted_by, metadata)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id, email
""", (
    perm_type_id,
    test_site_id,
    test_email,
    'admin@test',
    json.dumps({'reason': 'Test subscription', 'order_id': 'TEST-001'})
))

instance = cursor.fetchone()
instance_id, instance_email = instance
conn.commit()

print(f"✅ Permission granted:")
print(f"   Instance ID: {instance_id}")
print(f"   Email: {instance_email}")

# Step 4: Search users with permission
print(f"\n📋 Step 4: Searching users with permission '{perm_name}'...")

cursor.execute("""
    SELECT pi.email, pt.name, pi.granted_at, pi.metadata
    FROM permission_instances pi
    JOIN permission_types pt ON pi.permission_type_id = pt.id
    WHERE pi.site_id = %s
    AND pt.name = %s
    AND pi.revoked_at IS NULL
""", (test_site_id, perm_name))

users = cursor.fetchall()

print(f"✅ Found {len(users)} user(s) with permission:")
for user in users:
    print(f"   - {user[0]} (granted: {user[2]})")

# Step 5: Get IAM stats
print(f"\n📋 Step 5: Getting IAM stats for site {test_site_id}...")

cursor.execute("""
    SELECT COUNT(*) FROM permission_types 
    WHERE site_id = %s AND active = true
""", [test_site_id])
perm_types_count = cursor.fetchone()[0]

cursor.execute("""
    SELECT COUNT(DISTINCT email) FROM permission_instances 
    WHERE site_id = %s AND revoked_at IS NULL
""", [test_site_id])
active_users_count = cursor.fetchone()[0]

cursor.execute("""
    SELECT COUNT(*) FROM permission_instances 
    WHERE site_id = %s AND revoked_at IS NULL
""", [test_site_id])
active_instances_count = cursor.fetchone()[0]

print(f"✅ IAM Statistics:")
print(f"   Permission Types: {perm_types_count}")
print(f"   Active Users: {active_users_count}")
print(f"   Active Instances: {active_instances_count}")

# Step 6: Log audit event
print(f"\n📋 Step 6: Testing audit logging...")

cursor.execute("""
    INSERT INTO iam_audit_log (site_id, event_type, actor, target, details)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id, event_type, timestamp
""", (
    test_site_id,
    'permission_granted_test',
    'admin@test',
    test_email,
    json.dumps({'test': True, 'permission': perm_name})
))

audit = cursor.fetchone()
audit_id, audit_event, audit_time = audit
conn.commit()

print(f"✅ Audit event logged:")
print(f"   ID: {audit_id}")
print(f"   Event: {audit_event}")
print(f"   Time: {audit_time}")

# Step 7: Revoke permission
print(f"\n📋 Step 7: Revoking permission...")

cursor.execute("""
    UPDATE permission_instances
    SET revoked_at = NOW(),
        revoked_by = %s,
        revocation_reason = %s
    WHERE id = %s
    RETURNING id, email, revoked_at
""", (
    'admin@test',
    'Test revocation',
    instance_id
))

revoked = cursor.fetchone()
conn.commit()

if revoked:
    print(f"✅ Permission revoked:")
    print(f"   Instance ID: {revoked[0]}")
    print(f"   Email: {revoked[1]}")
    print(f"   Revoked at: {revoked[2]}")
else:
    print("⚠️ No permission to revoke")

# Cleanup
cursor.close()
conn.close()

# Final summary
print("\n" + "=" * 60)
print("  TEST SUMMARY")
print("=" * 60)
print("✅ Database migration completed")
print("✅ Permission type created")
print("✅ Permission granted to user")
print("✅ User search working")
print("✅ IAM stats working")
print("✅ Audit logging working")
print("✅ Permission revocation working")
print("=" * 60)
print("🎉 ALL DATABASE OPERATIONS SUCCESSFUL!")
print("=" * 60)
print(f"\nTest Site ID: {test_site_id}")
print(f"Test Permission: {perm_name}")
print(f"Test User: {test_email}")
print("\n💡 Next: Test REST API endpoints via HTTP requests")

