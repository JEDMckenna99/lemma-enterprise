#!/usr/bin/env python3
"""
Investigate a specific user signup on Lemma platform
Run with: heroku run python investigate_user.py --app lemma-enterprise-0f6ba17076c1
"""

import os
import psycopg2
from datetime import datetime

EMAIL_TO_INVESTIGATE = "plbybit8@gmail.com"

def investigate():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL not set. Run this on Heroku.")
        return
    
    # Fix URL for psycopg2
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    conn = psycopg2.connect(db_url, sslmode='require')
    cursor = conn.cursor()
    
    print(f"\n{'='*60}")
    print(f"INVESTIGATING: {EMAIL_TO_INVESTIGATE}")
    print(f"{'='*60}\n")
    
    # 1. Check permission_instances (IAM signups / beta users)
    print("--- PERMISSION INSTANCES (IAM/Beta Signups) ---")
    cursor.execute("""
        SELECT 
            pi.id,
            pi.site_id,
            pi.email,
            pi.credential_did,
            pi.granted_at,
            pi.granted_by,
            pi.expires_at,
            pi.metadata,
            pt.name as permission_type
        FROM permission_instances pi
        LEFT JOIN permission_types pt ON pi.permission_type_id = pt.id
        WHERE LOWER(pi.email) = LOWER(%s)
        ORDER BY pi.granted_at DESC
    """, (EMAIL_TO_INVESTIGATE,))
    
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  ID: {row[0]}")
            print(f"  Site ID: {row[1]}")
            print(f"  Email: {row[2]}")
            print(f"  Credential DID: {row[3]}")
            print(f"  Granted At: {row[4]}")
            print(f"  Granted By: {row[5]}")
            print(f"  Expires At: {row[6]}")
            print(f"  Metadata: {row[7]}")
            print(f"  Permission Type: {row[8]}")
            print("-" * 40)
    else:
        print("  No permission instances found for this email.\n")
    
    # 2. Check customers table (developer accounts)
    print("\n--- CUSTOMERS TABLE (Developer Accounts) ---")
    cursor.execute("""
        SELECT 
            customer_id,
            email,
            name,
            company,
            created_at,
            status,
            last_login,
            login_count
        FROM customers
        WHERE LOWER(email) = LOWER(%s)
    """, (EMAIL_TO_INVESTIGATE,))
    
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Customer ID: {row[0]}")
            print(f"  Email: {row[1]}")
            print(f"  Name: {row[2]}")
            print(f"  Company: {row[3]}")
            print(f"  Created At: {row[4]}")
            print(f"  Status: {row[5]}")
            print(f"  Last Login: {row[6]}")
            print(f"  Login Count: {row[7]}")
            print("-" * 40)
    else:
        print("  No customer account found for this email.\n")
    
    # 3. Check network_activity for any activity with IP/user-agent
    print("\n--- NETWORK ACTIVITY (IP/User-Agent Info) ---")
    cursor.execute("""
        SELECT 
            activity_type,
            service_type,
            success,
            timestamp,
            ip_address,
            user_agent,
            activity_metadata
        FROM network_activity
        WHERE activity_metadata::text ILIKE %s
        ORDER BY timestamp DESC
        LIMIT 10
    """, (f'%{EMAIL_TO_INVESTIGATE}%',))
    
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Activity Type: {row[0]}")
            print(f"  Service Type: {row[1]}")
            print(f"  Success: {row[2]}")
            print(f"  Timestamp: {row[3]}")
            print(f"  IP Address: {row[4]}")
            print(f"  User Agent: {row[5]}")
            print(f"  Metadata: {row[6]}")
            print("-" * 40)
    else:
        print("  No network activity found for this email.\n")
    
    # 4. Check site_users table
    print("\n--- SITE USERS TABLE ---")
    cursor.execute("""
        SELECT 
            site_id,
            user_did,
            user_email,
            display_name,
            user_status,
            user_role,
            added_by,
            added_at,
            last_login,
            site_user_metadata
        FROM site_users
        WHERE LOWER(user_email) = LOWER(%s)
    """, (EMAIL_TO_INVESTIGATE,))
    
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Site ID: {row[0]}")
            print(f"  User DID: {row[1]}")
            print(f"  Email: {row[2]}")
            print(f"  Display Name: {row[3]}")
            print(f"  Status: {row[4]}")
            print(f"  Role: {row[5]}")
            print(f"  Added By: {row[6]}")
            print(f"  Added At: {row[7]}")
            print(f"  Last Login: {row[8]}")
            print(f"  Metadata: {row[9]}")
            print("-" * 40)
    else:
        print("  No site_users entry found for this email.\n")
    
    # 5. Check audit_log for any actions by this user
    print("\n--- AUDIT LOG ---")
    cursor.execute("""
        SELECT 
            action,
            details,
            actor_id,
            timestamp,
            ip_address
        FROM audit_log
        WHERE details::text ILIKE %s
        ORDER BY timestamp DESC
        LIMIT 10
    """, (f'%{EMAIL_TO_INVESTIGATE}%',))
    
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  Action: {row[0]}")
            print(f"  Details: {row[1]}")
            print(f"  Actor ID: {row[2]}")
            print(f"  Timestamp: {row[3]}")
            print(f"  IP Address: {row[4]}")
            print("-" * 40)
    else:
        print("  No audit log entries found.\n")
    
    # Close connection
    cursor.close()
    conn.close()
    
    print(f"\n{'='*60}")
    print("ANALYSIS NOTES:")
    print("='*60}")
    print("- 'plbybit8' could be a shortened handle for 'PolyBit' or similar")
    print("- Check if the email domain pattern matches any known contacts")
    print("- The '8' suffix suggests multiple accounts or version")
    print("- Could be a crypto/Web3 user (Bybit is a crypto exchange)")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    investigate()


