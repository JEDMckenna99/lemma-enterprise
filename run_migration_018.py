#!/usr/bin/env python
"""Run migration 018 for agent credentials tables."""
import os
import psycopg2

# Read migration
with open('migrations/018_agent_credentials.sql', 'r') as f:
    migration_sql = f.read()

# Connect and execute
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()
cursor.execute(migration_sql)
conn.commit()
print('Migration 018_agent_credentials.sql executed successfully')
cursor.close()
conn.close()
