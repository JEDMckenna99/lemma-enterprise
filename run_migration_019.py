"""Run migration 019 - site_api_keys table"""
import psycopg2
import os

def run():
    conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')
    cur = conn.cursor()
    
    cur.execute('''
    CREATE TABLE IF NOT EXISTS site_api_keys (
        id SERIAL PRIMARY KEY,
        site_id VARCHAR(50) NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
        key_name VARCHAR(255) NOT NULL,
        key_hash VARCHAR(64) NOT NULL UNIQUE,
        key_prefix VARCHAR(20) NOT NULL,
        key_type VARCHAR(10) DEFAULT 'live',
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(255),
        last_used TIMESTAMP,
        expires_at TIMESTAMP,
        permissions JSONB DEFAULT '["read", "write"]'::jsonb
    )
    ''')
    
    # Create indexes
    cur.execute('CREATE INDEX IF NOT EXISTS idx_site_api_keys_site ON site_api_keys(site_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_site_api_keys_hash ON site_api_keys(key_hash)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_site_api_keys_active ON site_api_keys(site_id, is_active)')
    
    conn.commit()
    print('Migration 019 completed successfully - site_api_keys table created')
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    run()
