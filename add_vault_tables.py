#!/usr/bin/env python3
"""
Add Vault Storage Tables to Heroku PostgreSQL
============================================

This script adds the vault storage tables needed for device sync
to your existing Heroku PostgreSQL database.

Run with: python add_vault_tables.py
"""

import os
import psycopg2
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_vault_tables():
    """Add vault storage tables to PostgreSQL database"""
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable not found")
        logger.info("💡 Run: heroku config:get DATABASE_URL --app lemma-enterprise")
        return False
    
    try:
        # Connect to database
        logger.info("🔗 Connecting to Heroku PostgreSQL...")
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Check if vault tables already exist
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('vault_envelopes', 'vault_access_log', 'vault_rate_limits')
        """)
        
        existing_tables = [row[0] for row in cur.fetchall()]
        
        if existing_tables:
            logger.info(f"⚠️ Found existing vault tables: {existing_tables}")
            response = input("Continue and recreate tables? (y/N): ")
            if response.lower() != 'y':
                logger.info("❌ Aborted by user")
                return False
            
            # Drop existing tables
            for table in existing_tables:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                logger.info(f"🗑️ Dropped existing table: {table}")
        
        # Create vault_envelopes table
        logger.info("📦 Creating vault_envelopes table...")
        cur.execute("""
            CREATE TABLE vault_envelopes (
                id SERIAL PRIMARY KEY,
                vid VARCHAR(64) UNIQUE NOT NULL,
                ciphertext TEXT NOT NULL,
                counter INTEGER NOT NULL DEFAULT 1,
                aad TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                last_accessed_at TIMESTAMP,
                client_ip INET,
                expires_at TIMESTAMP
            )
        """)
        
        # Create indexes for vault_envelopes
        cur.execute("CREATE INDEX idx_vault_vid ON vault_envelopes(vid)")
        cur.execute("CREATE INDEX idx_vault_created_at ON vault_envelopes(created_at)")
        cur.execute("CREATE INDEX idx_vault_expires_at ON vault_envelopes(expires_at)")
        
        # Create vault_access_log table
        logger.info("📋 Creating vault_access_log table...")
        cur.execute("""
            CREATE TABLE vault_access_log (
                id SERIAL PRIMARY KEY,
                vid VARCHAR(64) NOT NULL,
                operation VARCHAR(20) NOT NULL,
                client_ip INET NOT NULL,
                user_agent TEXT,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                response_time_ms INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for vault_access_log
        cur.execute("CREATE INDEX idx_vault_log_vid_op ON vault_access_log(vid, operation)")
        cur.execute("CREATE INDEX idx_vault_log_timestamp ON vault_access_log(timestamp)")
        cur.execute("CREATE INDEX idx_vault_log_client_ip ON vault_access_log(client_ip)")
        cur.execute("CREATE INDEX idx_vault_log_failed ON vault_access_log(success, timestamp)")
        
        # Create vault_rate_limits table
        logger.info("⏱️ Creating vault_rate_limits table...")
        cur.execute("""
            CREATE TABLE vault_rate_limits (
                id SERIAL PRIMARY KEY,
                vid VARCHAR(64) NOT NULL,
                client_ip INET NOT NULL,
                request_count INTEGER DEFAULT 1,
                window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_request TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vid, client_ip, window_start)
            )
        """)
        
        # Create indexes for vault_rate_limits
        cur.execute("CREATE INDEX idx_vault_rate_window ON vault_rate_limits(vid, client_ip, window_start)")
        cur.execute("CREATE INDEX idx_vault_rate_cleanup ON vault_rate_limits(window_start)")
        
        # Commit all changes
        conn.commit()
        
        logger.info("✅ All vault tables created successfully!")
        
        # Verify tables exist
        cur.execute("""
            SELECT table_name, 
                   (SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = t.table_name AND table_schema = 'public') as column_count
            FROM information_schema.tables t
            WHERE table_schema = 'public' 
            AND table_name LIKE 'vault_%'
            ORDER BY table_name
        """)
        
        tables = cur.fetchall()
        logger.info("📊 Vault tables summary:")
        for table_name, column_count in tables:
            logger.info(f"   • {table_name}: {column_count} columns")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")
        return False
        
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def main():
    """Main function"""
    logger.info("🚀 Starting vault table migration...")
    logger.info("=" * 50)
    
    success = add_vault_tables()
    
    if success:
        logger.info("=" * 50)
        logger.info("🎉 VAULT MIGRATION COMPLETE!")
        logger.info("✅ Device sync will now work with persistent storage")
        logger.info("✅ QR code wallet transfer ready for production")
        logger.info("✅ Mobile device sync fully functional")
    else:
        logger.error("❌ Migration failed - device sync may not work")
    
    return success

if __name__ == "__main__":
    main()
