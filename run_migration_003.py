#!/usr/bin/env python3
"""
Run Migration 003 - Add Permission Types System
Executes the SQL migration on Heroku PostgreSQL
"""

import os
import psycopg2

# Get database URL from environment (set by Heroku)
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not set - run this on Heroku")
    exit(1)

# Fix DATABASE_URL for psycopg2 (postgres:// -> postgresql://)
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

print("🔗 Connecting to database...")
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cursor = conn.cursor()

print("📋 Running migration 003_add_permission_types.sql...")

# Read and execute migration
with open('migrations/003_add_permission_types.sql', 'r') as f:
    sql = f.read()
    
try:
    cursor.execute(sql)
    conn.commit()
    print("✅ Migration 003 completed successfully!")
    
    # Verify tables created
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('permission_types', 'permission_instances', 'permission_policies', 'iam_audit_log')
        ORDER BY table_name
    """)
    
    tables = cursor.fetchall()
    print(f"\n📊 Created tables:")
    for table in tables:
        print(f"   ✅ {table[0]}")
    
    if len(tables) == 4:
        print("\n🎉 All 4 IAM tables created successfully!")
    else:
        print(f"\n⚠️ Only {len(tables)}/4 tables created")
        
except Exception as e:
    print(f"❌ Migration failed: {e}")
    conn.rollback()
    exit(1)
finally:
    cursor.close()
    conn.close()

