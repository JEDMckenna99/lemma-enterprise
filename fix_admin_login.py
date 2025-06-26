#!/usr/bin/env python3
"""
Fix admin login configuration.
"""

import os
import json
from werkzeug.security import generate_password_hash

def fix_admin_login():
    """Ensure admin login works properly."""
    
    print("🔧 Fixing Admin Login Configuration")
    print("=" * 50)
    
    # Update customer account
    customer_file = os.path.join('instance', 'data', 'customers', '6160d9eb-3bfb-4061-9a25-1fc44270260e.json')
    
    with open(customer_file, 'r') as f:
        customer_data = json.load(f)
    
    # Ensure the password is set correctly
    customer_data['password_hash'] = generate_password_hash('Menace13')
    customer_data['login_enabled'] = True
    customer_data['login_methods'] = ['email_password', 'admin_panel']
    
    with open(customer_file, 'w') as f:
        json.dump(customer_data, f, indent=2)
    
    print("✅ Customer account login updated")
    
    # Create/update admin credentials file
    admin_file = os.path.join('instance', 'admins.json')
    
    admins = {
        "admin": {
            "username": "admin",
            "password_hash": generate_password_hash('Menace13'),
            "email": "jedmckenna@lemma.id",
            "permissions": ["all"]
        },
        "jedmckenna": {
            "username": "jedmckenna",
            "password_hash": generate_password_hash('Menace13'),
            "email": "jedmckenna@lemma.id", 
            "permissions": ["all"]
        }
    }
    
    os.makedirs(os.path.dirname(admin_file), exist_ok=True)
    with open(admin_file, 'w') as f:
        json.dump(admins, f, indent=2)
    
    print("✅ Admin credentials file created/updated")
    
    print("\n🎯 Login Options:")
    print("1. Admin Panel: https://lemma.id/admin/login")
    print("   Username: admin (or jedmckenna)")
    print("   Password: Menace13")
    print()
    print("2. Customer Portal: https://lemma.id/onboarding/login")
    print("   Email: jedmckenna@lemma.id")
    print("   Password: Menace13")

if __name__ == "__main__":
    fix_admin_login() 