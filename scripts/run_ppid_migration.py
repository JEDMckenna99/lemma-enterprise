#!/usr/bin/env python3
"""
Run PPID migration to clear old global DIDs and update to PPID-based tracking.
Run this on Heroku: heroku run python scripts/run_ppid_migration.py --app lemma-enterprise
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    from api.database import get_db
    from sqlalchemy import text
    
    db = get_db()
    
    try:
        # Check what's in the database first
        print("🔍 Checking current user_permissions...")
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
        
        # Check platform_users table
        print("\n🔍 Checking platform_users table...")
        try:
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
        except Exception as e:
            print(f"   ⚠️ platform_users table may not exist: {e}")
        
        # Final verification
        print("\n📊 Final verification:")
        result = db.execute(text("SELECT COUNT(*) FROM user_permissions")).fetchone()
        print(f"   user_permissions records: {result[0] if result else 0}")
        
        print("\n✅ Migration complete!")
        print("   User identifiers now use PPIDs (site-specific, unlinkable)")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    run_migration()
