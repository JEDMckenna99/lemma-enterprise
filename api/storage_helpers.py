"""
Storage Helpers for PostgreSQL normalized tables

These helpers write to the normalized sites and api_keys tables,
enabling the transition away from JSON columns in the customers table.
"""

import os
import logging
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)


def get_pg_connection():
    """Get a raw PostgreSQL connection for direct SQL"""
    import psycopg2
    
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    
    # Handle Heroku-style postgres:// URLs
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return psycopg2.connect(database_url, sslmode='require')


def upsert_site_to_postgres(site_id: str, site_domain: str, customer_id: str,
                            company_name: str = '', admin_email: str = '',
                            environment: str = 'production', site_label: str = ''):
    """
    Insert or update a site in the PostgreSQL sites table.
    This is the normalized storage - eventually will replace customers.sites JSON.
    """
    conn = None
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO sites (site_id, site_domain, customer_id, company_name, 
                             admin_email, environment, site_label, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', NOW())
            ON CONFLICT (site_id) DO UPDATE SET
                site_domain = EXCLUDED.site_domain,
                customer_id = EXCLUDED.customer_id,
                company_name = EXCLUDED.company_name,
                admin_email = EXCLUDED.admin_email,
                environment = EXCLUDED.environment,
                site_label = EXCLUDED.site_label,
                updated_at = NOW()
        """, (site_id, site_domain, customer_id, company_name, admin_email, 
              environment, site_label))
        
        conn.commit()
        cursor.close()
        logger.info(f"✅ Upserted site {site_id} to PostgreSQL")
        return True
        
    except Exception as e:
        logger.error(f"Failed to upsert site to PostgreSQL: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def upsert_api_key_to_postgres(customer_id: str, site_id: str, key_hash: str,
                               key_hint: str, name: str = 'API Key',
                               environment: str = 'production'):
    """
    Insert or update an API key in the PostgreSQL api_keys table.
    This is the normalized storage - eventually will replace customers.api_keys JSON.
    """
    conn = None
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_keys (customer_id, site_id, key_hash, key_hint, name,
                                 environment, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW())
            ON CONFLICT (key_hash) DO UPDATE SET
                name = EXCLUDED.name,
                environment = EXCLUDED.environment
        """, (customer_id, site_id, key_hash, key_hint, name, environment))
        
        conn.commit()
        cursor.close()
        logger.info(f"✅ Upserted API key to PostgreSQL (site: {site_id})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to upsert API key to PostgreSQL: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def get_customer_sites_from_postgres(customer_id: str) -> list:
    """
    Get all sites for a customer from the PostgreSQL sites table.
    This is the preferred read path - eventually will be the only source.
    """
    conn = None
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT site_id, site_domain, company_name, environment, site_label,
                   status, created_at
            FROM sites 
            WHERE customer_id = %s AND status = 'active'
            ORDER BY created_at DESC
        """, (customer_id,))
        
        sites = []
        for row in cursor.fetchall():
            sites.append({
                'site_id': row[0],
                'site_domain': row[1],
                'company_name': row[2],
                'environment': row[3],
                'site_label': row[4],
                'status': row[5],
                'created_at': row[6].isoformat() if row[6] else None
            })
        
        cursor.close()
        return sites
        
    except Exception as e:
        logger.warning(f"Could not read sites from PostgreSQL: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_customer_api_keys_from_postgres(customer_id: str) -> list:
    """
    Get all API keys for a customer from the PostgreSQL api_keys table.
    """
    conn = None
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT site_id, key_hint, name, environment, status, 
                   created_at, last_used, usage_count
            FROM api_keys 
            WHERE customer_id = %s AND status = 'active'
            ORDER BY created_at DESC
        """, (customer_id,))
        
        keys = []
        for row in cursor.fetchall():
            keys.append({
                'site_id': row[0],
                'key_hint': row[1],
                'name': row[2],
                'environment': row[3],
                'status': row[4],
                'created_at': row[5].isoformat() if row[5] else None,
                'last_used': row[6].isoformat() if row[6] else None,
                'usage_count': row[7] or 0
            })
        
        cursor.close()
        return keys
        
    except Exception as e:
        logger.warning(f"Could not read API keys from PostgreSQL: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_sites_for_customer_from_postgres(customer_id: str) -> list:
    """
    Get sites for a customer - tries PostgreSQL first, then falls back to JSON lookup.
    This is the transition function used during migration.
    """
    # First try PostgreSQL
    pg_sites = get_customer_sites_from_postgres(customer_id)
    if pg_sites:
        logger.info(f"📊 Got {len(pg_sites)} sites from PostgreSQL for customer {customer_id}")
        return pg_sites
    
    # Fallback to JSON column
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT api_keys, sites FROM customers WHERE customer_id = %s
        """, (customer_id,))
        
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row:
            return []
        
        import json
        api_keys_data = row[0]
        sites_data = row[1]
        
        if isinstance(api_keys_data, str):
            api_keys_data = json.loads(api_keys_data) if api_keys_data else []
        if isinstance(sites_data, str):
            sites_data = json.loads(sites_data) if sites_data else []
        
        sites = []
        
        # Get sites from sites JSON
        for site_entry in (sites_data or []):
            site_id = site_entry.get('site_id')
            if site_id:
                sites.append({
                    'site_id': site_id,
                    'site_domain': site_entry.get('site_domain') or site_entry.get('domain') or site_id,
                    'company_name': site_entry.get('company_name') or site_entry.get('label') or '',
                    'environment': site_entry.get('environment') or 'production',
                    'site_label': site_entry.get('site_label') or site_entry.get('label') or ''
                })
        
        # Also check API keys for any site_ids not in sites list
        existing_site_ids = {s['site_id'] for s in sites}
        for key_data in (api_keys_data or []):
            key_site_id = key_data.get('site_id')
            if key_site_id and key_data.get('status') != 'revoked' and key_site_id not in existing_site_ids:
                sites.append({
                    'site_id': key_site_id,
                    'site_domain': key_site_id,
                    'company_name': key_data.get('name', ''),
                    'environment': 'production',
                    'site_label': ''
                })
        
        logger.info(f"📊 Got {len(sites)} sites from JSON columns for customer {customer_id}")
        return sites
        
    except Exception as e:
        logger.error(f"Failed to get sites for customer {customer_id}: {e}")
        return []
