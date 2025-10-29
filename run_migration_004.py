"""
Run Migration 004: Fix IAM Audit Log Constraints
Adds multi-tenant security improvements:
- Makes iam_audit_log.site_id NOT NULL
- Adds foreign key constraint
- Enables Row-Level Security (RLS)
"""

import os
import psycopg2

def run_migration():
    # Get DATABASE_URL from environment
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not set")
        return
    
    # Fix Heroku URL format
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    print("🔗 Connecting to database...")
    
    try:
        # Connect with SSL required (Heroku)
        conn = psycopg2.connect(db_url, sslmode='require')
        conn.autocommit = False
        cursor = conn.cursor()
        
        print("📖 Reading migration file...")
        with open('migrations/004_fix_audit_log_constraints.sql', 'r') as f:
            migration_sql = f.read()
        
        print("🚀 Running migration 004...")
        cursor.execute(migration_sql)
        
        # Commit the transaction
        conn.commit()
        
        print("\n✅ Migration 004 completed successfully!")
        print("\n📊 Verifying constraints...")
        
        # Verify the changes
        cursor.execute("""
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'iam_audit_log'
                AND tc.constraint_type = 'FOREIGN KEY';
        """)
        
        fk_results = cursor.fetchall()
        if fk_results:
            print("✅ Foreign key constraint added:")
            for constraint_name, constraint_type, column_name in fk_results:
                print(f"   - {constraint_name} ({constraint_type}) on {column_name}")
        else:
            print("⚠️  No foreign key constraints found (might already exist)")
        
        # Check RLS status
        cursor.execute("""
            SELECT schemaname, tablename, rowsecurity
            FROM pg_tables
            WHERE tablename IN ('permission_types', 'permission_instances', 
                               'permission_policies', 'iam_audit_log')
                AND schemaname = 'public';
        """)
        
        rls_results = cursor.fetchall()
        print("\n✅ Row-Level Security (RLS) status:")
        for schema, table, rls_enabled in rls_results:
            status = "ENABLED" if rls_enabled else "DISABLED"
            print(f"   - {table}: {status}")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Migration 004 complete! Multi-tenant security enhanced.")
        
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        if conn:
            conn.rollback()
            conn.close()
    except FileNotFoundError:
        print("❌ Migration file not found: migrations/004_fix_audit_log_constraints.sql")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if conn:
            conn.rollback()
            conn.close()

if __name__ == '__main__':
    run_migration()

