"""Check database tables for admin dashboard data"""
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print('=== SITES TABLE ===')
cur.execute('SELECT site_id, site_domain, admin_email, created_at FROM sites ORDER BY created_at DESC LIMIT 10')
for row in cur.fetchall():
    print(f'  {row[0]} | {row[1]} | {row[2]} | {row[3]}')

print()
print('=== CUSTOMERS TABLE ===')
cur.execute('SELECT customer_id, email, sites, created_at FROM customers ORDER BY created_at DESC LIMIT 10')
for row in cur.fetchall():
    sites = row[2] if row[2] else []
    site_count = len(sites) if isinstance(sites, list) else 0
    print(f'  {row[0][:20] if row[0] else "N/A"}... | {row[1]} | sites: {site_count} | {row[3]}')

print()
print('=== COUNTS ===')
cur.execute('SELECT COUNT(*) FROM sites')
print(f'  Sites table: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM customers')
print(f'  Customers table: {cur.fetchone()[0]}')

cur.execute("SELECT COUNT(*) FROM customers WHERE sites IS NOT NULL AND sites::text != '[]'")
print(f'  Customers with sites JSON: {cur.fetchone()[0]}')

cur.close()
conn.close()
