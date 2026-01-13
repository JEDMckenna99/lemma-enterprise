#!/usr/bin/env python3
"""
Run migration 012: Wallet Credentials Server Sync

Creates the wallet_credentials table for storing synced credentials
from third-party sites, enabling the unified wallet view.
"""

import os
import psycopg2

def run_migration():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not set")
        return False
    
    # Heroku uses postgres:// but psycopg2 needs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg2.connect(database_url, sslmode='require')
        cur = conn.cursor()
        
        # Read migration file
        with open('migrations/012_wallet_credentials.sql', 'r') as f:
            migration_sql = f.read()
        
        print("🚀 Running migration 012: Wallet Credentials Server Sync")
        cur.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        
        # Verify table exists
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'wallet_credentials'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        
        print("\n📋 wallet_credentials table columns:")
        for col_name, col_type in columns:
            print(f"   - {col_name}: {col_type}")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    run_migration()
