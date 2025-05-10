#!/usr/bin/env python3
"""
Admin Reset Script for Lemma Enterprise

This script directly modifies the admin credentials in the data directory.
"""
import os
import json
import getpass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Data directory
DATA_DIR = os.path.join(os.path.expanduser('~'), '.lemma_enterprise')
os.makedirs(DATA_DIR, exist_ok=True)

def reset_admin_credentials():
    """Reset admin credentials in the environment and config files."""
    print("=== LEMMA ADMIN RESET ===\n")
    
    # Get admin credentials from environment or use defaults
    admin_user = os.environ.get('LEMMA_ADMIN_USER', 'admin')
    admin_pass = os.environ.get('LEMMA_ADMIN_PASS', 'password')
    
    print(f"Current admin credentials:")
    print(f"  - Username: {admin_user}")
    print(f"  - Password: {'*' * len(admin_pass)}")
    
    # Update .env file with admin credentials
    env_path = os.path.join(os.getcwd(), '.env')
    
    # Read existing .env content
    env_content = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_content = f.readlines()
    
    # Check if admin credentials are already in .env
    admin_user_found = False
    admin_pass_found = False
    
    for i, line in enumerate(env_content):
        if line.startswith('LEMMA_ADMIN_USER='):
            env_content[i] = f'LEMMA_ADMIN_USER={admin_user}\n'
            admin_user_found = True
        elif line.startswith('LEMMA_ADMIN_PASS='):
            env_content[i] = f'LEMMA_ADMIN_PASS={admin_pass}\n'
            admin_pass_found = True
    
    # Add admin credentials if not found
    if not admin_user_found:
        env_content.append(f'LEMMA_ADMIN_USER={admin_user}\n')
    if not admin_pass_found:
        env_content.append(f'LEMMA_ADMIN_PASS={admin_pass}\n')
    
    # Write updated .env content
    with open(env_path, 'w') as f:
        f.writelines(env_content)
    
    print(f"✅ Admin credentials set in .env file")
    
    # Set in current environment
    os.environ['LEMMA_ADMIN_USER'] = admin_user
    os.environ['LEMMA_ADMIN_PASS'] = admin_pass
    
    # Create or update admin config file
    admin_config = {
        "username": admin_user,
        "password": admin_pass,
        "role": "admin",
        "created_at": "2025-05-09T00:00:00Z"
    }
    
    admin_file = os.path.join(DATA_DIR, 'admin.json')
    with open(admin_file, 'w') as f:
        json.dump(admin_config, f, indent=2)
    
    print(f"✅ Admin credentials set in {admin_file}")
    
    print("\n🔑 Admin credentials have been reset.")
    print("Please restart the server for changes to take effect.")
    print("You can now log in with:")
    print(f"  - Username: {admin_user}")
    print(f"  - Password: {admin_pass}")

if __name__ == "__main__":
    reset_admin_credentials()
