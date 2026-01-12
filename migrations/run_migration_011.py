"""
Migration 011: Data migration from JSON columns to normalized tables

This script:
1. Adds customer_id column to sites table
2. Creates api_keys table
3. Reads customers.sites JSON and inserts into sites table
4. Reads customers.api_keys JSON and inserts into api_keys table
"""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection"""
    import psycopg2
    
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    
    # Handle Heroku-style postgres:// URLs
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return psycopg2.connect(database_url, sslmode='require')


def run_schema_migration(conn):
    """Run the schema changes"""
    cursor = conn.cursor()
    
    # Step 1: Add customer_id column to sites table
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'sites' AND column_name = 'customer_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sites ADD COLUMN customer_id VARCHAR(50)")
            logger.info("✅ Added customer_id column to sites table")
        else:
            logger.info("✅ customer_id column already exists")
    except Exception as e:
        logger.warning(f"Could not add customer_id: {e}")
        conn.rollback()
    
    conn.commit()
    
    # Step 2: Add environment column
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'sites' AND column_name = 'environment'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sites ADD COLUMN environment VARCHAR(20) DEFAULT 'production'")
            logger.info("✅ Added environment column to sites table")
        else:
            logger.info("✅ environment column already exists")
    except Exception as e:
        logger.warning(f"Could not add environment: {e}")
        conn.rollback()
    
    conn.commit()
    
    # Step 3: Add site_label column
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'sites' AND column_name = 'site_label'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE sites ADD COLUMN site_label VARCHAR(255)")
            logger.info("✅ Added site_label column to sites table")
        else:
            logger.info("✅ site_label column already exists")
    except Exception as e:
        logger.warning(f"Could not add site_label: {e}")
        conn.rollback()
    
    conn.commit()
    
    # Step 4: Make columns nullable
    for col in ['api_key', 'oauth_client_id', 'company_name']:
        try:
            cursor.execute(f"ALTER TABLE sites ALTER COLUMN {col} DROP NOT NULL")
            logger.info(f"✅ Made {col} nullable")
        except Exception as e:
            logger.debug(f"Could not alter {col}: {e}")
            conn.rollback()
    
    conn.commit()
    
    # Step 5: Create api_keys table
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                customer_id VARCHAR(50) NOT NULL,
                site_id VARCHAR(50) NOT NULL,
                key_hash VARCHAR(64) NOT NULL UNIQUE,
                key_hint VARCHAR(8) NOT NULL,
                name VARCHAR(255) DEFAULT 'API Key',
                status VARCHAR(20) DEFAULT 'active',
                environment VARCHAR(20) DEFAULT 'production',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                usage_count INTEGER DEFAULT 0,
                revoked_at TIMESTAMP
            )
        """)
        logger.info("✅ Created api_keys table")
    except Exception as e:
        logger.warning(f"Could not create api_keys table: {e}")
        conn.rollback()
    
    conn.commit()
    
    # Step 6: Add indexes
    indexes = [
        ("idx_sites_customer_id", "sites", "customer_id"),
        ("idx_sites_environment", "sites", "environment"),
        ("idx_api_keys_customer", "api_keys", "customer_id"),
        ("idx_api_keys_site", "api_keys", "site_id"),
        ("idx_api_keys_status", "api_keys", "status"),
    ]
    
    for idx_name, table, column in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
            logger.info(f"✅ Created index {idx_name}")
        except Exception as e:
            logger.debug(f"Could not create index {idx_name}: {e}")
            conn.rollback()
    
    conn.commit()
    cursor.close()
    logger.info("✅ Schema migration complete")


def migrate_sites(conn):
    """Migrate sites from customers.sites JSON to sites table"""
    cursor = conn.cursor()
    
    # Get all customers with sites
    cursor.execute("SELECT customer_id, sites FROM customers WHERE sites IS NOT NULL AND sites::text != '[]'")
    customers = cursor.fetchall()
    
    migrated = 0
    skipped = 0
    
    for customer_id, sites_json in customers:
        sites_data = sites_json if isinstance(sites_json, list) else json.loads(sites_json or '[]')
        
        for site_entry in sites_data:
            site_id = site_entry.get('site_id')
            site_domain = site_entry.get('site_domain') or site_entry.get('domain')
            
            if not site_id:
                logger.warning(f"Skipping site entry without site_id for customer {customer_id}")
                skipped += 1
                continue
            
            # Check if site already exists
            cursor.execute("SELECT site_id FROM sites WHERE site_id = %s", (site_id,))
            if cursor.fetchone():
                # Update existing site with customer_id
                cursor.execute("""
                    UPDATE sites SET customer_id = %s WHERE site_id = %s AND customer_id IS NULL
                """, (customer_id, site_id))
                logger.info(f"Updated existing site {site_id} with customer_id {customer_id}")
            else:
                # Insert new site
                try:
                    cursor.execute("""
                        INSERT INTO sites (
                            site_id, site_domain, company_name, admin_email, customer_id,
                            environment, site_label, oauth_client_secret, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, '', NOW())
                        ON CONFLICT (site_id) DO UPDATE SET customer_id = EXCLUDED.customer_id
                    """, (
                        site_id,
                        site_domain or site_id,
                        site_entry.get('company_name') or site_entry.get('label') or '',
                        site_entry.get('admin_email') or site_entry.get('contact_email') or '',
                        customer_id,
                        site_entry.get('environment') or 'production',
                        site_entry.get('label') or site_entry.get('site_label') or ''
                    ))
                    migrated += 1
                    logger.info(f"Migrated site {site_id} ({site_domain}) for customer {customer_id}")
                except Exception as e:
                    logger.error(f"Failed to migrate site {site_id}: {e}")
                    conn.rollback()
                    skipped += 1
    
    conn.commit()
    cursor.close()
    logger.info(f"Sites migration complete: {migrated} migrated, {skipped} skipped")
    return migrated, skipped


def migrate_api_keys(conn):
    """Migrate API keys from customers.api_keys JSON to api_keys table"""
    cursor = conn.cursor()
    
    # Get all customers with api_keys
    cursor.execute("SELECT customer_id, api_keys FROM customers WHERE api_keys IS NOT NULL AND api_keys::text != '[]'")
    customers = cursor.fetchall()
    
    migrated = 0
    skipped = 0
    
    for customer_id, api_keys_json in customers:
        api_keys_data = api_keys_json if isinstance(api_keys_json, list) else json.loads(api_keys_json or '[]')
        
        for key_entry in api_keys_data:
            site_id = key_entry.get('site_id')
            
            if not site_id:
                logger.debug(f"Skipping API key without site_id for customer {customer_id}")
                skipped += 1
                continue
            
            # Get key_hash (either stored or compute from key)
            key_hash = key_entry.get('key_hash')
            key_hint = key_entry.get('key_hint')
            
            if not key_hash:
                raw_key = key_entry.get('key')
                if raw_key:
                    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
                    key_hint = raw_key[-8:] if len(raw_key) > 8 else raw_key
                else:
                    logger.warning(f"Skipping API key without key or key_hash for customer {customer_id}")
                    skipped += 1
                    continue
            
            # Check if this key already exists
            cursor.execute("SELECT id FROM api_keys WHERE key_hash = %s", (key_hash,))
            if cursor.fetchone():
                logger.debug(f"API key already exists (hash: {key_hash[:16]}...)")
                continue
            
            # Insert new API key
            try:
                cursor.execute("""
                    INSERT INTO api_keys (
                        customer_id, site_id, key_hash, key_hint, name,
                        status, environment, created_at, last_used, usage_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (key_hash) DO NOTHING
                """, (
                    customer_id,
                    site_id,
                    key_hash,
                    key_hint or '',
                    key_entry.get('name') or 'API Key',
                    key_entry.get('status') or 'active',
                    key_entry.get('environment') or 'production',
                    key_entry.get('created_at') or datetime.utcnow(),
                    key_entry.get('last_used'),
                    key_entry.get('usage_count') or 0
                ))
                migrated += 1
                logger.info(f"Migrated API key for site {site_id} (customer {customer_id})")
            except Exception as e:
                logger.error(f"Failed to migrate API key for site {site_id}: {e}")
                conn.rollback()
                skipped += 1
    
    conn.commit()
    cursor.close()
    logger.info(f"API keys migration complete: {migrated} migrated, {skipped} skipped")
    return migrated, skipped


def verify_migration(conn):
    """Verify migration completed successfully"""
    cursor = conn.cursor()
    
    # Count sites with customer_id
    cursor.execute("SELECT COUNT(*) FROM sites WHERE customer_id IS NOT NULL")
    sites_with_customer = cursor.fetchone()[0]
    
    # Count total api_keys
    cursor.execute("SELECT COUNT(*) FROM api_keys")
    total_api_keys = cursor.fetchone()[0]
    
    # Count customers with JSON data
    cursor.execute("SELECT COUNT(*) FROM customers WHERE sites IS NOT NULL AND sites::text != '[]'")
    customers_with_sites = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM customers WHERE api_keys IS NOT NULL AND api_keys::text != '[]'")
    customers_with_keys = cursor.fetchone()[0]
    
    cursor.close()
    
    logger.info("=" * 50)
    logger.info("Migration Verification:")
    logger.info(f"  Sites with customer_id: {sites_with_customer}")
    logger.info(f"  Total API keys in table: {total_api_keys}")
    logger.info(f"  Customers with sites JSON: {customers_with_sites}")
    logger.info(f"  Customers with api_keys JSON: {customers_with_keys}")
    logger.info("=" * 50)
    
    return {
        'sites_with_customer': sites_with_customer,
        'total_api_keys': total_api_keys,
        'customers_with_sites': customers_with_sites,
        'customers_with_keys': customers_with_keys
    }


def run_migration():
    """Run the full data migration"""
    logger.info("Starting storage consolidation migration...")
    
    try:
        conn = get_db_connection()
        
        # Run schema migration first
        logger.info("Running schema migration...")
        run_schema_migration(conn)
        
        # Migrate sites data
        logger.info("Migrating sites...")
        sites_migrated, sites_skipped = migrate_sites(conn)
        
        # Migrate API keys data
        logger.info("Migrating API keys...")
        keys_migrated, keys_skipped = migrate_api_keys(conn)
        
        # Verify migration
        stats = verify_migration(conn)
        
        conn.close()
        
        logger.info("=" * 50)
        logger.info("Migration Complete!")
        logger.info(f"  Sites migrated: {sites_migrated}")
        logger.info(f"  API keys migrated: {keys_migrated}")
        logger.info("=" * 50)
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
