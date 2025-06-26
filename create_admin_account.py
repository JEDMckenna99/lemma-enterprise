#!/usr/bin/env python3
"""
Create Admin Customer Account
Creates a customer account with admin privileges for jedmckenna@lemma.id
"""

import os
import sys
import json
import uuid
import secrets
import hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash

# Add lemma package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def hash_password(password: str) -> str:
    """Hash password using Werkzeug."""
    return generate_password_hash(password)

def hash_api_key(api_key: str) -> str:
    """Hash API key for secure storage."""
    salt = "lemma_api_key_salt_2024"  # Same salt as in onboarding.py
    return hashlib.sha256((api_key + salt).encode()).hexdigest()

def create_admin_customer():
    """Create admin customer account."""
    
    # Customer details
    email = "jedmckenna@lemma.id"
    company = "lemma"
    domain = "lemma.id"
    password = "Menace13"
    
    # Generate IDs and keys
    customer_id = str(uuid.uuid4())
    verification_token = secrets.token_hex(12)
    api_key = f"lemma_admin_{secrets.token_hex(32)}"
    
    print(f"Creating admin customer account...")
    print(f"Email: {email}")
    print(f"Company: {company}")
    print(f"Domain: {domain}")
    print(f"Customer ID: {customer_id}")
    print(f"API Key: {api_key}")
    
    # Create customer data with admin privileges
    customer_data = {
        'customer_id': customer_id,
        'email': email,
        'company': company,
        'domain': domain,
        'password_hash': hash_password(password),
        'verification_token': verification_token,
        'api_key': api_key,  # Store plain API key for admin
        'api_key_hash': hash_api_key(api_key),
        'api_key_created_at': datetime.now().isoformat(),
        'verified': True,  # Pre-verify admin account
        'verified_at': datetime.now().isoformat(),
        'verification_method': 'admin_created',
        'created_at': datetime.now().isoformat(),
        'last_login': None,
        
        # Admin privileges
        'is_admin': True,
        'admin_level': 'super_admin',
        'admin_permissions': [
            'customer_management',
            'api_key_management', 
            'billing_management',
            'system_administration',
            'security_management',
            'compliance_management'
        ],
        
        # Billing fields
        'stripe_customer_id': None,
        'stripe_subscription_id': None,
        'billing_status': 'admin_exempt',
        'billing_email': email,
        'current_rate': 0.00,  # Admin gets free access
        
        # Enhanced admin metadata
        'account_type': 'admin',
        'created_by': 'system_admin',
        'notes': 'Primary admin account for Lemma platform owner'
    }
    
    # Ensure directories exist
    storage_dir = 'instance/data'
    customers_dir = os.path.join(storage_dir, 'customers')
    os.makedirs(customers_dir, exist_ok=True)
    
    # Save customer data
    customer_file = os.path.join(customers_dir, f'{customer_id}.json')
    with open(customer_file, 'w') as f:
        json.dump(customer_data, f, indent=2)
    
    print(f"✅ Admin customer account created successfully!")
    print(f"📁 Saved to: {customer_file}")
    print(f"🔑 API Key: {api_key}")
    print(f"🔐 Password: {password}")
    print(f"👤 Customer ID: {customer_id}")
    print(f"✅ Account verified and ready to use")
    print(f"🎯 Admin privileges: Enabled")
    
    # Also create a summary file
    summary_file = os.path.join(storage_dir, 'admin_account_summary.json')
    summary_data = {
        'admin_account_created': datetime.now().isoformat(),
        'email': email,
        'customer_id': customer_id,
        'api_key': api_key,
        'domain': domain,
        'login_url': 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/onboarding/login',
        'dashboard_url': 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/onboarding/dashboard',
        'admin_panel_url': 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/admin'
    }
    
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2)
    
    print(f"📋 Summary saved to: {summary_file}")
    
    return customer_data

if __name__ == "__main__":
    create_admin_customer() 