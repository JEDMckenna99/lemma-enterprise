#!/usr/bin/env python3
"""
Run PPID migration to clear old global DIDs and update to PPID-based tracking.
Run this on Heroku: heroku run python scripts/run_ppid_migration.py --app lemma-enterprise
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def table_exists(db, table_name):
    """Check if a table exists in the database."""
    from sqlalchemy import text
    result = db.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = :table_name
        )
    """), {'table_name': table_name}).fetchone()
    return result[0] if result else False

def run_migration():
    from api.database import get_db
    from sqlalchemy import text
    
    db = get_db()
    
    try:
        # List existing tables
        print("📋 Current database tables:")
        result = db.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)).fetchall()
        for row in result:
            print(f"   - {row[0]}")
        
        # Check user_permissions table
        print("\n🔍 Checking user_permissions table...")
        if table_exists(db, 'user_permissions'):
            result = db.execute(text("SELECT COUNT(*) FROM user_permissions")).fetchone()
            total_count = result[0] if result else 0
            print(f"   Total records: {total_count}")
            
            result = db.execute(text("SELECT COUNT(*) FROM user_permissions WHERE user_did LIKE 'did:lemma:user:%'")).fetchone()
            old_count = result[0] if result else 0
            print(f"   Old format (did:lemma:user:xxx): {old_count}")
            
            result = db.execute(text("SELECT COUNT(*) FROM user_permissions WHERE user_did LIKE 'did:lemma:ppid_%'")).fetchone()
            ppid_count = result[0] if result else 0
            print(f"   New format (did:lemma:ppid_xxx): {ppid_count}")
            
            if old_count > 0:
                print(f"\n🧹 Clearing {old_count} old records with global DIDs...")
                db.execute(text("DELETE FROM user_permissions WHERE user_did LIKE 'did:lemma:user:%'"))
                db.commit()
                print("   ✅ Done!")
            else:
                print("\n✅ No old records to clear!")
        else:
            print("   ⚠️ Table does not exist yet (will be created when first permission is issued)")
        
        # Check platform_users table
        print("\n🔍 Checking platform_users table...")
        if table_exists(db, 'platform_users'):
            result = db.execute(text("SELECT COUNT(*) FROM platform_users")).fetchone()
            total_count = result[0] if result else 0
            print(f"   Total records: {total_count}")
            
            result = db.execute(text("SELECT COUNT(*) FROM platform_users WHERE user_did LIKE 'did:lemma:user:%'")).fetchone()
            old_count = result[0] if result else 0
            print(f"   Old format: {old_count}")
            
            if old_count > 0:
                print(f"\n🧹 Clearing {old_count} old platform_users records...")
                db.execute(text("DELETE FROM platform_users WHERE user_did LIKE 'did:lemma:user:%'"))
                db.commit()
                print("   ✅ Done!")
        else:
            print("   ⚠️ Table does not exist yet")
        
        # Check customers table (may have user_did column from migration 007)
        print("\n🔍 Checking customers table...")
        if table_exists(db, 'customers'):
            result = db.execute(text("SELECT COUNT(*) FROM customers")).fetchone()
            total_count = result[0] if result else 0
            print(f"   Total records: {total_count}")
            
            # Check if user_did column exists
            try:
                result = db.execute(text("SELECT COUNT(*) FROM customers WHERE user_did IS NOT NULL")).fetchone()
                print(f"   Records with user_did: {result[0] if result else 0}")
                
                result = db.execute(text("SELECT COUNT(*) FROM customers WHERE user_did LIKE 'did:lemma:user:%'")).fetchone()
                old_count = result[0] if result else 0
                print(f"   Old format: {old_count}")
                
                if old_count > 0:
                    print(f"\n🧹 Clearing {old_count} old user_did values...")
                    db.execute(text("UPDATE customers SET user_did = NULL WHERE user_did LIKE 'did:lemma:user:%'"))
                    db.commit()
                    print("   ✅ Done!")
            except Exception as e:
                print(f"   ⚠️ user_did column may not exist: {e}")
        else:
            print("   ⚠️ Table does not exist")
        
        print("\n✅ Migration check complete!")
        print("   User identifiers now use PPIDs (site-specific, unlinkable)")
        print("   Format: did:lemma:ppid_<HMAC(wallet_secret, site_id)>")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    run_migration()

