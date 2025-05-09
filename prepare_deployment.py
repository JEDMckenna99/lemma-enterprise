#!/usr/bin/env python3
"""
Deployment Preparation Script for Lemma Enterprise

This script prepares the Lemma Human Verification System for deployment
by creating a deployment package and setting up the necessary configuration.
"""
import os
import sys
import json
import shutil
import tempfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def check_environment_variables():
    """Check if all required environment variables are set."""
    print_header("Checking Environment Variables")
    
    required_vars = {
        "LEMMA_ADMIN_USER": os.environ.get("LEMMA_ADMIN_USER", "admin"),
        "LEMMA_ADMIN_PASS": os.environ.get("LEMMA_ADMIN_PASS", "password"),
        "LEMMA_SECRET_KEY": os.environ.get("LEMMA_SECRET_KEY", "default-secret-key-for-development")
    }
    
    optional_vars = {
        "TWILIO_ACCOUNT_SID": os.environ.get("TWILIO_ACCOUNT_SID", ""),
        "TWILIO_AUTH_TOKEN": os.environ.get("TWILIO_AUTH_TOKEN", ""),
        "TWILIO_PHONE_NUMBER": os.environ.get("TWILIO_PHONE_NUMBER", "")
    }
    
    # Check required variables
    all_required_set = True
    for var_name, var_value in required_vars.items():
        if var_value:
            print(f"✅ {var_name} is set")
        else:
            print(f"❌ {var_name} is not set")
            all_required_set = False
    
    # Check optional variables
    sms_enabled = all([optional_vars["TWILIO_ACCOUNT_SID"], 
                      optional_vars["TWILIO_AUTH_TOKEN"], 
                      optional_vars["TWILIO_PHONE_NUMBER"]])
    
    if sms_enabled:
        print("\n✅ SMS functionality is enabled with Twilio credentials")
    else:
        print("\n⚠️ SMS functionality will be disabled in deployment")
        print("To enable SMS, set the following environment variables:")
        for var_name in optional_vars:
            if not optional_vars[var_name]:
                print(f"  - {var_name}")
    
    return all_required_set, required_vars, optional_vars

def create_deployment_config(required_vars, optional_vars):
    """Create a deployment configuration file."""
    print_header("Creating Deployment Configuration")
    
    config = {
        "app_name": "LemmaHumanVerification",
        "environment_variables": {
            **required_vars,
            **{k: v for k, v in optional_vars.items() if v}  # Only include set optional vars
        },
        "sms_enabled": all([optional_vars["TWILIO_ACCOUNT_SID"], 
                           optional_vars["TWILIO_AUTH_TOKEN"], 
                           optional_vars["TWILIO_PHONE_NUMBER"]])
    }
    
    config_file = "deployment_config.json"
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Deployment configuration saved to: {config_file}")
    return config_file

def create_deployment_package():
    """Create a deployment package (zip file) from the source directory."""
    print_header("Creating Deployment Package")
    
    source_dir = os.getcwd()
    print(f"Source directory: {source_dir}")
    
    # Create a temporary directory for the package
    temp_dir = tempfile.mkdtemp()
    package_dir = os.path.join(temp_dir, "lemma-enterprise-package")
    os.makedirs(package_dir)
    
    # Copy all files except .git, __pycache__, etc.
    ignore_patterns = ['.git', '__pycache__', '.pytest_cache', '.vscode', 'venv', 'env', '.env', 
                      '*.zip', '*.pyc', 'deployment_config.json', 'lemma_test_credential_*.json']
    
    for item in os.listdir(source_dir):
        skip = False
        for pattern in ignore_patterns:
            if pattern.startswith('*'):
                if item.endswith(pattern[1:]):
                    skip = True
                    break
            elif item == pattern or (pattern.startswith('.') and item.startswith(pattern)):
                skip = True
                break
        
        if skip:
            continue
        
        source_item = os.path.join(source_dir, item)
        dest_item = os.path.join(package_dir, item)
        
        if os.path.isdir(source_item):
            shutil.copytree(source_item, dest_item, ignore=shutil.ignore_patterns(*ignore_patterns))
        else:
            shutil.copy2(source_item, dest_item)
    
    # Create a zip file
    zip_file = os.path.join(os.getcwd(), "lemma-enterprise.zip")
    shutil.make_archive(os.path.splitext(zip_file)[0], 'zip', package_dir)
    
    # Clean up temporary directory
    shutil.rmtree(temp_dir)
    
    print(f"✅ Deployment package created: {zip_file}")
    print(f"   Package size: {os.path.getsize(zip_file) / (1024*1024):.2f} MB")
    return zip_file

def main():
    """Main function to prepare for deployment."""
    print_header("LEMMA ENTERPRISE DEPLOYMENT PREPARATION")
    
    # Check environment variables
    all_required_set, required_vars, optional_vars = check_environment_variables()
    
    if not all_required_set:
        print("\n❌ Some required environment variables are not set.")
        print("Please set them before proceeding with deployment.")
        return False
    
    # Create deployment configuration
    config_file = create_deployment_config(required_vars, optional_vars)
    
    # Create deployment package
    zip_file = create_deployment_package()
    
    print_header("DEPLOYMENT PREPARATION COMPLETE")
    print("Your Lemma Human Verification System is ready for deployment!")
    print("\nTo deploy to Azure, run:")
    print("  python deploy_to_azure.py")
    print("\nThe deployment script will use the configuration in:")
    print(f"  {config_file}")
    print("\nThe deployment package is:")
    print(f"  {zip_file}")
    
    return True

if __name__ == "__main__":
    main()
