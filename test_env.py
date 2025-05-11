#!/usr/bin/env python3
"""
Environment Setup for Lemma Enterprise Tests

This script creates a suitable test environment by setting up necessary
environment variables for testing the Lemma Human Verification System.
"""
import os
import sys
import json
from uuid import uuid4

# Default environment variables for testing
DEFAULT_ENV_VARS = {
    # Core settings
    "LEMMA_ADMIN_USER": "admin",
    "LEMMA_ADMIN_PASS": "password",
    "LEMMA_SECRET_KEY": "test_secret_key",
    "LEMMA_BASE_URL": "http://localhost:5000",
    "LEMMA_API_KEY": str(uuid4()),
    
    # Storage settings
    "LEMMA_STORAGE_DIR": "./.lemma_enterprise",
    
    # Security settings
    "LEMMA_SESSION_TIMEOUT": "3600",
    "LEMMA_RATE_LIMIT": "100/hour",
    
    # Testing flags
    "TESTING": "True",
    "VERIFY_TLS": "False"
}

def setup_test_env():
    """Set up environment variables for testing."""
    print("Setting up test environment...")
    
    # Start with defaults
    env_vars = DEFAULT_ENV_VARS.copy()
    
    # Load any existing .env file
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f.readlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    env_vars[key] = value
    
    # Set environment variables
    for key, value in env_vars.items():
        os.environ[key] = value
        print(f"✅ Set {key}")
    
    print("\n✅ Test environment set up successfully!")
    print(f"Admin User: {env_vars['LEMMA_ADMIN_USER']}")
    print(f"Admin Password: {env_vars['LEMMA_ADMIN_PASS']}")
    print(f"Base URL: {env_vars['LEMMA_BASE_URL']}")
    
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        print("\n✅ Created .env file with test settings")
    
    return env_vars

if __name__ == "__main__":
    setup_test_env()
    print("\n🚀 You can now run tests with the configured environment.")
