#!/usr/bin/env python3
"""
Database Migration Runner for Lemma IAM
Run this to apply database migrations
"""

import os
import sys
import psycopg2
from psycopg2 import sql
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL') or os.getenv('HEROKU_POSTGRESQL_JADE_URL')

def run_migration(migration_file):
    """
    Run a SQL migration file
    
    Usage:
        python migrations/run_migration.py migrations/001_create_audit_logs.sql
    """
    database_url = get_database_url()
    
    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        logger.error("   Set DATABASE_URL environment variable")
        return False
    
    try:
        # Read migration file
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        logger.info(f"📝 Running migration: {migration_file}")
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Execute migration
        cur.execute(migration_sql)
        conn.commit()
        
        logger.info(f"✅ Migration completed successfully")
        
        # Close connection
        cur.close()
        conn.close()
        
        return True
        
    except FileNotFoundError:
        logger.error(f"❌ Migration file not found: {migration_file}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

def run_all_migrations():
    """Run all pending migrations in order"""
    import glob
    
    migration_files = sorted(glob.glob('migrations/*.sql'))
    
    if not migration_files:
        logger.warning("⚠️ No migration files found")
        return
    
    logger.info(f"Found {len(migration_files)} migration files")
    
    for migration_file in migration_files:
        success = run_migration(migration_file)
        if not success:
            logger.error(f"❌ Migration failed, stopping: {migration_file}")
            return False
    
    logger.info("✅ All migrations completed successfully")
    return True

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Run specific migration
        migration_file = sys.argv[1]
        run_migration(migration_file)
    else:
        # Run all migrations
        run_all_migrations()

